#!/usr/bin/env python3
"""manaka-store.com（EC）の商品を、Device（src/device.json と assets/device/）に取り込む。

EC に商品が増えた・文や値段や写真が変わった時の手順（標準ライブラリだけで動く）:
  python3 tools/import_store.py --fetch     # EC の公開ページと写真を _agent/store-snapshot/ に写す（Device は変えない）
  python3 tools/import_store.py --check     # 写しを読んで、取り込む中身を確かめる（何も書かない）
  python3 tools/import_store.py             # src/device.json と assets/device/ に書く
  python3 tools/build.py && python3 tools/build.py --check

何を取り込むか:
- 対象は products/list?category_id= 1・2・3・4・21 の一覧に並ぶ商品（重なりは 1 件）。一覧の件数（ページの
  ItemList の numberOfItems と「全 N 件」）と、並んでいる商品の数が合わなければ止まる。
- 商品 ID は EC の商品番号、ec_url は EC の商品ページ。category は EC の商品ページのパンくずの大きいカテゴリ
  （一覧に出るカテゴリ全部は store_import.category_ids に持つ）。
- 文は EC の商品ページに見えている文をそのまま写す（足さない・直さない）: 商品名、商品名の下の一言（copy）、
  コンセプトの本文（body）、特徴（features）、商品仕様（specs）、よくあるご質問（highlights）。
- 商品仕様は、今の商品ページの型に出す欄が無いので、EC と同じ見出し・写真・文で features の最後にも入れる。
- 規格（色など）ごとに、EC の名前・税抜の値段・写真を variants に入れる。値段は、src/site.json の price の決まりで
  出る税込が EC の税込と合うことを確かめる（合わなければ止まる）。
- 写真は EC と同じファイルを、撮影情報の区画だけ除いて assets/device/ に EC と同じ名前で置く（画素は触らない）。

上書きしないもの:
- この道具の印（store_import）が無い商品（Device 表から来た星牌など）。
- 取り込みの後に手で直した商品（印の content_sha256 と中身が合わなくなった商品）。EC に合わせ直したい時は、
  その商品を device.json から外してから取り込む。
- EC の一覧から消えた商品は消さない（報告に出る）。

取り方: --fetch は 1 件ずつ、間隔をあけて取る。ページは毎回取り直し、写真は写しにあれば取り直さない。
途中で止まった時は --fetch --missing で、写しに無いページと写真だけを取る。読めない商品が 1 つでもあれば、
どの商品が何で読めなかったかを出して、何も書かずに止まる。
"""

import argparse
import base64
import gzip
import hashlib
from html.parser import HTMLParser
from http.client import HTTPException, HTTPSConnection
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import getproxies, proxy_bypass
import zlib

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "https://manaka-store.com"
HOSTS = {"manaka-store.com"}
CATEGORY_IDS = ("1", "2", "3", "4", "21")
SHOP = "祈りの道具屋まなか"          # src/site.json の shops の match
IMAGE_DIR = "/html/upload/save_image/"
IMAGE_NAME = r"[0-9A-Za-z][0-9A-Za-z_.-]*\.(?:jpe?g|png|webp)"
INTERVAL = 0.6                        # 取得の間隔（秒）。本番の店なので並列にしない
MAX_FILE = 25 * 1024 * 1024
MAX_LIST_PAGES = 50
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5",
         "li", "ul", "ol", "dl", "dt", "dd", "table", "tr", "th", "td", "figure", "figcaption"}


class ImportError(ValueError):
    """確かめられなかったので、何も書かずに止める。"""


# ── HTML を木にする（標準ライブラリだけ） ─────────────────────────────

class Node:
    def __init__(self, tag="", attrs=(), parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs), [], parent

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def elements(self, tag=None):
        return [c for c in self.children if isinstance(c, Node) and (tag is None or c.tag == tag)]

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def find(self, predicate):
        return next((n for n in self.walk() if n is not self and predicate(n)), None)

    def find_all(self, predicate):
        return [n for n in self.walk() if n is not self and predicate(n)]

    def by_id(self, value):
        found = [n for n in self.walk() if n.attrs.get("id") == value]
        return found[0] if found else None

    def text(self):
        """見える文。<br> は改行、ブロックの境も改行 1 つ。行の前後の空白だけを落とす（文は変えない）。"""
        parts = []

        def render(node):
            if isinstance(node, str):
                parts.append(re.sub(r"[\t\r\n\f ]+", " ", node))
            elif node.tag == "br":
                parts.append("\n")
            elif node.tag not in {"script", "style", "noscript", "template"}:
                edge = ["\f"] if node.tag in BLOCK else []
                parts.extend(edge)
                for child in node.children:
                    render(child)
                parts.extend(edge)

        render(self)
        raw = re.sub(r" *([\n\f]) *", r"\1", re.sub(r" {2,}", " ", "".join(parts)))
        raw = raw.replace("\n\f", "\f")       # ブロックの境の直前の <br> は、行を変えるだけ（空行にならない）
        return re.sub(r"\f+", "\n", raw).strip("\n ")


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


# ── 住所と写し ───────────────────────────────────────────────────────

def checked_url(value, base=ORIGIN):
    url = urlsplit(urljoin(base, value))
    if (url.scheme != "https" or url.hostname not in HOSTS
            or url.username or url.password or url.port not in {None, 443}):
        raise ImportError("取得の対象は manaka-store.com の HTTPS だけ: %r" % value)
    return urlunsplit(("https", url.hostname, url.path or "/", url.query, ""))


def list_url(category, page=1):
    return "%s/products/list?category_id=%s%s" % (ORIGIN, category, "" if page == 1 else "&pageno=%d" % page)


def product_id(url):
    match = re.fullmatch(r"/products/detail/([1-9][0-9]*)/?", urlsplit(url).path)
    return match.group(1) if match else None


def product_url(pid):
    return "%s/products/detail/%s" % (ORIGIN, pid)


def image_url(name):
    if not re.fullmatch(IMAGE_NAME, name):
        raise ImportError("写真の名前の形が違う: %r" % name)
    return ORIGIN + IMAGE_DIR + name


def image_name(src, base):
    """商品の写真（/html/upload/save_image/ の直下）の名前。それ以外の画像は None。"""
    url = urlsplit(checked_url(src, base))
    if not url.path.startswith(IMAGE_DIR) or url.query:
        return None
    name = url.path[len(IMAGE_DIR):]
    return name if re.fullmatch(IMAGE_NAME, name) else None


class Snapshot:
    """EC のページと写真の写し。manifest.json の resources が「住所 → 写しのファイル」。"""

    def __init__(self, path, fetch=False, missing_only=False):
        self.path, self.fetch, self.missing_only = Path(path).resolve(), fetch, missing_only
        self.resources, self.fresh, self.downloaded, self.last, self.connection = {}, set(), 0, 0.0, None
        manifest = self.path / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("schema") != "manaka-store-snapshot/1" or not isinstance(data.get("resources"), dict):
                raise ImportError("写しの manifest.json の形が違う")
            self.resources = {str(k): str(v) for k, v in data["resources"].items()}
        elif not fetch:
            raise ImportError("写しが無い: %s（先に --fetch）" % self.path)

    def target(self, name):
        target = self.path / name
        if not re.fullmatch(r"resources/[0-9a-f]{64}", name) or target.is_symlink():
            raise ImportError("写しのファイルの名前が違う: %r" % name)
        return target

    def has(self, url):
        name = self.resources.get(url)
        return bool(name) and self.target(name).is_file()

    def connect(self):
        """店への接続を 1 本だけ開いて使い回す（1 件ごとに閉じる取り方だと、店の応答が途中で切れることがある）。"""
        host = urlsplit(ORIGIN).hostname
        proxy = getproxies().get("https")
        if proxy and not proxy_bypass(host):
            via = urlsplit(proxy if "://" in proxy else "http://" + proxy)
            if via.scheme != "http":
                raise ImportError("https の取得に使える中継（http の proxy）でない")
            headers = {}
            if via.username:
                pair = "%s:%s" % (unquote(via.username), unquote(via.password or ""))
                headers["Proxy-Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
            connection = HTTPSConnection(via.hostname, via.port or 8080, timeout=60)
            connection.set_tunnel(host, 443, headers)
            return connection
        return HTTPSConnection(host, 443, timeout=60)

    def get(self, url):
        for _ in range(4):                                   # 転送は 3 回まで（先も manaka-store.com だけ）
            parts = urlsplit(url)
            if self.connection is None:
                self.connection = self.connect()
            self.connection.request("GET", parts.path + ("?" + parts.query if parts.query else ""), headers={
                "Host": parts.hostname, "User-Agent": "MA-Device-Import/1.0", "Accept-Encoding": "gzip"})
            response = self.connection.getresponse()
            body = response.read(MAX_FILE + 1)
            if len(body) > MAX_FILE:
                raise ImportError("25 MiB を超えるファイル: " + url)
            if response.status in {301, 302, 303, 307, 308} and response.getheader("Location"):
                url = checked_url(response.getheader("Location"), url)
                continue
            if response.status != 200:
                raise HTTPError(url, response.status, response.reason, response.headers, None)
            if response.getheader("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body
        raise ImportError("転送が多すぎる: " + url)

    def download(self, url, page):
        wait = INTERVAL - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self.last = time.monotonic()
            try:
                data = self.get(url)
                if page and not data.rstrip().endswith(b"</html>"):
                    raise HTTPException("ページが途中で切れている")
                break
            except HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    raise ImportError("取れなかった（HTTP %d）: %s" % (exc.code, url)) from exc
                error = exc
            except (HTTPException, OSError, EOFError, zlib.error) as exc:   # 途中で切れた・つながらない → 待って取り直す
                error = exc
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            if attempt == 2:
                raise ImportError("取れなかった（%s）: %s" % (error, url))
            time.sleep(5 * (attempt + 1))
        if len(data) > MAX_FILE:
            raise ImportError("25 MiB を超えるファイル: " + url)
        name = "resources/" + hashlib.sha256(data).hexdigest()
        target = self.target(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            atomic_write(target, data)
        self.resources[url] = name
        self.fresh.add(url)
        self.downloaded += 1
        if self.downloaded % 20 == 0:
            self.save()
        return data

    def read(self, url, page=False):
        """page=True はページ（--fetch のたびに読み直す）。写真は写しにあれば取り直さない。"""
        url = checked_url(url)
        if self.fetch and url not in self.fresh and not (self.has(url) and (self.missing_only or not page)):
            return self.download(url, page)
        if not self.has(url):
            raise ImportError("写しに無い（--fetch で取る）: " + url)
        target = self.target(self.resources[url])
        if target.stat().st_size > MAX_FILE:
            raise ImportError("25 MiB を超えるファイル: " + url)
        return target.read_bytes()

    def html(self, url):
        try:
            return self.read(url, page=True).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportError("UTF-8 で読めないページ: " + url) from exc

    def save(self):
        self.path.mkdir(parents=True, exist_ok=True)
        write_json(self.path / "manifest.json", {
            "schema": "manaka-store-snapshot/1", "resources": dict(sorted(self.resources.items()))})


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def atomic_write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".import-", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


# ── 一覧 ─────────────────────────────────────────────────────────────

def json_ld(root, kind):
    found = []
    for node in root.walk():
        if node.tag == "script" and node.attrs.get("type") == "application/ld+json":
            try:
                value = json.loads("".join(c for c in node.children if isinstance(c, str)))
            except json.JSONDecodeError as exc:
                raise ImportError("JSON-LD を読めない") from exc
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and item.get("@type") == kind:
                    found.append(item)
    return found


def read_listing(html, category):
    """一覧の 1 ページ → (並んでいる商品 ID, カテゴリ名, EC の言う件数)。商品が無いページは ([], None, None)。"""
    root = Document(html).root
    grid = root.by_id("product-list")
    if grid is None or grid.tag != "ul":
        raise ImportError("カテゴリ %s: 一覧（ul#product-list）が見つからない" % category)
    ids = []
    for item in grid.elements("li"):
        if "product-item" not in item.classes():
            raise ImportError("カテゴリ %s: 一覧に商品でない項目がある" % category)
        links = {product_id(checked_url(a.attrs["href"], list_url(category)))
                 for a in item.find_all(lambda n: n.tag == "a" and n.attrs.get("href"))}
        links.discard(None)
        if len(links) != 1:
            raise ImportError("カテゴリ %s: 商品ページへのリンクを 1 つに決められない項目がある" % category)
        ids.append(links.pop())
    if len(set(ids)) != len(ids):
        raise ImportError("カテゴリ %s: 一覧に同じ商品が 2 度出ている" % category)
    if not ids:
        return [], None, None
    lists = json_ld(root, "ItemList")
    if len(lists) != 1:
        raise ImportError("カテゴリ %s: 一覧の件数（ItemList）を読めない" % category)
    listed = [product_id(checked_url(e.get("url", ""))) for e in lists[0].get("itemListElement", [])]
    name, number = lists[0].get("name"), lists[0].get("numberOfItems")
    if not isinstance(name, str) or not name.strip() or not isinstance(number, int):
        raise ImportError("カテゴリ %s: カテゴリ名か件数を読めない" % category)
    if set(listed) != set(ids) or len(listed) != len(ids):
        raise ImportError("カテゴリ %s: ItemList の商品と、並んでいる商品が合わない" % category)
    shown = re.search(r"全\s*([0-9,]+)\s*件", root.text())           # ページに出ている「全 N 件」
    if shown and amount(shown.group(1)) != number:
        raise ImportError("カテゴリ %s: ページの「全 %s 件」と ItemList の %d 件が合わない" % (category, shown.group(1), number))
    return ids, name.strip(), number


def catalog(snapshot):
    """5 カテゴリの一覧 → (商品 ID → カテゴリ ID の並び〔EC の並び順〕, カテゴリ ID → 名前, カテゴリ ID → 件数)。"""
    membership, names, counts = {}, {}, {}
    for category in CATEGORY_IDS:
        ids, number = [], None
        for page in range(1, MAX_LIST_PAGES + 1):
            found, name, total = read_listing(snapshot.html(list_url(category, page)), category)
            new = [pid for pid in found if pid not in ids]
            if not new:
                break
            if page == 1:
                names[category], number = name, total
            elif total != number:
                raise ImportError("カテゴリ %s: ページごとに件数が違う" % category)
            ids.extend(new)
        else:
            raise ImportError("カテゴリ %s: 一覧のページが多すぎる" % category)
        if not ids or number != len(ids):
            raise ImportError("カテゴリ %s: EC の件数 %s と、並んでいた %d 件が合わない" % (category, number, len(ids)))
        counts[category] = len(ids)
        for pid in ids:
            membership.setdefault(pid, []).append(category)
    return membership, names, counts


# ── 商品ページ ───────────────────────────────────────────────────────

def one(nodes, what):
    if len(nodes) != 1:
        raise ImportError("%s が %d 個ある（1 個のはず）" % (what, len(nodes)))
    return nodes[0]


def amount(value):
    value = str(value).strip().replace(",", "")
    if not re.fullmatch(r"[0-9]+", value):
        raise ImportError("値段を数字として読めない: %r" % value)
    return int(value)


def shown_price(net, rule):
    """tools/build.py の shown_price と同じ計算（device.json の値段 → サイトに出る値段）。"""
    if rule.get("sheet") == "税抜":
        return net * (100 + rule.get("tax_percent", 10)) // 100
    return net


def stored_price(net, gross, rule):
    """device.json に持つ値段。サイトに出る値段が EC の税込と合うことを確かめる。"""
    if rule.get("sheet") != "税抜":
        return gross
    if shown_price(net, rule) == gross:
        return net
    raise ImportError("EC の税抜 %d 円から出る税込が、EC の税込 %d 円と合わない" % (net, gross))


def read_variants(root, column, gallery, rule):
    """規格（色など）ごとの名前・値段・写真。EC の eccube.classCategories と、規格の選択欄から読む。

    規格の写真は、EC が規格を選んだ時に切り替える写真（color_image_file_name）。EC はページの上の写真の並び
    （gallery）にある時だけ切り替えるので、並びに無い名前（EC に実体の無い古い名前がある）と、写真の無い規格は、
    EC で出たままになる 1 枚目の写真にする。
    """
    found = []
    for node in root.walk():
        if node.tag == "script":
            script = "".join(c for c in node.children if isinstance(c, str))
            for match in re.finditer(r"eccube\.classCategories\s*=\s*", script):
                try:
                    found.append(json.JSONDecoder().raw_decode(script[match.end():])[0])
                except json.JSONDecodeError as exc:
                    raise ImportError("規格の JSON を読めない") from exc
    classes = one(found, "規格の JSON（eccube.classCategories）")
    classes = {k: v for k, v in classes.items() if k != "__unselected"}
    select = [n for n in root.walk() if n.tag == "select" and n.attrs.get("id") == "classcategory_id1"]
    if any(n.tag == "select" and n.attrs.get("id") == "classcategory_id2" for n in root.walk()):
        raise ImportError("規格が 2 段ある商品は、まだ読めない")
    if select:
        labels = {o.attrs.get("value"): o.text() for o in one(select, "規格の選択欄").find_all(lambda n: n.tag == "option")}
        labels.pop("__unselected", None)
        if list(labels) != list(classes):
            raise ImportError("規格の選択欄と、規格の JSON が合わない")
    else:
        labels = None       # 選択欄の無い商品（問い合わせで買う商品）。規格の名前が EC に出ていないので、名前の無い 1 つにまとめる
    if not classes:
        raise ImportError("規格が 1 つも無い")
    variants, gross = [], []
    for key, group in classes.items():
        if not isinstance(group, dict) or list(group) != ["#"]:
            raise ImportError("規格が 2 段ある商品は、まだ読めない")
        item = group["#"]
        gross.append(amount(item.get("price02_inc_tax", "")))
        image = item.get("color_image_file_name")
        variants.append({"color": labels[key] if labels else "",
                         "list_price": amount(item["price01"]) if item.get("price01") else None,
                         "price": stored_price(amount(item.get("price02", "")), gross[-1], rule),
                         "image": image if labels and image in gallery else gallery[0]})
    if labels is None:
        if any(v != variants[0] for v in variants):
            raise ImportError("選択欄が無いのに、規格ごとに値段が違う")
        variants = variants[:1]
    # 商品ページの上に出ている値段（「77,000 円(税込)」「55,000 ～ 66,000 円(税込)」）と突き合わせる
    price = one(column.find_all(lambda n: "price02-default" in n.classes()), "値段の表示")
    if "税込" not in price.parent.text():
        raise ImportError("値段の表示が税込か確かめられない")
    shown = [amount(x) for x in re.findall(r"[0-9][0-9,]*", price.text())]
    if shown not in ([min(gross)], [min(gross), max(gross)]) or (len(shown) == 1 and min(gross) != max(gross)):
        raise ImportError("商品ページの値段の表示 %s と、規格ごとの税込 %s が合わない" % (shown, sorted(set(gross))))
    return variants


def read_product(html, pid, categories, names, rule):
    """商品ページ → device.json の 1 商品。EC の文はそのまま写す。"""
    root = Document(html).root
    canonical = one([n for n in root.walk() if n.tag == "link" and n.attrs.get("rel") == "canonical"], "canonical")
    if product_id(checked_url(canonical.attrs.get("href", ""))) != pid:
        raise ImportError("ページの canonical が、この商品の番号でない")
    main = one([n for n in root.walk() if n.tag == "main"], "main")
    heading = main.by_id("heading")
    if heading is None:
        raise ImportError("商品の見出しの区画（#heading）が無い")
    title = one(heading.find_all(lambda n: n.tag == "h1"), "商品名（h1）")
    name = title.text()
    data = one(json_ld(root, "Product"), "JSON-LD の Product")
    if not name or "\n" in name or name != str(data.get("name", "")).strip():
        raise ImportError("商品名を 1 つに決められない（h1 %r / JSON-LD %r）" % (name, data.get("name")))
    column = title
    while column is not heading and not column.find(lambda n: "ec-price" in n.classes()):
        column = column.parent
    copies = column.elements("p")
    if len(copies) > 1:
        raise ImportError("商品名の下の一言を 1 つに決められない")
    copy = copies[0].text() if copies else ""
    if " ".join(copy.split()) != " ".join(str(data.get("description") or "").split()):
        raise ImportError("商品名の下の一言が、JSON-LD の description と合わない")
    # ページの上の写真の並び（1 枚目がメインの写真）
    gallery = [image_name(a.attrs.get("href", ""), product_url(pid))
               for a in heading.find_all(lambda n: n.tag == "a" and "item" in n.classes())]
    if not gallery or not all(gallery):
        raise ImportError("メインの写真が無い（ページの上の写真の並びを読めない）")
    variants = read_variants(root, column, gallery, rule)

    # コンセプト（商品説明の本文）。見出しの h3 は Device の型に欄が無いので写さない
    body, concept = "", main.by_id("concept")
    if concept is not None:
        body = one(concept.find_all(lambda n: n.tag == "p"), "コンセプトの本文").text()

    # 特徴（写真 1 枚・見出し・本文の組）
    features, feature = [], main.by_id("feature")
    if feature is not None:
        lists = [d for d in feature.elements("div")
                 if not d.find(lambda n: n.tag in {"h2", "audio"})]     # 「特徴」の見出しと、音色の再生は除く
        for block in (one(lists, "特徴の並び").elements() if lists else []):
            headings = {h.text() for h in block.find_all(lambda n: n.tag == "h3")}   # 画面の幅ごとに同じ見出しが 2 つある
            image = one(block.find_all(lambda n: n.tag == "img"), "特徴の写真")
            image = image_name(image.attrs.get("src", ""), product_url(pid))
            if not image:
                raise ImportError("特徴の写真が、商品の写真の置き場に無い")
            features.append({"image": image, "title": one(sorted(headings), "特徴の見出し"),
                             "body": one(block.find_all(lambda n: n.tag == "p"), "特徴の本文").text()})

    # 商品仕様（項目と中身の 2 列の並び）と、その 1 枚目の写真
    specs, spec_image, detail = [], None, main.by_id("detail")
    if detail is not None:
        tables = [u for u in detail.find_all(lambda n: n.tag == "ul")
                  if u.elements("li") and all([e.tag for e in li.elements()] == ["p", "p"] for li in u.elements("li"))]
        for row in one(tables, "商品仕様の表").elements("li"):
            label, value = (cell.text() for cell in row.elements("p"))
            if not label or not value:
                raise ImportError("商品仕様に、空の項目がある")
            specs.append({"label": label, "value": value})
        pictures = [image_name(i.attrs.get("src", ""), product_url(pid)) for i in detail.find_all(lambda n: n.tag == "img")]
        spec_image = next((x for x in pictures if x), None)
    if not specs or not spec_image:
        raise ImportError("商品仕様か、その写真が無い")
    # 商品仕様は、今の商品ページの型（tools/build.py）に出す欄が無い。EC と同じ見出し・1 枚目の写真・文のまま、
    # 特徴の最後の 1 組として出す（項目と中身は改行でつなぐだけ。specs にも項目ごとに持つ）
    spec_title = one(main.by_id("spec").elements("h2"), "商品仕様の見出し").text()
    features.append({"image": spec_image, "title": spec_title,
                     "body": "\n\n".join("%s\n%s" % (x["label"], x["value"]) for x in specs)})

    # よくあるご質問
    highlights, question = [], main.by_id("question")
    for row in (question.find_all(lambda n: n.tag == "li") if question is not None else []):
        asked, answered = row.elements("div") if len(row.elements("div")) == 2 else (None, None)
        if asked is None or [p.text() for p in asked.elements("p")][:1] != ["Q"] or len(asked.elements("p")) != 2 \
                or [p.text() for p in answered.elements("p")] != ["A"] or len(answered.elements("div")) != 1:
            raise ImportError("よくあるご質問の形が違う")
        highlights.append({"q": asked.elements("p")[1].text(), "a": answered.elements("div")[0].text()})

    # カテゴリは、EC の商品ページのパンくずの大きいカテゴリ（5 つの対象のうちのもの）。無ければ一覧のカテゴリ
    category = names[categories[0]]
    for crumbs in json_ld(root, "BreadcrumbList"):
        for entry in crumbs.get("itemListElement", []):
            match = re.search(r"[?&]category_id=([0-9]+)$", str(entry.get("item") or ""))
            if match and match.group(1) in categories and entry.get("position") == 2:
                category = names[match.group(1)]
    return {"id": pid, "name": name, "shop": SHOP, "category": category, "copy": copy, "body": body,
            "highlights": highlights, "specs": specs, "features": features, "variants": variants,
            "ec_url": product_url(pid)}


# ── 写真（撮影情報の区画だけを除く。画素は触らない） ─────────────────────

SCAN_END = re.compile(b"\xff+(?![\x00\xd0-\xd7\xff])")
EXTENSIONS = {"jpeg": (".jpg", ".jpeg"), "png": (".png",), "webp": (".webp",)}


def exif_orientation(payload):
    """APP1（Exif）の向きの値。無ければ None。"""
    if not payload.startswith(b"Exif\x00\x00") or len(payload) < 14:
        return None
    tiff = payload[6:]
    order = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if order is None:
        return None
    offset = struct.unpack(order + "I", tiff[4:8])[0]
    if offset + 2 > len(tiff):
        return None
    for i in range(struct.unpack(order + "H", tiff[offset:offset + 2])[0]):
        entry = tiff[offset + 2 + i * 12:offset + 14 + i * 12]
        if len(entry) == 12 and struct.unpack(order + "H", entry[:2])[0] == 0x0112:
            return struct.unpack(order + "H", entry[8:10])[0]
    return None


def clean_image(data):
    """(撮影情報の区画を除いた中身, 形式)。JPEG は APP1〔Exif・XMP〕・APP13〔IPTC〕・コメント、PNG は eXIf と文字の区画、WebP は EXIF・XMP。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        result, offset, kinds = bytearray(data[:8]), 8, []
        while offset + 12 <= len(data):
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            end = offset + size + 12
            kind = data[offset + 4:offset + 8]
            if end > len(data):
                raise ImportError("PNG が途中で切れている")
            if zlib.crc32(data[offset + 4:end - 4]) & 0xffffffff != struct.unpack(">I", data[end - 4:end])[0]:
                raise ImportError("PNG の検査値が合わない")
            kinds.append(kind)
            if kind not in {b"eXIf", b"iTXt", b"tEXt", b"zTXt"}:
                result.extend(data[offset:end])
            offset = end
            if kind == b"IEND":
                if kinds[0] != b"IHDR" or b"IDAT" not in kinds:
                    raise ImportError("PNG の絵の本体が無い")
                return bytes(result), "png"
        raise ImportError("PNG の終わりの印が無い")
    if data.startswith(b"\xff\xd8\xff"):
        result, offset, frame, scanned = bytearray(data[:2]), 2, False, False
        while offset < len(data):
            start = offset
            if data[offset] != 0xff:
                raise ImportError("JPEG の区画を読めない")
            while offset < len(data) and data[offset] == 0xff:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker == 0xd9:                                    # 終わりの印。その後ろに付いた物は写さない
                if not frame or not scanned:
                    raise ImportError("JPEG の絵の本体が無い")
                result.extend(b"\xff\xd9")
                return bytes(result), "jpeg"
            if marker == 0x01 or 0xd0 <= marker <= 0xd7:
                result.extend(data[start:offset])
                continue
            size = int.from_bytes(data[offset:offset + 2], "big")
            end = offset + size
            if size < 2 or end > len(data):
                raise ImportError("JPEG が途中で切れている")
            if marker == 0xe1 and exif_orientation(data[offset + 2:end]) not in {None, 1}:
                raise ImportError("写真の向きが Exif で回してある（区画を除くと向きが変わる）")
            if marker not in {0xe1, 0xed, 0xfe}:
                result.extend(data[start:end])
            if marker in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                frame = True
            offset = end
            if marker == 0xda:                                    # 絵の本体。次の区画の印まではそのまま写す
                scanned = True
                following = SCAN_END.search(data, offset)
                if following is None:
                    raise ImportError("JPEG の終わりの印が無い")
                result.extend(data[offset:following.start()])
                offset = following.start()
        raise ImportError("JPEG の終わりの印が無い")
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        if int.from_bytes(data[4:8], "little") + 8 != len(data):
            raise ImportError("WebP の長さが合わない")
        chunks, offset, pixels = [], 12, False
        while offset + 8 <= len(data):
            kind = data[offset:offset + 4]
            size = int.from_bytes(data[offset + 4:offset + 8], "little")
            end = offset + 8 + size + size % 2
            if end > len(data):
                raise ImportError("WebP が途中で切れている")
            chunk = bytearray(data[offset:end])
            if kind == b"VP8X" and size == 10:
                chunk[8] &= ~(0x08 | 0x04) & 0xff                 # Exif・XMP ありの印を下ろす
            if kind in {b"VP8 ", b"VP8L", b"ANMF"}:
                pixels = True
            if kind not in {b"EXIF", b"XMP "}:
                chunks.append(chunk)
            offset = end
        if offset != len(data) or not pixels:
            raise ImportError("WebP の絵の本体が無い")
        payload = b"WEBP" + b"".join(chunks)
        return b"RIFF" + len(payload).to_bytes(4, "little") + payload, "webp"
    raise ImportError("JPEG・PNG・WebP のどれでもない")


def asset_name(name, kind):
    """assets/device/ に置く名前。EC と同じ名前。中身と拡張子が合わない時だけ、拡張子を中身に合わせる。"""
    stem, extension = os.path.splitext(name)
    return name if extension.lower() in EXTENSIONS[kind] else stem + EXTENSIONS[kind][0]


# ── 取り込み ─────────────────────────────────────────────────────────

def content_hash(product):
    value = {k: v for k, v in product.items() if k != "store_import"}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def hand_made(product):
    """この道具の印が無い商品（Device 表から来た商品）と、取り込みの後に手で直した商品。上書きしない。"""
    marker = product.get("store_import")
    return (not isinstance(marker, dict) or marker.get("source") != ORIGIN
            or marker.get("content_sha256") != content_hash(product))


def prepare(snapshot, device, rule):
    """写しを全部読んで、書く中身を作る。ここでは何も書かない。"""
    existing = {}
    for product in device["products"]:
        if str(product["id"]) in existing:
            raise ImportError("device.json の商品 ID が重複: %s" % product["id"])
        existing[str(product["id"])] = product
    membership, names, counts = catalog(snapshot)
    imported, images, kept, failed = {}, {}, [], {}
    for pid, categories in membership.items():
        if pid in existing and hand_made(existing[pid]):
            kept.append(pid)
            continue
        try:
            product = read_product(snapshot.html(product_url(pid)), pid, categories, names, rule)
            mine = {}
            for item in product["variants"] + product["features"]:
                try:
                    data, kind = clean_image(snapshot.read(image_url(item["image"])))
                except ImportError as exc:
                    raise ImportError("写真 %s: %s" % (item["image"], exc)) from exc
                item["image"] = asset_name(item["image"], kind)
                if images.get(item["image"], data) != data:
                    raise ImportError("同じ名前で中身の違う写真がある: " + item["image"])
                mine[item["image"]] = data
            product["store_import"] = {"source": ORIGIN, "category_ids": categories,
                                       "content_sha256": content_hash(product)}
            imported[pid] = product
            images.update(mine)
        except ImportError as exc:
            failed[pid] = str(exc)
    # 並び: 今ある商品の順は変えない。新しい商品は、EC の並び（カテゴリ 1→2→3→4→21 の一覧の順）で 1 つ前の商品の後ろに入れる
    order = [str(p["id"]) for p in device["products"]]
    previous = None
    for pid in membership:
        if pid in imported and pid not in existing:
            order.insert(order.index(previous) + 1 if previous in order else 0, pid)
        if pid in order:
            previous = pid
    products = [imported.get(pid, existing.get(pid)) for pid in order]
    report = {"categories": {names[c]: counts[c] for c in CATEGORY_IDS}, "listed": sum(counts.values()),
              "catalog": len(membership),
              "added": [p for p in imported if p not in existing],
              "changed": [p for p in imported if p in existing and existing[p] != imported[p]],
              "same": [p for p in imported if p in existing and existing[p] == imported[p]],
              "kept": kept, "absent": [p for p in existing if p not in membership], "failed": failed,
              "images": len(images), "image_bytes": sum(len(d) for d in images.values())}
    return dict(device, products=products), images, report


def install(device_path, assets_path, result, images, kept_images):
    """写真を置いてから、最後に device.json を書く。手で置いた写真は上書きしない。"""
    for name, data in images.items():
        target = assets_path / name
        if target.is_symlink() or (target.exists() and name in kept_images and target.read_bytes() != data):
            raise ImportError("上書きしない商品が使っている写真と、名前が重なる: " + name)
    assets_path.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, data in images.items():
        target = assets_path / name
        if not target.exists() or target.read_bytes() != data:
            atomic_write(target, data)
            written += 1
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if device_path.read_text(encoding="utf-8") != encoded:
        atomic_write(device_path, encoded.encode("utf-8"))
    return written


def show(report):
    print("カテゴリごとの件数（EC の一覧の件数と一致）: %s ＝ のべ %d・重なりを除いて %d" % (
        " / ".join("%s %d" % pair for pair in report["categories"].items()), report["listed"], report["catalog"]))
    print("取り込む商品: 新しく足す %d・中身が変わる %d・変わらない %d" % (
        len(report["added"]), len(report["changed"]), len(report["same"])))
    if report["changed"]:
        print("  中身が変わる商品 ID: " + " ".join(report["changed"]))
    print("上書きしない商品（Device 表から来た商品・手で直した商品）: " + (" ".join(report["kept"]) or "なし"))
    print("EC の一覧に無い商品（消さずに残す）: " + (" ".join(report["absent"]) or "なし"))
    print("写真: %d 枚・%.1f MiB" % (report["images"], report["image_bytes"] / 1048576))
    for pid, why in report["failed"].items():
        print("読めなかった商品 %s: %s" % (pid, why))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "_agent" / "store-snapshot",
                        help="EC のページと写真の写しを置く所（既定: _agent/store-snapshot。commit しない）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="EC から写しを作る（Device は変えない）")
    mode.add_argument("--check", action="store_true", help="写しを読んで確かめるだけ（何も書かない）")
    parser.add_argument("--missing", action="store_true", help="--fetch で、写しに無いページと写真だけを取る")
    args = parser.parse_args(argv)
    snapshot = None
    try:
        if args.missing and not args.fetch:
            raise ImportError("--missing は --fetch と一緒に使う")
        device_path = ROOT / "src" / "device.json"
        device = json.loads(device_path.read_text(encoding="utf-8"))
        rule = json.loads((ROOT / "src" / "site.json").read_text(encoding="utf-8")).get("price", {})
        snapshot = Snapshot(args.snapshot, args.fetch, args.missing)
        result, images, report = prepare(snapshot, device, rule)
        show(report)
        if args.fetch:
            print("写しを作った: %s（今回取ったのは %d 件）" % (snapshot.path, snapshot.downloaded))
        if report["failed"]:
            raise ImportError("読めなかった商品が %d 件ある。何も書いていない" % len(report["failed"]))
        if not args.fetch and not args.check:
            kept_images = {x.get("image") for p in result["products"] if hand_made(p)
                           for x in p["variants"] + p["features"]}
            written = install(device_path, ROOT / "assets" / "device", result, images, kept_images)
            print("書いた: src/device.json（%d 商品）・assets/device/ の写真 %d 枚" % (len(result["products"]), written))
        return 0
    except (ImportError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("止めた: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if snapshot is not None and snapshot.fetch:
            snapshot.save()


if __name__ == "__main__":
    sys.exit(main())
