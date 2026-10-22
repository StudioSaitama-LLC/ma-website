#!/usr/bin/env python3
"""src/ のデータから、間｜MA の公開用 HTML を生成する。

使い方:
  python3 tools/build.py          # 生成して上書きする
  python3 tools/build.py --check  # 生成結果と repo のファイルが一致するかだけ確かめる（一致しなければ終了コード 1）

- 標準ライブラリだけで動く（Python 3.9 以上）。
- 生成するのは repo 直下の HTML（GitHub Pages が main の直下をそのまま配信するため）。
  生成したファイルの先頭には「直接編集しない」旨の注記を入れる。直すときは src/ を直してから実行する。
- 生成したファイルの一覧は tools/generated.txt に書く（消えたページを見つけるため）。
- 見た目は 2026-10-16 版のデザイン（荒井さんの PC / Phone の PDF）に合わせている。
"""
import argparse
import hashlib
import datetime
import html
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
MARK = "<!-- このファイルは tools/build.py が src/ から生成しています。直接編集せず src/ を直して再生成してください。 -->"
STATUS = {"published": "", "editing": "準備中", "planned": "準備中"}  # 来た人に作る側の段階の違いは要らないので、公開前は「準備中」の 1 つ
LAB_STATUS = ("確認済み", "候補", "相談中")  # Lab の資料の出典の確かめ具合（確認済み＝書誌を国会図書館・CiNii・版元で確かめた）
LAB_QUOTE_MIN = 8  # Lab の引用は、この字数以上の一節を写す（1 字の一致で通らないように）
LAB_NAME_MAX = 6  # Lab の要素の名前の長さ（地図の札に入る長さ）
LAB_GLYPH = {"言葉": "◆", "文章": "■", "音": "●", "映像": "▶", "写真": "▲", "場": "◉"}  # 資料の形の目印（塗りの記号でそろえる）
KIND = {"tv": "TV", "mag": "Magazine", "radio": "Radio"}  # 扉の名前（Home の地図だけで使う）
VIEW = {"tv": "動画", "mag": "読み物", "radio": "音声"}  # 回の中での呼び名（Magazine は badge の「随想記事」などを使う）
KIND_ORDER = {"tv": 0, "mag": 1, "radio": 2}
NEW_COUNT = 3  # 日付の新しい順にこの件数だけ <NEW> を付ける
NEW_DAYS = 60  # ただし、いちばん新しい日付からこの日数より古いものには付けない
# 先読み: 同じサイトの中のリンクに乗せた（スマホは押し始めた）ら、次のページを先に組み立てておく（Chrome・Edge の Speculation Rules。
# 対応していないブラウザは何もしない）。外のサイト・新しい窓で開くものは除く
SPECULATION = ('<script type="speculationrules">{"prerender":[{"where":{"and":[{"href_matches":"/*"},'
               '{"not":{"selector_matches":"[target=_blank], [rel~=nofollow]"}}]},"eagerness":"moderate"}]}</script>')
DEVICE_SEARCH_MIN = 10  # 道具がこの数に満たない間は、検索欄とお店の絞り込みを出さない（1 つを探すための道具は要らない）
SLUG = r"[a-z0-9][a-z0-9-]*"  # URL と id に入る名前（番組・回・お店）
IMAGE_NAME = r"[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)"
BLANK_GIF = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"  # 1px の透明な画像
ARTICLE_META = "<!-- build:meta -->"  # 記事の断片で、日付の行を入れる場所
CJK = "[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"  # 和文の字（ソースの改行を詰める間）


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return html.escape(s or "", quote=True)


def lines(s):
    """改行をそのまま見せる（文に手を入れない）。"""
    return "<br>\n".join(esc(x) for x in (s or "").split("\n"))


def brs(rows):
    """行の並びを <br> でつなぐ（デザインの改行位置を保つ）。"""
    return "<br>".join(esc(x) for x in rows)


def yen(v):
    return "¥{:,}".format(v)


def short_date(d):
    """2026-09-30 → 26/09/30（デザインの表記）。"""
    m = re.fullmatch(r"\d\d(\d\d)-(\d\d)-(\d\d)", d or "")
    return "%s/%s/%s" % m.groups() if m else ""


def dotted(d):
    return d.replace("-", ".") if d else ""


def bad_date(d):
    """YYYY-MM-DD で、実在する日付でなければ True。"""
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", d or ""):
        return True
    try:
        datetime.date.fromisoformat(d)
    except ValueError:
        return True
    return False


def id_key(item):
    return [int(x) for x in item["id"].split("-")]


def drop_code(title):
    """YouTube の題の頭の管理番号（「MA Channel #2.1.2 」）を外す（画面に管理番号を出さない）。"""
    return re.sub(r"^\s*MA Channel\s*#\d+(?:\.\d+)+\s*", "", title or "")


def bracket(title):
    """題を「」で囲む。題に「」があるとき（YouTube の題など）は、入れ子が読みにくいので『』で囲む。"""
    if "「" in title or "」" in title:
        return "『%s』" % title
    return "「%s」" % title


def flat(rows):
    """行の並びを 1 続きの文にする（News の一言は 3 行で切るので、改行で行を使わない）。"""
    out = ""
    for r in (x.strip() for x in rows):
        if not r:
            continue
        if out and not re.search(r"[。．！？!?」』）)…]$", out):
            out += " "
        out += r
    return out


def class_list(attrs):
    """タグの属性の文字列から class の並びを取り出す（data-class などは見ない。引用符の無い値も読む）。"""
    m = re.search(r"(?<![\w-])class\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'>]+)", attrs, flags=re.I)
    return m.group(1).strip("\"'").split() if m else []


def body_blocks(frag):
    """記事の断片から、class に article-body を持つ div の中身を順に返す（コメントは除き、入れ子の div を数える）。"""
    frag = re.sub(r"<!--.*?-->", "", frag, flags=re.S)
    out, done = [], 0
    for m in re.finditer(r"<div\b([^>]*)>", frag, flags=re.I):
        if m.start() < done:
            continue  # 前の本文の塊の中（article-body の入れ子は二重に数えない）
        if "article-body" not in class_list(m.group(1)):
            continue
        depth, start = 1, m.end()
        for t in re.finditer(r"<div\b|</div\s*>", frag[start:], flags=re.I):
            depth += 1 if t.group(0)[1] != "/" else -1
            if depth == 0:
                out.append(frag[start:start + t.start()])
                done = start + t.end()
                break
    return out


def article_text(frag, limit=400):
    """記事の断片から、本文（article-body の段落）の文字だけを冒頭から limit 字まで取り出す。
    <br> は行の区切り、ソースの改行は和文どうしの間なら詰め、それ以外は空白にする。"""
    out = []
    for body in body_blocks(frag):
        for para in re.findall(r"<p\b[^>]*>(.*?)</p\s*>", body, flags=re.S | re.I):
            para = re.sub(r"<br\s*/?>", "\x00", para, flags=re.I)
            para = html.unescape(re.sub(r"<[^>]+>", "", para))
            para = re.sub(r"(?<=%s)[ \t\r]*\n\s*(?=%s)" % (CJK, CJK), "", para)
            para = re.sub(r"\s*\n\s*", " ", para)
            out += [x.strip() for x in para.split("\x00") if x.strip()]
        if sum(len(x) for x in out) >= limit:
            break
    return flat(out)[:limit]


def split_after_block(html, open_tag, where):
    """html を、open_tag で始まる div の閉じタグの直後で 2 つに分ける（入れ子の div を数える）。"""
    start = html.find(open_tag)
    if start < 0:
        raise SystemExit("src/%s: %s が見つかりません" % (where, open_tag))
    depth = 0
    for m in re.finditer(r"<!--.*?-->|<div\b|</div>", html[start:], flags=re.S):
        if m.group(0).startswith("<!--"):
            continue
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            end = start + m.end()
            return html[:end], html[end:]
    raise SystemExit("src/%s: %s の閉じタグがありません" % (where, open_tag))


class Site:
    def __init__(self):
        self.site = load("site.json")
        self.programs = load("programs.json")
        self.contents = load("contents.json")
        self.device = load("device.json")
        self.manifesto = load("manifesto.json")
        self.company = load("company.json")
        self.lab = load("lab.json")
        self.pages = {}
        self.validate()
        self.news = self.collect_news()
        # <NEW> の候補は News の日付と、公開したコンテンツの日付（原稿の日付が回の日付と違う記事にも付くように）
        dates = sorted(set(n["date"] for n in self.news) |
                       set(self.item_date(c) for c in self.contents if c.get("status") == "published" and self.item_date(c)), reverse=True)
        if dates:
            limit = datetime.date.fromisoformat(dates[0]) - datetime.timedelta(days=NEW_DAYS)
            dates = [d for d in dates if datetime.date.fromisoformat(d) >= limit]
        self.new_dates = dates[:NEW_COUNT]

    def validate(self):
        """データの綴り違い・未登録の番組・画像の置き忘れを、生成の前に止める。"""
        errors = []
        slugs = set(p["slug"] for p in self.programs)
        episodes = {}
        for p in self.programs:
            if not re.fullmatch(SLUG, p.get("slug", "")):
                errors.append("programs.json: slug は英小文字・数字・ハイフンだけ: %r" % p.get("slug"))
            if p.get("illust") and not os.path.exists(os.path.join(ROOT, "assets", "illust", p["illust"] + ".svg")):
                errors.append("programs.json %s: assets/illust/%s.svg が無い" % (p["slug"], p["illust"]))
            if p.get("logo", "") not in ("", "top", "end"):
                errors.append("programs.json %s: logo は \"\"・\"top\"・\"end\" のどれか: %r" % (p["slug"], p.get("logo")))
            if p.get("illust_sp", "top") not in ("top", "end"):
                errors.append("programs.json %s: illust_sp は \"top\" か \"end\": %r" % (p["slug"], p.get("illust_sp")))
            if p.get("illust_sp") == "end" and not p.get("illust"):
                errors.append("programs.json %s: illust_sp を \"end\" にするなら illust（絵の名前）も書く" % p["slug"])
            for e in p.get("episodes", []):
                if not isinstance(e.get("title"), str) or not e["title"].strip():
                    errors.append("programs.json %s: 回の title（文字）が要る: %r" % (p["slug"], e.get("key")))
                if not re.fullmatch(SLUG, e.get("key", "")):
                    errors.append("programs.json %s: 回の key は英小文字・数字・ハイフンだけ: %r" % (p["slug"], e.get("key")))
                if e.get("key") in episodes:
                    errors.append("programs.json: 回の key が重複: %s" % e["key"])
                episodes[e.get("key")] = p["slug"]
                if e.get("date") and bad_date(e["date"]):
                    errors.append("programs.json %s: date は YYYY-MM-DD: %r" % (e["key"], e["date"]))
        seen = set()
        for c in self.contents:
            cid = c.get("id", "")
            if not re.fullmatch(r"\d+-\d+-\d+", cid):
                errors.append("contents.json: 番号の形が違う: %r" % cid)
            if cid in seen:
                errors.append("contents.json: 番号が重複: %s" % cid)
            seen.add(cid)
            if c.get("kind") not in KIND:
                errors.append("contents.json #%s: kind は tv / mag / radio のどれか: %r" % (cid, c.get("kind")))
            if c.get("status") not in STATUS:
                errors.append("contents.json #%s: status は published / editing / planned のどれか: %r" % (cid, c.get("status")))
            if c.get("program") not in slugs:
                errors.append("contents.json #%s: programs.json に無い番組: %r" % (cid, c.get("program")))
            if c.get("episode") and episodes.get(c["episode"]) != c.get("program"):
                errors.append("contents.json #%s: 番組 %s に回 %r が無い（programs.json の episodes）"
                              % (cid, c.get("program"), c["episode"]))
            if c.get("date") and bad_date(c["date"]):
                errors.append("contents.json #%s: date は YYYY-MM-DD: %r" % (cid, c["date"]))
            if c.get("soundcloud") and not (c.get("kind") == "radio" and re.fullmatch(r"https://soundcloud\.com/[\w-]+/[\w-]+", c["soundcloud"])):
                errors.append("contents.json #%s: soundcloud は音声（radio）の項目に、https://soundcloud.com/<持ち主>/<回> の形で書く: %r" % (cid, c["soundcloud"]))
            if c.get("youtube") and not re.fullmatch(r"[A-Za-z0-9_-]{11}", c["youtube"]):
                errors.append("contents.json #%s: YouTube の動画 ID（11 文字）ではない: %r" % (cid, c["youtube"]))
            for k in ("yt_title", "yt_lead", "excerpt"):
                if k in c and not isinstance(c[k], str):
                    errors.append("contents.json #%s: %s は文字列" % (cid, k))
            if ("yt_title" in c or "yt_lead" in c) and not (c.get("youtube") and c.get("status") == "published"):
                # 公開前の動画（限定公開など）の題と説明文を、公開の repo に入れないため
                errors.append("contents.json #%s: yt_title・yt_lead は youtube があって公開（published）の項目だけ（tools/import_youtube.py が書く）" % cid)
            if "device" in c and not (isinstance(c["device"], list) and all(isinstance(x, (str, int)) for x in c["device"])):
                errors.append("contents.json #%s: device は商品 ID の並び（[\"2\"] など）" % cid)
            if c.get("related"):
                errors.append("contents.json #%s: related（旧版の関連コンテンツ）は改訂版では出さない。回なら episode、番組の第 0 回なら prologue にする" % cid)
            if c.get("article") and not c.get("episode") and not c.get("prologue"):
                errors.append("contents.json #%s: 記事（article）は回（episode）か第 0 回（prologue）に入れる（回を決めていないと回のページと記事の住所が重なる）" % cid)
            if c.get("prologue") and c.get("kind") != "mag":
                errors.append("contents.json #%s: prologue（番組の第 0 回）は読み物（mag）だけ" % cid)
            if c.get("prologue") and (c.get("episode") or c.get("related")):
                errors.append("contents.json #%s: prologue（番組の第 0 回）は回にも関連にも入れない（episode・related を外す）" % cid)
            if c.get("kind") == "mag" and c.get("badge") and c.get("status") == "published" and c["badge"] not in self.site.get("views", {}):
                errors.append("contents.json #%s: site.json の views に「%s」の一言が無い（見方のカードに出す）" % (cid, c["badge"]))
            if c.get("portrait_focus") and not re.fullmatch(r"\d{1,3}% \d{1,3}%", c["portrait_focus"]):
                errors.append("contents.json #%s: portrait_focus は \"68%% 50%%\" の形で書く" % cid)
            hero = c.get("hero", [])
            if not (isinstance(hero, list) and all(isinstance(x, str) for x in hero)):
                errors.append("contents.json #%s: hero は写真の名前の並び（[\"photo-1.jpg\", …]）" % cid)
                hero = []
            if c.get("portrait") and not (c.get("portrait_alt") or "").strip():
                errors.append("contents.json #%s: portrait を出すなら、写真の説明 portrait_alt も書く" % cid)
            for name in hero + ([c["portrait"]] if c.get("portrait") else []):
                if not re.fullmatch(IMAGE_NAME, name):
                    errors.append("contents.json #%s: 写真の名前は英数字・-・_ と拡張子だけ（assets/ の直下）: %r" % (cid, name))
                elif not os.path.exists(os.path.join(ROOT, "assets", name)):
                    errors.append("contents.json #%s: assets/%s が無い（hero / portrait）" % (cid, name))
            if c.get("article") and not os.path.exists(os.path.join(SRC, c["article"])):
                errors.append("contents.json #%s: 記事のファイルが無い: src/%s" % (cid, c["article"]))
            elif c.get("article"):
                with open(os.path.join(SRC, c["article"]), encoding="utf-8") as f:
                    if not article_text(f.read()):
                        errors.append("contents.json #%s: src/%s から本文（class に article-body を持つ div の中の <p>）が取れない"
                                      "（Magazine の抜き出しに使う）" % (cid, c["article"]))
        shops = set(s["match"] for s in self.site["shops"])
        for s_ in self.site["shops"]:
            if not re.fullmatch(SLUG, s_.get("slug", "")):
                errors.append("site.json shops: slug は英小文字・数字・ハイフンだけ: %r" % s_.get("slug"))
        prod_ids = set()
        for prod in self.device["products"]:
            if not re.fullmatch(r"[0-9A-Za-z_-]+", str(prod.get("id", ""))):
                errors.append("device.json: 商品 ID の形が違う: %r" % prod.get("id"))
            if prod.get("id") in prod_ids:
                errors.append("device.json: 商品 ID が重複: %r" % prod.get("id"))
            prod_ids.add(prod.get("id"))
            if not prod.get("variants"):
                errors.append("device.json %s: 色違い（販売価格のある行）が 1 つも無い" % prod["name"])
            if prod["shop"] not in shops:
                errors.append("device.json %s: site.json の shops に無いお店: %r" % (prod["name"], prod["shop"]))
            images = [v.get("image") for v in prod["variants"]] + [f.get("image") for f in prod["features"]]
            for img in images:
                if not img:
                    errors.append("device.json %s: 画像の名前が空" % prod["name"])
                elif "/" in img or img.startswith("."):
                    errors.append("device.json %s: 画像はファイル名だけを書く: %r" % (prod["name"], img))
                elif not os.path.exists(os.path.join(ROOT, "assets", "device", img)):
                    errors.append("device.json %s: assets/device/%s が無い（Drive から置く）" % (prod["name"], img))
            for v in prod["variants"]:
                if not isinstance(v.get("price"), int):
                    errors.append("device.json %s（%s）: 販売価格が数字でない: %r" % (prod["name"], v.get("color"), v.get("price")))
        for c in self.contents:
            for pid in c.get("device", []) if isinstance(c.get("device"), list) else []:
                if str(pid) not in set(str(x) for x in prod_ids):
                    errors.append("contents.json #%s: device.json に無い商品 ID: %r" % (c.get("id"), pid))
        for p in self.programs:
            pro = [c["id"] for c in self.contents if c.get("program") == p["slug"] and c.get("prologue")]
            if len(pro) > 1:
                errors.append("programs.json %s: 第 0 回（prologue）が 2 つ以上ある: %s" % (p["slug"], ", ".join(pro)))
            if p.get("related"):
                errors.append("programs.json %s: related（旧版の関連コンテンツ）は改訂版では出さない" % p["slug"])
            for e in p.get("episodes", []):
                if re.fullmatch(r"\d+-\d+-\d+", e.get("key", "")):
                    errors.append("programs.json %s: 回の key に番号の形（%s）は使わない（記事の住所と重なる）" % (p["slug"], e["key"]))
        for g in self.site.get("gates", []):
            if not re.fullmatch(SLUG, g.get("key", "")):
                errors.append("site.json gates: key は英小文字・数字・ハイフンだけ（class の名前に使う）: %r" % g.get("key"))
            for k in ("name", "short", "ja", "url"):
                if not isinstance(g.get(k), str) or not g[k].strip():
                    errors.append("site.json gates %s: %s（文字）が要る" % (g.get("key"), k))
            for k in ("plain", "state"):
                if k in g and not isinstance(g[k], str):
                    errors.append("site.json gates %s: %s は文字" % (g.get("key"), k))
        if not isinstance(self.site.get("views", {}), dict) or not all(isinstance(v, str) for v in self.site.get("views", {}).values()):
            errors.append("site.json views: 見方の一言は文字（{\"随想記事\": \"…\"}）")
        for c in self.contents:
            if "words" in c and not isinstance(c["words"], str):
                errors.append("contents.json #%s: words（書き手）は文字" % c.get("id"))
        ids = set(c.get("id") for c in self.contents)
        for p in self.programs:
            rel = p.get("related", [])
            if not (isinstance(rel, list) and all(isinstance(x, str) for x in rel)):
                errors.append("programs.json %s: related はコンテンツの番号の並び（[\"2-1-2\"] など）" % p.get("slug"))
                continue
            if len(set(rel)) != len(rel):
                errors.append("programs.json %s: related に同じ番号が 2 回ある" % p.get("slug"))
            for cid in rel:
                if cid not in ids:
                    errors.append("programs.json %s: related の番号が contents.json に無い: %r" % (p.get("slug"), cid))
                elif any(c.get("id") == cid and c.get("program") == p.get("slug") for c in self.contents):
                    errors.append("programs.json %s: related の %s は同じ番組のもの（同じ番組なら contents.json で related: true にする）" % (p.get("slug"), cid))
        for f in self.company.get("facilities", []):
            items = f.get("items", []) if isinstance(f, dict) else []
            if not isinstance(items, list):
                errors.append("company.json facilities %r: items は施設の並び（[] でもよい）" % (f.get("name"),))
                items = []
            for x in [f] + items:
                if not isinstance(x, dict) or not isinstance(x.get("name"), str) or not x["name"].strip():
                    errors.append("company.json facilities: 施設は {\"name\": …, \"url\": …} の形で書く: %r" % (x,))
                elif x.get("url") and not (isinstance(x["url"], str) and re.fullmatch(r"https?://[^\s\"<>]+", x["url"])):
                    errors.append("company.json facilities %s: url は http(s):// で始める: %r" % (x["name"], x["url"]))
        for n in self.site.get("news", []):
            if not isinstance(n.get("title"), str) or not n["title"].strip():
                errors.append("site.json news: title（文字）が要る: %r" % (n,))
            if bad_date(n.get("date")):
                errors.append("site.json news %r: date は実在する YYYY-MM-DD: %r" % (n.get("title"), n.get("date")))
        photo = self.company.get("photo", {}).get("src")
        if photo and not os.path.exists(os.path.join(ROOT, "assets", photo)):
            errors.append("company.json: assets/%s が無い" % photo)
        self.validate_lab(errors)
        # 回と道具の要素の札（Lab の要素の key）。付けるかどうかはまなか側が決める（無ければ札は出ない）
        el_keys = set(e.get("key") for e in self.lab.get("elements", []))
        for p_ in self.programs:
            for e in p_.get("episodes", []):
                for k in e.get("elements", []):
                    if k not in el_keys:
                        errors.append("programs.json %s の回 %s: lab.json に無い要素: %r" % (p_["slug"], e.get("key"), k))
        for prod in self.device["products"]:
            for k in prod.get("elements", []):
                if k not in el_keys:
                    errors.append("device.json %s: lab.json に無い要素: %r" % (prod.get("name"), k))
        if errors:
            raise SystemExit("データに問題があります:\n  " + "\n  ".join(errors))

    def validate_lab(self, errors):
        """Lab の試作データ（src/lab.json）。引用の一節が MA Notion の本文に無ければ止める（MA Notion を軸にする決まり）。"""
        lab = self.lab
        shape = {"version": str, "intro": list, "rule": dict, "poles": dict, "forms": list, "doors": dict,
                 "elements": list, "terms": list, "references": list, "research": list}
        for k, typ in shape.items():
            if not isinstance(lab.get(k), typ):
                errors.append("lab.json: %s が無いか、形が違う（%s）" % (k, typ.__name__))
        if any(not isinstance(lab.get(k), typ) for k, typ in shape.items()):
            return  # 形が崩れていると以下の検査自体ができない
        chapters = set(c["no"] for c in self.manifesto["chapters"])
        forms = set(lab["forms"])

        def need(kind, name, it, keys, lists=(), optional=()):
            """必須の項目が、空でない文字列（lists は文字列の並び。optional は書くなら文字列の並び）で入っているか。"""
            ok = True
            if not isinstance(it, dict):
                errors.append("lab.json %s: 項目が {} の形でない: %r" % (kind, it))
                return False
            for k in keys:
                if not isinstance(it.get(k), str) or not it[k].strip():
                    errors.append("lab.json %s %s: %s が無いか、文字列でない" % (kind, name, k))
                    ok = False
            for k in lists:
                if k not in it:
                    errors.append("lab.json %s %s: %s（文字列の並び）が無い" % (kind, name, k))
                    ok = False
            for k in tuple(lists) + tuple(optional):
                v = it.get(k, [])
                if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                    errors.append("lab.json %s %s: %s は文字列の並びで書く" % (kind, name, k))
                    ok = False
            return ok

        for key in ("dictionary", "reference", "research"):
            info = lab.get("doors", {}).get(key)
            if not isinstance(info, dict) or not need("doors", key, info, ("ja", "role")):
                errors.append("lab.json doors: %s に ja と role を書く" % key)
        if not all(isinstance(x, dict) for x in lab["elements"] + lab["terms"] + lab["references"] + lab["research"]):
            errors.append("lab.json: elements / terms / references / research の各項目は {} の形で書く")
            return
        ekeys = set()
        for e in lab["elements"]:
            if not re.fullmatch(SLUG, e.get("key", "")):
                errors.append("lab.json elements: key は英小文字・数字・ハイフンだけ: %r" % e.get("key"))
            if e.get("key") in ekeys:
                errors.append("lab.json elements: key が重複: %s" % e["key"])
            ekeys.add(e.get("key"))
            if need("elements", e.get("key"), e, ("name", "sub", "mitsu", "ma"), ("acts",), ("guess",)) and len(e["name"]) > LAB_NAME_MAX:
                errors.append("lab.json elements %s: name は %d 字まで（地図の札に入れるため）: %r" % (e["key"], LAB_NAME_MAX, e["name"]))
            if any(g not in ("mitsu", "ma") for g in e.get("guess", [])):
                errors.append("lab.json elements %s: guess（本文に無い見立ての印）は mitsu / ma のどれか" % e.get("key"))
        keys = set()
        for t in lab["terms"]:
            if not re.fullmatch(SLUG, t.get("key", "")):
                errors.append("lab.json terms: key は英小文字・数字・ハイフンだけ: %r" % t.get("key"))
            if t.get("key") in keys:
                errors.append("lab.json terms: key が重複: %s" % t["key"])
            keys.add(t.get("key"))
            need("terms", t.get("key"), t, ("word", "reading", "kind", "gloss", "sense", "question"), ("onomatopoeia", "related", "elements"), ("acts",))
        ids = set()
        for r in lab["references"]:
            if not re.fullmatch(SLUG, r.get("id", "")):
                errors.append("lab.json references: id は英小文字・数字・ハイフンだけ: %r" % r.get("id"))
            if r.get("id") in ids:
                errors.append("lab.json references: id が重複: %s" % r["id"])
            ids.add(r.get("id"))
            if need("references", r.get("id"), r, ("form", "field", "title", "creator", "why", "question", "status"), ("terms", "elements")) \
                    and not r["elements"] and r.get("status") != "相談中":
                errors.append("lab.json %s: どの要素が映っているか（elements）を 1 つ以上書く（決めていないなら status を 相談中 に）" % r["id"])
            if not isinstance(r.get("year", ""), str) or not isinstance(r.get("note", ""), str):
                errors.append("lab.json %s: year と note は文字列で書く（年だけでも \"1971\" のように）" % r.get("id"))
            if r.get("form") not in forms:
                errors.append("lab.json %s: form は forms のどれか: %r" % (r.get("id"), r.get("form")))
            if type(r.get("pole")) is not int or not 0 <= r["pole"] <= 100:
                errors.append("lab.json %s: pole は 0（密）〜100（間）の整数: %r" % (r.get("id"), r.get("pole")))
            if r.get("status") not in LAB_STATUS:
                errors.append("lab.json %s: status は %s のどれか: %r" % (r.get("id"), "・".join(LAB_STATUS), r.get("status")))
        for rs in lab["research"]:
            if not re.fullmatch(SLUG, rs.get("id", "")):
                errors.append("lab.json research: id は英小文字・数字・ハイフンだけ: %r" % rs.get("id"))
            if rs.get("id") in ids:
                errors.append("lab.json research: id が資料と重複: %s" % rs["id"])
            ids.add(rs.get("id"))
            need("research", rs.get("id"), rs, ("theme",), ("terms", "lines", "elements"))
            if rs.get("status") not in STATUS:
                errors.append("lab.json research %s: status は published / editing / planned のどれか: %r" % (rs.get("id"), rs.get("status")))
        acts = set(a for t in lab["terms"] for a in t.get("acts", []))
        used = set()
        for kind in ("elements", "terms", "references", "research"):
            for it in lab[kind]:
                name = it.get("key") or it.get("id")
                for k in list(it.get("terms", [])) + list(it.get("related", [])):
                    if k not in keys:
                        errors.append("lab.json %s %s: 用語集（terms）に無い key: %r" % (kind, name, k))
                for k in it.get("elements", []):
                    if k not in ekeys:
                        errors.append("lab.json %s %s: 要素（elements）に無い key: %r" % (kind, name, k))
                    elif kind == "references":
                        used.add(k)
                if kind == "elements":
                    for a in it.get("acts", []):
                        if a not in acts:
                            errors.append("lab.json elements %s: acts は MA Notion の羅列（用語の acts）にある語だけ: %r" % (name, a))
                if type(it.get("ch")) is not int or it["ch"] not in chapters:
                    errors.append("lab.json %s %s: ch は MA Notion の章番号（整数）: %r" % (kind, name, it.get("ch")))
                elif not isinstance(it.get("quote"), str) or len(it["quote"].strip()) < LAB_QUOTE_MIN:
                    errors.append("lab.json %s %s: quote は %d 字以上の一節を写す" % (kind, name, LAB_QUOTE_MIN))
                elif it["quote"] not in self.chapter_text(it["ch"]):
                    errors.append("lab.json %s %s: quote が第 %s 章の本文に見つからない（一字一句そのまま写す）" % (kind, name, it["ch"]))
        for k in ekeys - used:
            errors.append("lab.json elements %s: この要素が映っている資料が 1 つも無い（地図に線が出ない）" % k)

    # ---------- データのまとめ ----------

    def program(self, slug):
        for p in self.programs:
            if p["slug"] == slug:
                return p
        raise SystemExit("contents.json に未登録の番組: %s" % slug)

    def gate(self, key):
        for g in self.site["gates"]:
            if g["key"] == key:
                return g
        raise SystemExit("site.json に無い Gate: %s" % key)

    def shop_of(self, prod):
        for s in self.site["shops"]:
            if s["match"] == prod["shop"]:
                return s
        raise SystemExit("site.json に無いお店: %s" % prod["shop"])

    def item_url(self, item):
        return "channel/%s/%s/" % (item["program"], item["id"])

    def product_url(self, prod):
        return "do/device/%s/%s/" % (self.shop_of(prod)["slug"], prod["id"])

    def item_date(self, item):
        """コンテンツの日付。無ければ、その回（programs.json の episodes）の日付を引き継ぐ。"""
        if item.get("date"):
            return item["date"]
        for p in self.programs:
            for e in p.get("episodes", []):
                if e["key"] == item.get("episode") and p["slug"] == item["program"]:
                    return e.get("date", "")
        return ""

    def latest_key(self, item):
        """公開済みを先に、その中は日付の新しい順・番号の大きい順。"""
        date = int((self.item_date(item) or "0").replace("-", ""))
        return (0 if item.get("status") == "published" else 1, -date, [-x for x in id_key(item)])

    def episodes(self, p):
        """番組の回ごとに、その回のコンテンツをまとめる。回を決めていないコンテンツは 1 件で 1 回とする。"""
        out = []
        mine = [c for c in self.contents if c["program"] == p["slug"] and not c.get("related") and not c.get("prologue")]
        for e in p.get("episodes", []):
            items = sorted((c for c in mine if c.get("episode") == e["key"]),
                           key=lambda c: (KIND_ORDER[c["kind"]], id_key(c)))
            out.append((e, items))
        for c in sorted(mine, key=id_key):
            if not c.get("episode"):
                out.append((self.solo_episode(c), [c]))
        return out

    def yt_item(self, items):
        """回の TV のうち、YouTube の題を取り込んだもの（tools/import_youtube.py）。回の題と一言はこれに合わせる。"""
        for c in items:
            if c["kind"] == "tv" and c.get("status") == "published" and c.get("yt_title"):
                return c
        return None

    def ep_title(self, e, items):
        """回の見出し。YouTube の題に揃えるが、頭の管理番号（「MA Channel #2.1.2 」）は画面に出さない
        （題は import_youtube.py がいつも YouTube から写し直すので、データでなくここで外す）。"""
        tv = self.yt_item(items)
        title = tv["yt_title"] if tv else e["title"]
        return drop_code(title) or title

    def ep_lines(self, e, items):
        """回の一言（行の並び）。YouTube の説明文の冒頭があればそれ、無ければ caption と text。"""
        tv = self.yt_item(items)
        if tv and tv.get("yt_lead"):
            return [x.strip() for x in tv["yt_lead"].split("\n") if x.strip()]
        return [x for x in (e.get("caption"), e.get("text")) if x]

    def find_episode(self, item):
        """コンテンツが入っている回（番組・回・その回のコンテンツ）。"""
        p = self.program(item["program"])
        for e, items in self.episodes(p):
            if item in items:
                return p, e, items
        return p, self.solo_episode(item), [item]

    def solo_episode(self, c):
        """回を決めていないコンテンツは、1 件で 1 回として扱う。"""
        return {"key": c["id"], "title": c["title"], "caption": c.get("caption", ""), "text": "", "date": c.get("date", "")}

    def numbered(self, p):
        """番組の回に番号を付けたもの（#1 から。並びは programs.json の順で、回を決めていないコンテンツはその後）。"""
        return [(i + 1, e, items) for i, (e, items) in enumerate(self.episodes(p))]

    def number_of(self, p, e):
        for n, e2, _ in self.numbered(p):
            if e2["key"] == e["key"]:
                return n
        return 0

    def prologue(self, p):
        """番組の第 0 回（企画背景）。回ではなく番組に属する読み物（contents.json の prologue: true）。"""
        return [c for c in self.contents if c["program"] == p["slug"] and c.get("prologue")]

    def episode_url(self, p, e):
        return "channel/%s/%s/" % (p["slug"], e["key"])

    def ep_name(self, e):
        """カードで使う短い呼び名（題の後ろの括弧書きを外す。例「仁科 正史 (Pro Snowboarder/Artist)」→「仁科 正史」）。"""
        return re.sub(r"\s*[(（][^()（）]*[)）]\s*$", "", e["title"]).strip() or e["title"]

    def ep_label(self, n, e):
        return "#%d %s" % (n, self.ep_name(e))

    def is_published(self, items):
        return any(c.get("status") == "published" for c in items)

    def view_label(self, c):
        """見方の呼び名（動画・随想記事・編集後記・音声）。"""
        return c["badge"] if c["kind"] == "mag" and c.get("badge") else VIEW[c["kind"]]

    def view_note(self, c):
        """見方の一言（site.json の views。「いつを、誰の目で」の対にそろえる）。"""
        return self.site.get("views", {}).get(self.view_label(c), "")

    def content(self, cid):
        for c in self.contents:
            if c["id"] == cid:
                return c
        raise SystemExit("contents.json に無い番号: %s" % cid)

    def collect_news(self):
        """新着は回の単位。回ごとにいちばん新しい日付で 1 行にし、あとから足したものは「10/08 編集後記を追加」と添える。"""
        news = []
        for p in self.programs:
            for n, e, items in self.numbered(p):
                by_date = {}
                for c in items:
                    if c.get("status") == "published" and self.item_date(c):
                        by_date.setdefault(self.item_date(c), []).append(c)
                if not by_date:
                    continue
                last = max(by_date)
                added = ""
                if last != min(by_date):
                    added = "%s %sを追加" % (short_date(last)[3:], "・".join(self.view_label(c) for c in by_date[last]))
                news.append({"date": last, "program": p, "episode": e, "n": n, "items": items, "added": added})
        for x in self.site.get("news", []):
            news.append({"date": x["date"], "title": x["title"], "url": x.get("url", ""), "text": x.get("text", "")})
        return sorted(news, key=lambda x: x["date"], reverse=True)

    def is_new(self, date):
        return bool(date) and date in self.new_dates

    # ---------- 共通部品 ----------

    def href(self, cur, target):
        prefix = "../" * cur.count("/")
        if target == "":
            return prefix or "./"
        return prefix + target

    def tag(self, text, variant="a", el="h2", id_=None, m=None):
        """白い札の見出し（デザインの News・Table of Contents など）。"""
        mm = (' data-m="%s"' % m) if m else ""
        return '<%s class="tag tag-%s"%s%s><span%s>%s</span></%s>' % (
            el, variant, (' id="%s"' % id_) if id_ else "", mm, (' data-m="%s-t" data-mt' % m) if m else "", esc(text), el)

    def frame(self, text, el="h2", m=None):
        """白い線で囲んだ見出し（「間を巡る 4 つの門と 8 つの扉」など）。"""
        return '<%s class="frame-label"%s>%s</%s>' % (el, (' data-m="%s"' % m) if m else "", esc(text), el)

    def gate_head(self, g, el="h1"):
        """門のページの見出し: 名前（Lab など）といまの言葉の 2 段。平易な説明は見出しの下の導入文に置く。"""
        state = (' <span class="status">%s</span>' % esc(g["state"])) if g.get("state") else ""
        plain = ('\n    <p class="gh-plain">%s</p>' % esc(g["plain"])) if g.get("plain") else ""
        # 同じ門のページどうしでは、この塊を同じ形・同じ高さで出す（部屋を移っても上が動かない。g-<門> は移るときの動きの目印）
        return ('<div class="gate-head g-%s">\n    <%s class="gh-title" data-m="gh" data-mt><strong>%s</strong>%s</%s>\n'
                '    <p class="gh-sub" data-m="gs" data-mt>%s</p>%s\n  </div>' % (g["key"], el, esc(g["name"]), state, el, esc(g["ja"]), plain))

    def new_badge(self):
        return '<span class="new">&lt;NEW&gt;</span>'

    def status_badge(self, status):
        s = STATUS.get(status, "")
        return ' <span class="status">%s</span>' % s if s else ""

    def viewbox(self, name):
        """assets/illust/<name>.svg の viewBox（手描きの絵の SVG。元は荒井さんの PDF から線をなぞったもの）。"""
        self._vb = getattr(self, "_vb", {})
        if name not in self._vb:
            path = os.path.join(ROOT, "assets", "illust", name + ".svg")
            if not os.path.exists(path):
                raise SystemExit("assets/illust/%s.svg がありません" % name)
            # 取り決め: 先頭の <svg> に viewBox、絵の本体は <symbol id="art">（ページは <use href="…#art"> で呼ぶ）
            text = open(path, encoding="utf-8").read()
            m = re.search(r'<svg\b[^>]*\bviewBox="([^"]+)"', text)
            sym = re.search(r'<symbol\b(?=[^>]*\bid="art")[^>]*\bviewBox="([^"]+)"', text)
            if not m or not sym:
                raise SystemExit("assets/illust/%s.svg: <svg viewBox=…> と <symbol id=\"art\" viewBox=…> が要る（README の「手描きの絵」）" % name)
            if m.group(1) != sym.group(1):
                raise SystemExit("assets/illust/%s.svg: <svg> と <symbol id=\"art\"> の viewBox が違う" % name)
            self._vb[name] = m.group(1)
        return self._vb[name]

    def illust(self, cur, name, cls, m=None):
        """手描きの絵。色はページの文字色（currentColor）なので、灰地では黒線になる。"""
        name = re.sub(r"\.(png|svg)$", "", name)
        return ('<svg class="illust %s" viewBox="%s" aria-hidden="true" focusable="false"%s><use href="%s#art"/></svg>'
                % (cls, self.viewbox(name), (' data-m="%s"' % m) if m else "", self.href(cur, "assets/illust/%s.svg" % name)))

    def logo(self, cur, cls="logo-mark", m=None):
        # 飾りのロゴ（ページの題は別にある）なので、読み上げでは飛ばす
        return '<img class="%s" src="%s" width="496" height="512" alt="" loading="lazy" decoding="async"%s>' % (
            cls, self.href(cur, "assets/logo.png"), (' data-m="%s"' % m) if m else "")

    def header(self, cur):
        h = lambda t: self.href(cur, t)
        tabs = []
        for g in self.site["gates"]:
            active = cur.startswith(g["url"].split("/")[0] + "/")
            # 名札（小）: 上の小さな字に短い一言、白札に名前。いまいる門は黒の塗り（青は押せる印に取っておく）
            tabs.append('<a class="gate-tab gt-%s%s" href="%s"%s><span class="gt-no" data-m="tl-%s" data-mt>%s</span>'
                        '<span class="gt-box" data-m="tb-%s"><span data-m="tt-%s" data-mt>%s</span></span></a>'
                        % (g["key"], " is-active" if active else "", h(g["url"]), ' aria-current="page"' if active else "",
                           g["key"], esc(g["short"]), g["key"], g["key"], esc(g["name"])))
        # サイト名の段はスクロールで流れ、名札の段は上端まで来たら貼り付く（css の .gate-bar）。メニューのボタンは右上に残す
        return """<header class="site-header">
  <a class="site-title" href="{home}" data-m="title" data-mt>{name}</a>
  <button class="menu-btn" type="button" aria-controls="site-menu" aria-expanded="false" aria-label="メニューを開く" data-m="ham">
    <span></span><span></span><span></span>
  </button>
</header>
<nav class="gate-bar" aria-label="主な行き先">
  <div class="gate-tabs">
    {tabs}
  </div>
</nav>

{menu}""".format(home=h(""), name=esc(self.site["name"]), tabs="\n    ".join(tabs), menu=self.menu(cur))

    def menu(self, cur):
        """全体の地図。門は名前と短い一言の 2 段、その下に番組や扉。準備中は灰色で押せない形。"""
        h = lambda t: self.href(cur, t)
        cols = []
        for g in self.site["gates"]:
            state = (' <span class="status">%s</span>' % esc(g["state"])) if g.get("state") else ""
            head = '<a class="mg-head" href="%s"><span class="mg-short">%s</span><strong>%s</strong></a>%s' % (
                h(g["url"]), esc(g["short"]), esc(g["name"]), state)
            rows = []
            if g["key"] == "channel":
                for p in self.programs:
                    soon = "" if any(self.is_published(items) for _, _, items in self.numbered(p)) else self.status_badge("planned")
                    rows.append('<li><a href="%s">%s</a>%s</li>' % (h("channel/%s/" % p["slug"]), esc(p["ja"]), soon))
            else:
                for d in g["doors"]:
                    if d["ready"] and d.get("url"):
                        rows.append('<li><a href="%s">%s</a></li>' % (h(d["url"]), esc(d["en"])))
                    elif not d["ready"]:
                        rows.append('<li class="is-dim">%s%s</li>' % (esc(d["en"]), self.status_badge("planned")))
            ul = ('\n        <ul class="mg-list">\n          %s\n        </ul>' % "\n          ".join(rows)) if rows else ""
            cols.append("""      <div class="menu-gate mg-{key}">
        {head}{ul}
      </div>""".format(key=esc(g["key"]), head=head, ul=ul))
        return """<div class="menu-overlay" id="site-menu" aria-hidden="true">
  <div class="bar">
    <a class="site-title" href="{home}">{name}</a>
    <button class="menu-close" type="button" aria-label="メニューを閉じる"><span></span><span></span></button>
  </div>
  <nav class="menu-inner" aria-label="サイトの案内">
    <a class="menu-home" href="{home}">Home</a>
    <div class="menu-gates">
{cols}
    </div>
    <div class="menu-links"><a href="{contact}">Contact</a><a href="{company}">Company</a></div>
  </nav>
  {figure}
</div>
""".format(home=h(""), name=esc(self.site["name"]), cols="\n".join(cols), contact=h("contact/"), company=h("company/"),
           figure=self.illust(cur, "figure", "menu-figure"))

    def footer(self, cur):
        h = lambda t: self.href(cur, t)
        f = self.site["follow"]
        # 外のサイトは行き先のサービス名と ↗ で呼ぶ（音声は扉の名前 Radio・Podcast ではなく、行き先の SoundCloud）
        links = [(f.get("youtube"), "YouTube"), (f.get("podcast"), "SoundCloud"), (f.get("note"), "note")]
        follow = " ".join('<a href="%s" target="_blank" rel="noopener">%s <span aria-hidden="true">↗</span></a>' % (esc(u), n) for u, n in links if u)
        return """<footer class="site-footer">
  <p class="fc-1"><span class="fc-name" data-m="f1" data-mt>{name}</span> <span class="fc-follow" data-m="f2" data-mt>{follow}</span></p>
  <p class="fc-2" data-m="f3" data-mt>©2026, Manaka Ltd.{beta}</p>
  <button class="theme-toggle" type="button" aria-label="表示の色を切り替える" data-m="toggle">
    <span class="tt-knob"></span><span class="tt-label">Dark</span><span class="tt-icon" aria-hidden="true">☾</span>
  </button>
  <p class="footer-links" data-m="flinks"><a href="{contact}">Contact</a><a href="{company}">Company</a></p>
</footer>
""".format(name=esc(self.site["name"]), follow=follow, beta=("　" + esc(self.site["beta_note"])) if self.site.get("noindex") else "",
           company=h("company/"), contact=h("contact/"))

    def claim(self, cur):
        """同じ住所に 2 つのページを書かない（回のページと記事のページが重なったら止める）。"""
        if cur in self.pages:
            raise SystemExit("同じ住所に 2 つのページを作ろうとした: %s（回の key と記事の番号、回を決めていない記事を確かめる）" % cur)

    def asset_version(self, rel):
        """見た目・動きのファイルの中身の印（中身が変われば変わる）。URL に付けておけば、置き場で長く覚えさせても古いものが残らない。"""
        self._ver = getattr(self, "_ver", {})
        if rel not in self._ver:
            with open(os.path.join(ROOT, rel), "rb") as f:
                self._ver[rel] = hashlib.sha1(f.read()).hexdigest()[:10]
        return self._ver[rel]

    def page(self, cur, title, body, main_class="page", description=None):
        self.claim(cur)
        h = lambda t: self.href(cur, t)
        name = self.site["name"]
        full = name if title is None else "%s | %s" % (title, name)
        desc = description or self.site["description"]
        robots = '\n<meta name="robots" content="noindex, nofollow">' if self.site.get("noindex") else ""
        doc = """<!DOCTYPE html>
{mark}
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{full}</title>{robots}
<script>document.documentElement.classList.add("js");function maTheme(){{try{{document.documentElement.classList.toggle("light",localStorage.getItem("ma-theme")==="light")}}catch(e){{}}}}maTheme();if(document.prerendering)document.addEventListener("prerenderingchange",maTheme,{{once:true}});(function(){{try{{if(!matchMedia("(max-width:359.98px)").matches)return;var d=document.documentElement,z=document.createElement("div");z.style.cssText="position:absolute;visibility:hidden;width:0;height:100vh;zoom:.5";d.appendChild(z);var h=z.getBoundingClientRect().height;z.remove();if(h>0&&h<innerHeight*.75)d.classList.add("zoom-vh")}}catch(e){{}}}})()</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&display=swap" rel="stylesheet">
<meta name="description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{name}">
<meta property="og:title" content="{full}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{touch}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#1414dc">
<link rel="icon" href="{ico}" sizes="any">
<link rel="icon" type="image/png" href="{png}">
<link rel="apple-touch-icon" href="{touch}">
<link rel="stylesheet" href="{css}">
{spec}
</head>
<body>

{header}
<main class="{main_class}" id="main">
{body}
</main>

{footer}
<script src="{js}"></script>
</body>
</html>
""".format(mark=MARK, full=esc(full), robots=robots, desc=esc(desc), name=esc(name),
           touch=h("assets/apple-touch-icon.png"), ico=h("favicon.ico"), png=h("assets/favicon.png"),
           css=h("css/style.css") + "?v=" + self.asset_version("css/style.css"), header=self.header(cur), main_class=main_class, body=body.strip("\n"),
           footer=self.footer(cur), js=h("js/main.js") + "?v=" + self.asset_version("js/main.js"), spec=SPECULATION)
        self.pages[cur] = doc

    def redirect(self, cur, target, label):
        self.claim(cur)
        to = self.href(cur, target)
        self.pages[cur] = """<!DOCTYPE html>
{mark}
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="0; url={to}">
<link rel="canonical" href="{to}">
<meta name="robots" content="noindex">
<title>ページを移動しました | {name}</title>
</head>
<body>
<p><a href="{to}">{label}へ移動する</a></p>
</body>
</html>
""".format(mark=MARK, to=esc(to), name=esc(self.site["name"]), label=esc(label))

    def date_meta(self, date, el="p", m=None):
        """日付の行（<NEW> と日付だけ。管理番号は画面に出さない）。"""
        parts = []
        if self.is_new(date):
            parts.append(self.new_badge())
        if date:
            parts.append('<span class="em-date">%s</span>' % esc(short_date(date)))
        mm = (' data-m="%s" data-mt' % m) if m else ""
        return '<%s class="entry-meta"%s>%s</%s>' % (el, mm, " ".join(parts), el) if parts else ""

    # ---------- 部品（見直し案の 10 個。カードは 1 枚に行き先 1 つ。中に別のリンクを入れない） ----------

    def tv_media(self, item):
        if item.get("youtube") and item.get("status") == "published":
            return ('<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/%s" title="%s（YouTube）" '
                    'loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
                    'picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>'
                    % (esc(item["youtube"]), esc(drop_code(item.get("yt_title")) or item["title"])))
        return '<div class="video video-ph"><span class="play" aria-hidden="true"></span><span class="ph-label">準備中</span></div>'

    def card(self, href, rows, cls, id_=None, soon=False, ext=False):
        """カードの外枠。href があれば枠ごと押せて右下に →（外のサイトへは ↗ で、新しいタブ）、無ければ（準備中）灰色の破線で押せない。"""
        idattr = (' id="%s"' % id_) if id_ else ""
        inner = "\n          ".join(r for r in rows if r)
        if href and not soon:
            return ('      <li class="card %s"%s>\n        <a class="card-link" href="%s"%s>\n          %s\n          '
                    '<span class="card-go" aria-hidden="true">%s</span>\n        </a>\n      </li>'
                    % (cls, idattr, href, ' target="_blank" rel="noopener"' if ext else "", inner, "↗" if ext else "→"))
        return '      <li class="card %s is-soon"%s>\n        <div class="card-body">\n          %s\n        </div>\n      </li>' % (cls, idattr, inner)

    def cards(self, items, cls=""):
        return '<ul class="cards%s">\n%s\n    </ul>' % ((" " + cls) if cls else "", "\n".join(items)) if items else ""

    def program_card(self, cur, p):
        """番組カード: 和題・副題・回の数・最新の回。"""
        eps = self.numbered(p)
        pub = [(n, e) for n, e, items in eps if self.is_published(items)]
        # 数え方は連続ものの言い方（全○回）。回が無い番組は、無いことを言わずに状態（準備中）だけを出す
        if pub:
            n, e = pub[-1]
            meta = esc("全 %d 回｜最新 %s" % (len(pub), self.ep_label(n, e)))
        else:
            meta = self.status_badge("planned").strip()
        return self.card(self.href(cur, "channel/%s/" % p["slug"]), [
            '<span class="card-title">%s</span>' % esc(p["ja"]),
            '<span class="card-note">%s</span>' % esc(p.get("sub", "")) if p.get("sub") else "",
            '<span class="card-meta">%s</span>' % meta,
        ], "card-program")

    def episode_card(self, cur, p, n, e, items, show_program=False, added="", id_=None):
        """回カード: 番組名（ほかの番組と並ぶとき）・#回 人・一言・日付・この回にある見方・あとから足したもの。"""
        pub = [c for c in items if c.get("status") == "published"]
        date = max((self.item_date(c) for c in pub if self.item_date(c)), default="")
        first = min((self.item_date(c) for c in pub if self.item_date(c)), default="")
        note = e.get("caption") or (self.ep_lines(e, items)[:1] or [""])[0]
        views = "・".join(dict.fromkeys(self.view_label(c) for c in sorted(pub, key=lambda c: KIND_ORDER[c["kind"]])))
        meta = " ".join(x for x in (self.new_badge() if self.is_new(date) else "", esc(short_date(first)), esc(views)) if x)
        rows = [
            '<span class="card-kicker">%s</span>' % esc(p["ja"]) if show_program else "",
            '<span class="card-title">%s</span>' % esc(self.ep_label(n, e)),
            '<span class="card-note">%s</span>' % esc(note) if note else "",
            ('<span class="card-meta">%s</span>' % meta) if pub else '<span class="card-meta">%s</span>' % self.status_badge("planned").strip(),
            '<span class="card-update">%s</span>' % esc(added) if added else "",
        ]
        return self.card(self.href(cur, self.episode_url(p, e)) if pub else None, rows, "card-episode", id_=id_, soon=not pub)

    def prologue_card(self, cur, c):
        """第 0 回（企画背景）のカード。記事が公開されていれば記事へ。"""
        pub = c.get("status") == "published" and c.get("article")
        rows = ['<span class="card-title">#0 %s</span>' % esc(self.view_label(c)),
                '<span class="card-note">%s</span>' % esc(c["title"]),
                '<span class="card-meta">%s</span>' % (esc(self.view_note(c)) if pub else self.status_badge(c.get("status")).strip())]
        return self.card(self.href(cur, self.item_url(c)) if pub else None, rows, "card-episode card-prologue", soon=not pub)

    def view_card(self, cur, c, p, e):
        """見方カード: 種類・一言（いつを、誰の目で）・書き手。動画は回のページで再生、記事は記事へ、音声は SoundCloud へ（↗）。"""
        pub = c.get("status") == "published"
        ext = False
        if c["kind"] == "tv":
            href, note = self.href(cur, self.episode_url(p, e)), "この回のページで観る"
        elif c["kind"] == "radio" and c.get("soundcloud"):
            href, note, ext = c["soundcloud"], "SoundCloud で聴く", True
        elif c.get("article"):
            href, note = self.href(cur, self.item_url(c)), self.view_note(c)
        else:
            href, note = None, self.view_note(c)
        rows = ['<span class="card-title">%s</span>' % esc(self.view_label(c)),
                '<span class="card-note">%s</span>' % esc(note) if note else "",
                '<span class="card-meta">Words %s</span>' % esc(c["words"]) if c.get("words") and pub else "",
                '<span class="card-meta">%s</span>' % self.status_badge(c.get("status")).strip() if not pub else ""]
        return self.card(href if pub else None, rows, "card-view", soon=not pub or not href, ext=ext)

    def product_card(self, cur, prod):
        """道具カード（一覧）。枠ごと押せる。「詳細」のボタンは置かない。"""
        shop = self.shop_of(prod)
        v = prod["variants"][0]
        return """      <li class="dev-card" data-shop="{slug}" data-text="{text}">
        <a class="dc-link" href="{url}">
          <span class="dc-img"><img src="{img}" width="720" height="720" loading="lazy" decoding="async" alt=""></span>
          <span class="dc-shop">{shop}</span>
          <span class="dc-name">{name}</span>
          <span class="price">{price}{tax}</span>
          <span class="card-go" aria-hidden="true">→</span>
        </a>
      </li>""".format(slug=esc(shop["slug"]), text=esc(" ".join([prod["name"], prod["shop"], prod["category"], prod["copy"]] + [x["color"] for x in prod["variants"]])),
                       url=self.href(cur, self.product_url(prod)), img=esc(self.href(cur, "assets/device/" + v["image"])), name=esc(prod["name"]),
                       shop=esc(shop["name"]), price=esc(self.price_label(prod)), tax=self.tax_label())

    def next_steps(self, cur, back, nxt=None):
        """次の一歩: 戻る先と次の 2 つだけ。次が準備中なら押せない形で知らせる。"""
        out = ['<a class="ns-back" href="%s"><span aria-hidden="true">←</span> %s</a>' % (self.href(cur, back[0]), esc(back[1]))]
        if nxt and nxt[0]:
            out.append('<a class="ns-next" href="%s">%s <span aria-hidden="true">→</span></a>' % (self.href(cur, nxt[0]), esc(nxt[1])))
        elif nxt:
            out.append('<span class="ns-next is-soon">%s</span>' % esc(nxt[1]))
        return '<nav class="next-steps" aria-label="次へ">%s</nav>' % "".join(out)

    def next_episode(self, p, n):
        """同じ番組の次の回（公開済み）。無ければ、次の回が準備中かどうか。"""
        later = [(m, e, items) for m, e, items in self.numbered(p) if m > n]
        for m, e, items in later:
            if self.is_published(items):
                return (self.episode_url(p, e), "次の回 %s" % self.ep_label(m, e))
        return (None, "次の回は準備中") if later else None

    def element_chips(self, cur, keys, label):
        """要素の札（Lab の要素の欄へ）。まだ付けていなければ出さない（付けるかはまなか側が決める）。"""
        return self.lab_chips(cur, keys, label) if keys else ""

    def section(self, title, body, cls=""):
        return '<section class="sec%s">\n    %s\n    %s\n  </section>' % ((" " + cls) if cls else "", self.tag(title, "t"), body) if body else ""

    # ---------- 各ページ ----------

    def latest_episode(self):
        """動画を公開した回のうち、いちばん新しい回（Home の「最新の回を観る」の行き先）。
        読み物や音声だけ先に出た回は、観るものが無いので選ばない。"""
        for x in self.news:
            if x.get("episode") and any(c["kind"] == "tv" and c.get("status") == "published" for c in x["items"]):
                return x
        return None

    def news_rows(self, cur, limit):
        """新着の並び。回は回カード（番組名つき）、回でないお知らせは題と一言だけ。"""
        rows = []
        for x in self.news[:limit]:
            if x.get("episode"):
                rows.append(self.episode_card(cur, x["program"], x["n"], x["episode"], x["items"], show_program=True, added=x["added"]))
            else:
                link = self.href(cur, x["url"]) if x.get("url") else None
                rows.append(self.card(link, ['<span class="card-meta">%s</span>' % esc(short_date(x["date"])),
                                             '<span class="card-title">%s</span>' % esc(x["title"]),
                                             '<span class="card-note">%s</span>' % esc(x["text"]) if x.get("text") else ""], "card-news"))
        return self.cards(rows)

    def build_home(self):
        cur = "index.html"
        h = lambda t: self.href(cur, t)
        q = self.site["quote"]
        # 引用は掲載が決まるまで欄ごと出さない（空いたままの欄は画面 1 枚分の空白になる）
        quote = ""
        if q.get("lines"):
            quote = """
  <section class="quote col" id="quote" aria-label="引用">
{lines}
    <p class="quote-credit" data-m="credit" data-mt>(-{credit})</p>
  </section>
""".format(lines="\n".join('    <p>%s</p>' % esc(l) for l in q["lines"]), credit=esc(q["credit"]))
        latest = self.latest_episode()
        start = ('<a class="btn-primary" href="%s">最新の回を観る <span aria-hidden="true">→</span></a>' % h(self.episode_url(latest["program"], latest["episode"]))) if latest else ""
        gates = []
        for i, g in enumerate(self.site["gates"]):
            state = (' <span class="status">%s</span>' % esc(g["state"])) if g.get("state") else ""
            head = '<a href="%s"><strong>%s</strong></a> <span class="gh-ja">%s</span>%s' % (h(g["url"]), esc(g["name"]), esc(g["ja"]), state)
            subs = []
            if g["key"] == "channel":
                for p in self.programs:
                    soon = not any(self.is_published(items) for _, _, items in self.numbered(p))
                    subs.append('<li><a href="%s">%s</a>%s</li>' % (h("channel/%s/" % p["slug"]), esc(p["ja"]), self.status_badge("planned") if soon else ""))
            else:
                for d in g["doors"]:
                    if d["ready"] and d.get("url"):
                        subs.append('<li><a href="%s">%s</a></li>' % (h(d["url"]), esc(d["en"])))
                    elif not d["ready"]:
                        subs.append('<li class="is-dim">%s%s</li>' % (esc(d["en"]), self.status_badge("planned")))
            gates.append("""      <li class="toc-gate">
        <p class="toc-head" data-m="g{i}" data-mt>{head}</p>
        <p class="toc-plain">{plain}</p>{subs}
      </li>""".format(i=i, head=head, plain=esc(g.get("plain", "")),
                      subs=('\n        <ul class="toc-doors" data-m="d%d" data-mt>\n          %s\n        </ul>' % (i, "\n          ".join(subs))) if subs else ""))
        body = """
  <h1 class="visually-hidden">{name}</h1>

  <section class="hero" id="top">
    <div class="hero-block">
      <p class="hero-now" data-m="now" data-mt>現在、</p>
      <p class="hero-count" data-m="count"><span class="hc-line" data-m="hcline"></span><span class="hc-num" data-m="hcnum">{visitors}</span></p>
      <p class="hero-text" data-m="htext" data-mt>人が平場に立ちました。</p>
      {figure}
    </div>
  </section>

  <section class="home-start col" aria-label="このサイトについて">
    <p class="home-lead">{desc}</p>
    {start}
    {hiraba}
  </section>
{quote}
  <section class="toc col" id="toc">
    {toc_tag}
    <ol class="toc-gates">
{gates}
    </ol>
  </section>

  <section class="news col" id="news">
    {news_tag}
    {device}
    {news}
  </section>
  <div class="home-end">{homelogo}</div>
""".format(homelogo=self.logo(cur, "home-logo", m="flogo"), name=esc(self.site["name"]), visitors=esc(str(self.site.get("visitors", 1))),
           figure=self.illust(cur, "figure", "hero-figure", m="figure"), desc=esc(self.site["description"]), start=start,
           hiraba=self.illust(cur, "hiraba", "hiraba-illust", m="hiraba"), quote=quote,
           toc_tag=self.tag("間を巡る 4 つの門", "b", m="toctag"), gates="\n".join(gates),
           news_tag=self.tag("News", "t", m="newstag"), device=self.illust(cur, "device", "device-illust", m="device"),
           news=self.news_rows(cur, 3))
        self.page(cur, None, body, main_class="page home-page")

    def fold_chapter(self, no, title, paras, i, label=None):
        """章の開閉（最初は見出しだけ）。章の題そのものが開閉のボタンで、右の ＋ が開く・− が閉じる。本文の最後の − でも閉じる。
        label を渡すとそれを見出しにする（MA Notion は原稿の「0. 真面目な提案」の形）。無ければ「第 n 章 : 「題」」。"""
        return """    <section class="fold chapter is-folded" id="ch{no}">
      <h2 class="fold-head"><button class="fold-toggle" type="button" aria-expanded="false" aria-controls="ch{no}-body"><span class="ft-title" data-m="ch{i}" data-mt>{label}</span><span class="ft-sign" aria-hidden="true"></span></button></h2>
      <div class="fold-body prose" id="ch{no}-body">
{paras}
        <p class="fold-end"><button class="fold-close" type="button" aria-controls="ch{no}-body" aria-label="「{title}」を閉じる"></button></p>
      </div>
    </section>""".format(no=no, title=esc(title), label=esc(label or "第 %s 章 : 「%s」" % (no, title)), paras="\n".join(paras), i=i)

    def build_notion(self):
        cur = "notion/index.html"
        m = self.manifesto
        n = self.site["notion"]
        chapters = []
        for i, c in enumerate(m["chapters"]):
            out = []
            for p in c["paragraphs"]:
                if isinstance(p, dict):
                    out.append('        <div class="manifesto-box">\n%s\n        </div>'
                               % "\n".join("          <p>%s</p>" % esc(l) for l in p["box"]))
                else:
                    out += ['        <p>%s</p>' % esc(l.strip()) for l in p.split("\n") if l.strip()]
            chapters.append(self.fold_chapter(c["no"], c["title"], out, i, label=c["heading"]))
        core, steps = n["core"], n["steps"]
        flow = []
        for i, st in enumerate(steps["flow"]):
            flow.append("""        <li class="flow-step fs-{i}">
          <div class="flow-box"><span><strong>{en}</strong> <span class="flow-ja">({ja})</span></span><span>“{verb}”</span></div>
          <ul class="flow-doors">{doors}</ul>
        </li>""".format(i=i, gate=esc(st["gate"]), en=esc(st["en"]), ja=esc(st["ja"]), verb=esc(st["verb"]),
                        doors="".join("<li>%s</li>" % esc(d) for d in st["doors"])))
        cap = core["caption"]
        body = """
  {logo}
  <div class="content notion">
    {head}

    <div class="chapters">
{chapters}
    </div>

    <section class="notion-part core" id="core">
      {core_label}
      <p class="part-heading" data-m="coreh" data-mt>{core_heading}</p>
      <p class="part-text" data-m="coret" data-mt>{core_lines}</p>
      <figure class="spectrum" aria-label="密と間の対比" data-m="spec">
        <span class="sp-name sp-mitsu">密</span><span class="sp-name sp-ma">間</span>
        <img class="dots dots-dense" src="{dense}" width="67" height="87" alt="" decoding="async"><img class="dots dots-sparse" src="{sparse}" width="91" height="98" alt="" decoding="async">
        <span class="sp-mid">論理 ⇄ 感覚</span><em class="sp-word">spectrum</em>
        <figcaption>{cap0}<br>{cap1}<br>{cap2}</figcaption>
      </figure>
    </section>

    <section class="notion-part steps" id="steps">
      {steps_label}
      <p class="part-text" data-m="stept" data-mt>{steps_lines}</p>
      <figure class="flow" aria-label="間を定める、広める、感化する" data-m="flow">
        <div class="flow-root">間｜MA<br>暮らしへの<br>インストール</div>
        <ol class="flow-steps">
{flow}
        </ol>
      </figure>
      {book}
    </section>
    <p class="formula formula-notion" data-m="formula"><span class="fm-left" data-m="fml" data-mt>We create of Your MA <span class="fm-eq">=</span></span><span class="fm-frac"><span class="fm-num" data-m="fmn" data-mt>Lab × Ch × Do</span><span class="fm-bar" aria-hidden="true"></span><span class="fm-den" data-m="fmd" data-mt>Notion</span></span></p>
  </div>
""".format(logo=self.logo(cur, "logo-mark lm-notion", m="lmn"), head=self.gate_head(self.gate("notion")),
           chapters="\n\n".join(chapters), core_label=self.frame(core["label"], m="corel"), core_heading=esc(core["heading"]),
           core_lines=brs(core["lines"]), dense=self.href(cur, "assets/figures/dots-dense.svg"), sparse=self.href(cur, "assets/figures/dots-sparse.svg"), cap0=esc(cap[0]), cap1=esc(cap[1]), cap2=esc(cap[2]),
           steps_label=self.frame(steps["label"], m="stepl"), steps_lines=brs(steps["lines"]),
           flow="\n".join(flow), book=self.illust(cur, "book", "book-illust", m="book"))
        self.page(cur, "Notion", body)

    # ---------- Lab（試作） ----------

    def ch_label(self, no):
        """章の呼び名。MA Notion の見出しと同じ「0. 真面目な提案」の形（10/22 まなかの指示）。"""
        for c in self.manifesto["chapters"]:
            if c["no"] == no:
                return c["heading"]
        return "%d." % no

    def chapter_text(self, no):
        """MA Notion の章の本文を一つの文字列に（引用の一節がそこにあるかを確かめる用）。"""
        for c in self.manifesto["chapters"]:
            if c["no"] == no:
                return "\n".join(("\n".join(p["box"]) if isinstance(p, dict) else p) for p in c["paragraphs"])
        return ""

    def lab_term(self, key):
        return [t for t in self.lab["terms"] if t["key"] == key][0]

    def lab_element(self, key):
        return [e for e in self.lab["elements"] if e["key"] == key][0]

    def lab_chips(self, cur, keys, label="要素"):
        """要素（Lab の入口の要素の欄へ飛ぶ）。丸い札は絞り込みだけに使うので、ここは文中のリンクと同じ下線の文字にする。"""
        if not keys:
            return '<p class="chips"><span class="chips-label">%s：</span><span class="chip-none">まだ決めていない</span></p>' % esc(label)
        chips = "・".join('<a class="chip" href="%s">%s</a>' % (self.href(cur, "lab/#e-%s" % k), esc(self.lab_element(k)["name"])) for k in keys)
        return '<p class="chips"><span class="chips-label">%s：</span>%s</p>' % (esc(label), chips)

    def local_nav(self, cur, g, here):
        """扉の帯（門の中の道案内）。門の見出しのすぐ下に横 1 段で、いまいる所は太字＋下線（aria-current）。
        門の入口が扉と同じ住所（Do の入口＝Device）なら「入口」は出さない。開いていない扉は灰色で押せない。
        here の下のページ（商品ページなど）では、その扉を「いまいる所」として示す。"""
        items = [] if g["url"] in [d.get("url") for d in g["doors"]] else [(g["url"], "入口", True)]
        # 開いている扉を先に、準備中は後ろに（並びの中は site.json の順）
        doors = [(d.get("url"), d["en"], bool(d["ready"] and d.get("url"))) for d in g["doors"]]
        items += [x for x in doors if x[2]] + [x for x in doors if not x[2]]
        lis = []
        for url, label, ok in items:
            if not ok:
                lis.append('<li class="is-dim">%s%s</li>' % (esc(label), self.status_badge("planned")))
                continue
            cur_attr, bar = "", ""
            if url == here:
                cur_attr = ' aria-current="page"'
            elif label != "入口" and here.startswith(url):
                cur_attr = ' aria-current="true"'
            if cur_attr:
                bar = '<span class="ln-bar" aria-hidden="true"></span>'  # いまいる所の下線。部屋を移ると横へ滑って移る（css の view-transition）
            lis.append('<li><a href="%s"%s data-label="%s">%s%s</a></li>' % (self.href(cur, url), cur_attr, esc(label), esc(label), bar))
        return '<nav class="local-nav ln-%s" aria-label="%s の部屋"><ul>%s</ul></nav>' % (g["key"], esc(g["name"]), "".join(lis))

    def lab_glyph(self, form):
        return '<span class="fg" aria-hidden="true">%s</span>' % esc(LAB_GLYPH.get(form, "■"))

    def lab_flow(self, cur):
        """要素の地図（流れの図）。間 → MA Notion の章 → 要素 → 部屋（Dictionary・Reference・Research）。
        帯の太さは、その要素が映っている言葉・資料・テーマの数。PC は 4 列、スマホは 要素 → 部屋 の 2 列（章はまとまりの見出し）。
        JS 無しでも出る。名前に乗せると、そこにつながる帯だけが濃くなる（js/main.js）。"""
        lab = self.lab
        h = lambda t: self.href(cur, t)
        rooms = [("dictionary", "Dictionary", "語", lab["terms"]), ("reference", "Reference", "点", lab["references"]),
                 ("research", "Research", "テーマ", lab["research"])]
        chapters = self.manifesto["chapters"]
        order = sorted(lab["elements"], key=lambda e: (e["ch"], lab["elements"].index(e)))
        val = {e["key"]: [sum(1 for x in items if e["key"] in x.get("elements", [])) for _, _, _, items in rooms] for e in order}
        etot = {k: sum(v) for k, v in val.items()}
        ctot = {c["no"]: sum(etot[e["key"]] for e in order if e["ch"] == c["no"]) for c in chapters}
        rtot = [sum(val[k][i] for k in val) for i in range(len(rooms))]
        total = sum(etot.values())
        if not total:  # どの要素にも何もつながっていなければ、図は出さない
            return "", "まだ、要素につながる言葉・資料・テーマが無い。"

        def stack(items, k, gap, top=0.0, minh=2.0, heads=None):
            """縦に積む。items=[(key, value)]。heads={key: 見出しの高さ}（その前に見出しの空きを取る）。"""
            out, y = {}, top
            for key, v in items:
                y += (heads or {}).get(key, 0)
                hgt = max(v * k, minh)
                out[key] = [y, y + hgt]
                y += hgt + gap
            return out, y - gap

        def ribbon(x0, a0, a1, x1, b0, b1):
            xm = (x0 + x1) / 2
            return ("M%.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1fL%.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1fZ"
                    % (x0, a0, xm, a0, xm, b0, x1, b0, x1, b1, xm, b1, xm, a1, x0, a1))

        def rib(d, **data):
            attrs = "".join(' data-%s="%s"' % (k, esc(str(v))) for k, v in data.items())
            return '<path class="rib" d="%s"%s/>' % (d, attrs)

        def node(x, y0, y1, w, empty=False):
            return '<rect class="node%s" x="%.1f" y="%.1f" width="%d" height="%.1f"/>' % (" is-empty" if empty else "", x, y0, w, max(y1 - y0, 1))

        def link(href, focus, inner, label):
            return '<a href="%s" data-focus="%s" aria-label="%s">%s</a>' % (href, focus, esc(label), inner)

        room_href = [h("lab/%s/" % r) for r, _, _, _ in rooms]
        # ---------- PC（間 → 章 → 要素 → 部屋） ----------
        W, H, w = 990, 540, 10
        xA, xB, xC, xD = 58, 250, 560, 860
        # いちばん隙間を取る列が高さ H にちょうど収まる太さ（要素・章・部屋のどの列も H の中に入る）
        k = (H - max((len(order) - 1) * 12, (len(chapters) - 1) * 28, (len(rooms) - 1) * 34)) / total
        def centered(items, gap, minh=2.0):
            _, end = stack(items, k, gap, 0, minh)
            return stack(items, k, gap, (H - end) / 2, minh)[0]
        nA = centered([("ma", total)], 0)
        nB = centered([(c["no"], ctot[c["no"]]) for c in chapters], 28)
        nC = centered([(e["key"], etot[e["key"]]) for e in order], 12)
        nD = centered([(i, rtot[i]) for i in range(len(rooms))], 34)
        ribs, labels = [], []
        ya = nA["ma"][0]
        for c in chapters:  # 間 → 章
            v = ctot[c["no"]] * k
            if v:
                b0 = nB[c["no"]][0]
                ribs.append(rib(ribbon(xA + w, ya, ya + v, xB, b0, b0 + v), ch=c["no"]))
                ya += v
        cur_b = {c["no"]: nB[c["no"]][0] for c in chapters}
        cur_c_in = {e["key"]: nC[e["key"]][0] for e in order}
        for e in order:  # 章 → 要素
            v = etot[e["key"]] * k
            b0 = cur_b[e["ch"]]
            c0 = cur_c_in[e["key"]]
            ribs.append(rib(ribbon(xB + w, b0, b0 + v, xC, c0, c0 + v), ch=e["ch"], el=e["key"]))
            cur_b[e["ch"]] += v
        cur_d = {i: nD[i][0] for i in range(len(rooms))}
        for e in order:  # 要素 → 部屋
            c0 = nC[e["key"]][0]
            for i in range(len(rooms)):
                v = val[e["key"]][i] * k
                if not v:
                    continue
                d0 = cur_d[i]
                ribs.append(rib(ribbon(xC + w, c0, c0 + v, xD, d0, d0 + v), ch=e["ch"], el=e["key"], room=rooms[i][0]))
                c0 += v
                cur_d[i] += v
        nodes = [node(xA, *nA["ma"], w)] + [node(xB, *nB[c["no"]], w, empty=not ctot[c["no"]]) for c in chapters] + \
                [node(xC, *nC[e["key"]], w) for e in order] + [node(xD, *nD[i], w) for i in range(len(rooms))]
        mid = lambda r: (r[0] + r[1]) / 2
        labels.append('<text class="t-fg t-ma" x="%d" y="%.1f" text-anchor="end" dominant-baseline="central">間</text>' % (xA - 12, mid(nA["ma"])))
        for c in chapters:
            y = mid(nB[c["no"]])
            text = '<text x="%d" y="%.1f" dominant-baseline="central">%s</text>' % (xB + w + 8, y, esc(self.ch_label(c["no"])))
            if ctot[c["no"]]:
                labels.append(link(h("notion/#ch%d" % c["no"]), "ch:%d" % c["no"], text, "%s（つながり %d）" % (self.ch_label(c["no"]), ctot[c["no"]])))
            else:
                labels.append('<text class="t-muted" x="%d" y="%.1f" dominant-baseline="central">%s（要素なし）</text>' % (xB + w + 8, y, esc(self.ch_label(c["no"]))))
        for e in order:
            y = mid(nC[e["key"]])
            labels.append(link("#e-%s" % e["key"], "el:%s" % e["key"],
                               '<text x="%d" y="%.1f" dominant-baseline="central">%s<tspan class="t-n" dx="6">%d</tspan></text>'
                               % (xC + w + 8, y, esc(e["name"]), etot[e["key"]]), "%s（つながり %d）" % (e["name"], etot[e["key"]])))
        for i, (r, en, unit, items) in enumerate(rooms):
            y = mid(nD[i])
            labels.append(link(room_href[i], "room:%s" % r,
                               '<text x="%d" y="%.1f" dominant-baseline="central"><tspan class="t-room">%s</tspan>'
                               '<tspan class="t-n" x="%d" dy="20">%d %s</tspan></text>' % (xD + w + 10, y - 8, en, xD + w + 10, len(items), unit),
                               "%s（%d %s・つながり %d）" % (en, len(items), unit, rtot[i])))
        pc = ('<svg class="flowmap pc-only" viewBox="0 0 %d %d" role="group" aria-label="間の地図。間から MA Notion の章、%d の要素を経て、Dictionary・Reference・Research へ。帯の太さはつながりの数">'
              '<title>間の地図</title>%s%s%s</svg>' % (W, H, len(order), "".join(ribs), "".join(nodes), "".join(labels)))
        # ---------- スマホ（要素 → 部屋。章はまとまりの見出し） ----------
        W2, w2 = 285, 8
        xE, xR = 86, 198
        k2 = 4.6
        heads, first = {}, set()
        for e in order:
            if e["ch"] not in first:
                first.add(e["ch"])
                heads[e["key"]] = 30
        nE, endE = stack([(e["key"], etot[e["key"]]) for e in order], k2, 7, 0, 2, heads)
        _, endR = stack([(i, rtot[i]) for i in range(len(rooms))], k2, 30, 0)
        H2 = max(endE, endR + 12) + 6  # 要素の列と部屋の列の高い方に合わせる
        nR = stack([(i, rtot[i]) for i in range(len(rooms))], k2, 30, (H2 - endR) / 2 + 6)[0]
        ribs2, labels2 = [], []
        cur_r = {i: nR[i][0] for i in range(len(rooms))}
        for e in order:
            c0 = nE[e["key"]][0]
            for i in range(len(rooms)):
                v = val[e["key"]][i] * k2
                if not v:
                    continue
                d0 = cur_r[i]
                ribs2.append(rib(ribbon(xE + w2, c0, c0 + v, xR, d0, d0 + v), ch=e["ch"], el=e["key"], room=rooms[i][0]))
                c0 += v
                cur_r[i] += v
        nodes2 = [node(xE, *nE[e["key"]], w2) for e in order] + [node(xR, *nR[i], w2) for i in range(len(rooms))]
        for e in order:
            if e["key"] in heads:
                labels2.append(link(h("notion/#ch%d" % e["ch"]), "ch:%d" % e["ch"],
                                    '<text class="t-head" x="0" y="%.1f">%s</text>' % (nE[e["key"]][0] - 12, esc(self.ch_label(e["ch"]))),
                                    "%s（つながり %d）" % (self.ch_label(e["ch"]), ctot[e["ch"]])))
            labels2.append(link("#e-%s" % e["key"], "el:%s" % e["key"],
                                '<text x="%d" y="%.1f" text-anchor="end" dominant-baseline="central">%s</text>' % (xE - 6, mid(nE[e["key"]]), esc(e["name"])),
                                "%s（つながり %d）" % (e["name"], etot[e["key"]])))
        for i, (r, en, unit, items) in enumerate(rooms):
            y = mid(nR[i])
            labels2.append(link(room_href[i], "room:%s" % r,
                                '<text x="%d" y="%.1f" dominant-baseline="central"><tspan class="t-room">%s</tspan>'
                                '<tspan class="t-n" x="%d" dy="16">%d %s</tspan></text>' % (xR + w2 + 6, y - 7, en, xR + w2 + 6, len(items), unit),
                                "%s（%d %s・つながり %d）" % (en, len(items), unit, rtot[i])))
        sp = ('<svg class="flowmap fm-sp sp-only" viewBox="0 0 %d %.0f" role="group" aria-label="間の地図。%d の要素から Dictionary・Reference・Research へ。帯の太さはつながりの数">'
              '<title>間の地図</title>%s%s%s</svg>' % (W2, H2, len(order), "".join(ribs2), "".join(nodes2), "".join(labels2)))
        empty_ch = [c for c in chapters if not ctot[c["no"]]]
        note = "帯の太さは、その要素が映っている言葉・資料・テーマの数（つながりは全部で %d）。名前を押すと、要素は下の欄へ、章は Notion へ、部屋はその部屋へ。" % total
        if empty_ch:
            note += "".join("「%s」からは、まだ要素を取り出していない。" % esc(self.ch_label(c["no"])) for c in empty_ch)
        unmapped = [(en, sum(1 for x in items if not x.get("elements"))) for _, en, _, items in rooms]
        unmapped = [(en, n) for en, n in unmapped if n]
        if unmapped:
            note += "要素を決めていないもの（%s）は、地図に入れていない。" % "・".join("%s %d 件" % (en, n) for en, n in unmapped)
        return sp + "\n    " + pc, note

    def lab_quote(self, cur, item):
        """MA Notion の一節と、その章へのリンク（Notion の章は #chN で開く）。"""
        return '<p class="lab-quote"><q>%s</q> <a class="lab-ch" href="%s">%s</a></p>' % (
            esc(item["quote"]), self.href(cur, "notion/#ch%d" % item["ch"]), esc(self.ch_label(item["ch"])))

    def lab_terms(self, cur, keys, label="Dictionary"):
        """部屋どうしの参照は部屋の名前で呼ぶ（Dictionary の言葉へ）。"""
        links = "・".join('<a href="%s">%s</a>' % (self.href(cur, "lab/dictionary/#t-%s" % k), esc(self.lab_term(k)["word"])) for k in keys)
        return '<p class="ref-terms"><span class="ref-label">%s</span>%s</p>' % (esc(label), links) if keys else ""

    def lab_pole(self, v):
        p = self.lab["poles"]
        return ('<p class="pole" role="img" aria-label="%s 0 〜 %s 100 の目盛りで %d"><span class="pole-l" aria-hidden="true">%s</span>'
                '<span class="pole-bar"><span class="pole-dot" style="left:%d%%"></span></span><span class="pole-r" aria-hidden="true">%s</span></p>'
                % (esc(p["left"]), esc(p["right"]), v, esc(p["left"]), v, esc(p["right"])))

    def lab_door(self, key):
        """扉の番号と英名は site.json の gates、日本語名と役割は lab.json の doors から。"""
        d = [x for x in self.gate("lab")["doors"] if x["url"].rstrip("/").split("/")[-1] == key][0]
        info = self.lab["doors"][key]
        return dict(d, ja=info["ja"], role=info["role"])

    def lab_head(self, cur, door):
        """扉のページの見出し: 上に門の名前（小さく）、扉の帯、扉の名前（h1）と副題・役割。"""
        g = self.gate("lab")
        # 上の塊（門の名前・言葉・説明・扉の帯）は入口と同じ形で出し、その下に部屋の名前（h1）を置く。部屋を移っても上が動かない
        return ('%s\n    %s\n    <div class="room-head">\n      <h1 class="room-title"><strong>%s</strong></h1>\n'
                '      <p class="room-sub">%s</p>\n    </div>\n    <p class="lab-lead">%s</p>'
                % (self.gate_head(g, el="p"), self.local_nav(cur, g, door["url"]), esc(door["en"]), esc(door["ja"]), esc(door["role"])))

    def build_lab(self):
        lab = self.lab
        g = self.gate("lab")
        counts = {"dictionary": len(lab["terms"]), "reference": len(lab["references"]), "research": len(lab["research"])}
        units = {"dictionary": "用語", "reference": "資料", "research": "テーマ"}
        # 入口: 要素の地図と要素の欄
        cur = "lab/index.html"
        by_el = {}
        for r in lab["references"]:
            for k in r.get("elements", []):
                by_el.setdefault(k, []).append(r)
        term_of = {}
        for t in lab["terms"]:
            for k in t.get("elements", []):
                term_of.setdefault(k, []).append(t)
        cards = []
        for i, e in enumerate(lab["elements"], 1):
            mark = lambda side: '<span class="guess" role="img" aria-label="（Lab の見立て）" title="本文に無い、Lab の見立て">※</span>' if side in e.get("guess", []) else ""
            acts = "・".join(esc(a) for a in e.get("acts", []))  # 押せないので札にしない（丸い札は絞り込みだけ）
            nref = len(by_el.get(e["key"], []))
            terms = term_of.get(e["key"], [])
            ch = '<a class="lab-ch" href="%s">%s</a>' % (self.href(cur, "notion/#ch%d" % e["ch"]), esc(self.ch_label(e["ch"])))
            # 一節が密／間の側の文そのものなら、同じ文を 2 度出さず、その行に章へのリンクを付ける
            side_of_quote = "mitsu" if e["quote"] == e["mitsu"] else ("ma" if e["quote"] == e["ma"] else "")
            quote = "" if side_of_quote else '\n        <p class="el-quote"><q>%s</q> %s</p>' % (esc(e["quote"]), ch)
            row = lambda side, label: '<div class="el-row el-%s"><dt>%s</dt><dd>%s%s%s</dd></div>' % (
                side, esc(label), esc(e[side]), mark(side), (" " + ch) if side_of_quote == side else "")
            links = ['<span class="el-label">Reference</span><a href="%s">%d 件</a>' % (self.href(cur, "lab/reference/#e-%s" % e["key"]), nref)]
            if terms:
                links.append('<span class="el-label">Dictionary</span>' + "・".join('<a href="%s">%s</a>' % (self.href(cur, "lab/dictionary/#t-%s" % t["key"]), esc(t["word"])) for t in terms))
            cards.append("""      <li class="el" id="e-{key}">
        <p class="el-no">{no:02d}</p>
        <h2 class="el-name">{name}</h2>
        <p class="el-sub">{sub}</p>
        <dl class="el-pair">
          {mitsu}
          {ma}
        </dl>{quote}
{acts}
        <p class="el-links">{links}</p>
      </li>""".format(key=esc(e["key"]), no=i, name=esc(e["name"]), sub=esc(e["sub"]),
                       mitsu=row("mitsu", lab["poles"]["left"]), ma=row("ma", lab["poles"]["right"]), quote=quote,
                       acts=('\n        <p class="el-acts"><span class="el-label">当てはまる行い</span>%s</p>' % acts) if acts else "",
                       links="　".join(links)))
        # 3 つの部屋はカードにして、導入文のすぐ後（地図より先）に置く（部門の入口は下の階層へすぐ進めることが先）
        rooms = []
        for d in g["doors"]:
            key = d["url"].rstrip("/").split("/")[-1]
            info = lab["doors"][key]
            rooms.append(self.card(self.href(cur, d["url"]), [
                '<span class="card-title">%s</span>' % esc(d["en"]),
                '<span class="card-note">%s</span>' % esc(info["ja"]),
                '<span class="card-meta">%s %d</span>' % (units[key], counts[key])], "card-room"))
        flow = self.lab_flow(cur)
        body = """
  <div class="content lab-page">
    {head}
    {nav}
    <div class="lab-lead prose">
{intro}
    </div>
    <section class="sec lab-rooms">
      {rooms_tag}
    {rooms}
    </section>
    <section class="sec lab-map-sec">
      {map_tag}
    {map}
    <p class="map-note">{map_note}</p>
    </section>
    {el_label}
    <p class="el-legend">密は詰まった側、間は余白の側。※ と「当てはまる行い」は、本文に無い Lab の見立て。</p>
    <ol class="el-grid">
{cards}
    </ol>
    {rule}
    <ol class="lab-rules">
{rules}
    </ol>
    <p class="pending-note">{version}</p>
  </div>
""".format(head=self.gate_head(g), nav=self.local_nav(cur, g, g["url"]), intro="\n".join("      <p>%s</p>" % esc(x) for x in lab["intro"]),
           rooms_tag=self.tag("部屋", "t"), rooms=self.cards(rooms, "cards-room"), map_tag=self.tag("間の地図", "t"), map=flow[0], map_note=flow[1],
           el_label=self.frame("間の要素（%d・Lab の見立て）" % len(lab["elements"])), cards="\n".join(cards),
           rule=self.frame(lab["rule"]["label"]), rules="\n".join("      <li>%s</li>" % esc(x) for x in lab["rule"]["lines"]),
           version=esc(lab["version"]))
        self.page(cur, "Lab", body)

        # Dictionary（言葉）
        cur = "lab/dictionary/index.html"
        by_term = {}
        for r in lab["references"]:
            for k in r["terms"]:
                by_term.setdefault(k, []).append(r)
        rows = []
        for t in lab["terms"]:
            refs = "・".join('<a href="%s">%s</a>' % (self.href(cur, "lab/reference/#r-%s" % r["id"]), esc(r["title"])) for r in by_term.get(t["key"], []))
            related = "・".join('<a href="#t-%s">%s</a>' % (esc(k), esc(self.lab_term(k)["word"])) for k in t.get("related", []))
            acts = ""
            if t.get("acts"):
                acts = '\n        <div><dt>羅列</dt><dd>%s</dd></div>' % esc("・".join(t["acts"]))
            rows.append("""    <li class="term" id="t-{key}">
      <p class="term-kana">{reading}</p>
      <div class="term-head"><h2 class="term-word">{word}</h2><span class="status"><span class="visually-hidden">種類: </span>{kind}</span></div>
      <dl class="term-body">
        <div><dt>一般には</dt><dd>{gloss}</dd></div>
        <div><dt>MA Notion では</dt><dd>{sense}</dd></div>
        <div><dt>一節</dt><dd>{quote}</dd></div>{acts}
        <div><dt>オノマトペの手がかり</dt><dd>{ono}</dd></div>
        <div><dt>要素</dt><dd class="lab-links">{chips}</dd></div>
        <div><dt>Reference</dt><dd class="lab-links">{refs}</dd></div>
        <div><dt>関連</dt><dd class="lab-links">{related}</dd></div>
      </dl>
      <p class="lab-q"><span class="lq-label">問い</span>{q}</p>
    </li>""".format(key=esc(t["key"]), reading=esc(t["reading"]), word=esc(t["word"]), kind=esc(t["kind"]), gloss=esc(t["gloss"]),
                     sense=esc(t["sense"]), quote=self.lab_quote(cur, t), acts=acts, ono=esc("・".join(t.get("onomatopoeia", []))),
                     refs=refs or "（まだ無い）", related=related or "—", q=esc(t["question"]),
                     chips="・".join('<a class="chip" href="%s">%s</a>' % (self.href(cur, "lab/#e-%s" % k), esc(self.lab_element(k)["name"])) for k in t.get("elements", []))))
        body = """
  <div class="content lab-page">
    {head}
    <ol class="term-list">
{rows}
    </ol>
  </div>
""".format(head=self.lab_head(cur, self.lab_door("dictionary")), rows="\n".join(rows))
        self.page(cur, "Dictionary | Lab", body)

        # Reference（資料）
        cur = "lab/reference/index.html"
        labels = {"form": "形", "elements": "要素"}
        pills = lambda key, items: ('<div class="ref-filters" data-filter="%s" role="group" aria-label="%sで絞り込む">\n      <p class="rf-label">%s</p>\n      <div class="pills"><div class="pill-row">'
                                    '<button class="pill is-active" type="button" data-v="">すべて</button> %s</div></div>\n    </div>'
                                    % (key, labels[key], labels[key],
                                       " ".join('<button class="pill" type="button" data-v="%s">%s</button>' % (esc(v), esc(l)) for v, l in items)))
        rows = []
        for r in lab["references"]:
            by = esc(r["creator"]) + (("、" + esc(r["year"])) if r.get("year") else "")
            note = ('\n      <p class="ref-note">※ %s</p>' % esc(r["note"])) if r.get("note") else ""
            rows.append("""    <li class="ref" id="r-{id}" data-form="{form}" data-elements="{els}">
      <div class="ref-main">
        <p class="ref-meta">{glyph}<span class="badge">{form}</span><span class="ref-field">{field}</span><span class="status">{status}</span></p>
        <h2 class="ref-title">{title}<span class="ref-by">{by}</span></h2>
        {chips}
        {pole}
      </div>
      <div class="ref-text">
        {quote}
        <p class="ref-why">{why}</p>
        <p class="lab-q"><span class="lq-label">問い</span>{q}</p>
        {termlinks}{note}
      </div>
    </li>""".format(id=esc(r["id"]), form=esc(r["form"]), els=esc(" ".join(r.get("elements", []))), glyph=self.lab_glyph(r["form"]), field=esc(r["field"]), status=esc(r["status"]),
                     title=esc(r["title"]), by=by, chips=self.lab_chips(cur, r.get("elements", [])), pole=self.lab_pole(r["pole"]),
                     quote=self.lab_quote(cur, r), why=esc(r["why"]), q=esc(r["question"]), termlinks=self.lab_terms(cur, r["terms"]), note=note))
        body = """
  <div class="content lab-page">
    {head}
    <div class="filter-box" role="group" aria-labelledby="fb-label">
      <p class="fb-label" id="fb-label">絞り込む</p>
    {f_elements}
    {f_form}
      <p class="ref-count" aria-live="polite" aria-atomic="true"><span class="rc-now">{n}</span> 件</p>
    </div>
    <ol class="ref-list">
{rows}
    </ol>
    <p class="ref-empty" hidden>この絞り込みに当たる資料はまだありません。</p>
  </div>
""".format(head=self.lab_head(cur, self.lab_door("reference")),
           f_elements=pills("elements", [(e["key"], e["name"]) for e in lab["elements"]]),
           f_form=pills("form", [(f, f) for f in lab["forms"]]),
           n=len(lab["references"]), rows="\n".join(rows))
        self.page(cur, "Reference | Lab", body)

        # Research（検証）
        cur = "lab/research/index.html"
        rows = []
        for rs in lab["research"]:
            rows.append("""    <li class="rs" id="rs-{id}">
      <h2 class="rs-theme">{theme}{status}</h2>
      {quote}
      <p class="rs-lines">{lines}</p>
      {chips}
      {terms}
    </li>""".format(id=esc(rs["id"]), theme=esc(rs["theme"]), status=self.status_badge(rs["status"]), quote=self.lab_quote(cur, rs),
                     lines=brs(rs["lines"]), chips=self.lab_chips(cur, rs.get("elements", [])), terms=self.lab_terms(cur, rs["terms"])))
        body = """
  <div class="content lab-page">
    {head}
    <ol class="research-list">
{rows}
    </ol>
    <p class="pending-note">テーマはまだ決まっていない。ここでは、MA Notion から取れる問いを候補として置いている。</p>
  </div>
""".format(head=self.lab_head(cur, self.lab_door("research")), rows="\n".join(rows))
        self.page(cur, "Research | Lab", body)

    def build_channel(self):
        cur = "channel/index.html"
        g = self.gate("channel")
        intro = "\n".join("      <p%s>%s</p>" % (' data-m="in1" data-mt' if i == 0 else "", brs(para))
                          for i, para in enumerate(self.site["channel"]["intro"]))
        # 並びは 新しい回（1 枚）→ 番組 → 紹介文。Channel の役目は番組を選ぶことと、いちばん新しい回へすぐ行けること。
        # 新着の一覧は Home の News だけに置く（同じ一覧を 2 か所に置かない）
        latest = self.latest_episode()
        feature = self.cards([self.episode_card(cur, latest["program"], latest["n"], latest["episode"], latest["items"],
                                                show_program=True, added=latest["added"])], "cards-feature") if latest else ""
        body = """
  <div class="content">
    {head}
{feature}
    <section class="sec channel-menu">
      {logo}
      {menu_tag}
    {programs}
    </section>

    <div class="intro prose">
{intro}
    </div>

    {illust}
  </div>
""".format(head=self.gate_head(g), intro=intro, logo=self.logo(cur, "logo-mark lm-channel", m="lmc"),
           feature=('\n    <section class="sec channel-latest">\n      %s\n    %s\n    </section>\n' % (self.tag("新しい回", "t", m="lntag"), feature)) if feature else "",
           menu_tag=self.tag("番組", "a", m="cmtag"), programs=self.cards([self.program_card(cur, p) for p in self.programs], "cards-program"),
           illust=self.illust(cur, "distribution", "distribution-illust", m="dist"))
        self.page(cur, "Channel", body, main_class="page channel-page")

    def build_programs(self):
        for p in self.programs:
            cur = "channel/%s/index.html" % p["slug"]
            lead = "\n".join("        <p%s>%s</p>" % (' data-m="ld1" data-mt' if i == 0 else "", brs(para))
                             for i, para in enumerate(p.get("lead", []))) or \
                '        <p class="pending-note">番組の紹介文は準備中です。</p>'
            # 回の一覧: 第 0 回（企画背景）→ #1 から。回はカードで、押すと回のページへ（その場では開かない）
            rows = [self.prologue_card(cur, c) for c in self.prologue(p)]
            rows += [self.episode_card(cur, p, n, e, items, id_="ep-%s" % e["key"]) for n, e, items in self.numbered(p)]
            entries = self.cards(rows, "cards-episode") or '    <p class="pending-note">準備中です。</p>'
            body = """
  <div class="program-top">
    <div class="content">
      <div class="program-head">
        <p class="crumb"><a href="{channel}">{gname}</a></p>
        <h1 class="ph-title" data-m="ph" data-mt><span class="ja">{ja}</span></h1>
        <p class="ph-en">{en}</p>
        <p class="ph-sub" data-m="ps" data-mt>- {sub} -</p>
      </div>
      <div class="program-lead prose">
{lead}
      </div>
    </div>
    {illust}
    {logo}
  </div>

  <div class="content">
    <section class="sec entries" id="entries">
      {ep_tag}
    {entries}
    </section>
  </div>
  <div class="program-end">{logo_end}{illust_end}</div>
""".format(en=esc(p["en"]), ja=esc(p["ja"]), sub=esc(p["sub"]), lead=lead, channel=self.href(cur, "channel/"), gname=esc(self.gate("channel")["name"]),
           illust=self.illust(cur, p["illust"], "program-illust" + (" pc-only" if p.get("illust_sp") == "end" else ""), m="pill") if p.get("illust") else "",
           logo=self.logo(cur, "logo-mark lm-program", m="lmp") if p.get("logo") == "top" else "",
           logo_end=self.logo(cur, "logo-mark lm-end", m="lme") if p.get("logo") == "end" else "",
           illust_end=self.illust(cur, p["illust"], "program-illust-end sp-only", m="pille") if p.get("illust_sp") == "end" else "",
           ep_tag=self.tag("エピソード", "t"), entries=entries)
            self.page(cur, p["ja"], body, main_class="page program-page pg-%s" % p["slug"])

    def build_episodes(self):
        """回のページ: 動画が主役。その下に読む・聴く（見方カード）、出てくる道具、映っている間、次の一歩。
        見出しは YouTube の題に揃える（回の題と一言を YouTube に合わせる決まり）。公開済みのコンテンツが 1 つも無い回はページを作らない。"""
        for p in self.programs:
            for n, e, items in self.numbered(p):
                if not self.is_published(items):
                    continue
                cur = self.episode_url(p, e) + "index.html"
                pub = [c for c in items if c.get("status") == "published"]
                lines_ = self.ep_lines(e, items)
                place = next((c.get("place") for c in items if c.get("place")), "")
                # 動画がまだの回も、動画の枠は「準備中」で置く（読み物や音声だけ先に出た回で、動画が来ることが分かるように）
                videos = "\n    ".join(self.tv_media(c) for c in items if c["kind"] == "tv")
                views = [self.view_card(cur, c, p, e) for c in items if c["kind"] != "tv"]
                prods = []
                for c in items:
                    for pid in c.get("device", []):
                        prod = [x for x in self.device["products"] if str(x["id"]) == str(pid)]
                        if prod and prod[0] not in prods:
                            prods.append(prod[0])
                date = min((self.item_date(c) for c in pub if self.item_date(c)), default="")
                body = """
  <div class="content episode">
    <div class="episode-head">
      <p class="crumb"><a href="{channel}">{gname}</a> › <a href="{prog}">{pja}</a></p>
      <p class="ep-no">{label}</p>
      <h1 class="ep-title">{title}</h1>
      {meta}
    </div>
    {videos}
    <div class="ep-about">
      <p class="ep-lines">{lines}</p>{place}
    </div>
  {views}
  {prods}
  {els}
    {steps}
  </div>
""".format(channel=self.href(cur, "channel/"), gname=esc(self.gate("channel")["name"]), prog=self.href(cur, "channel/%s/" % p["slug"]),
           pja=esc(p["ja"]), label=esc(self.ep_label(n, e)), title=esc(self.ep_title(e, items)), meta=self.date_meta(date),
           lines="<br>".join(esc(x) for x in lines_), place=('\n      <p class="ep-place">Place: %s</p>' % esc(place)) if place else "",
           videos=videos, views=self.section("読む・聴く", self.cards(views, "cards-view")),
           prods=self.section("出てくる道具", ('<ul class="dev-grid">\n%s\n    </ul>' % "\n".join(self.product_card(cur, x) for x in prods)) if prods else ""),
           els=self.section("映っている間", self.element_chips(cur, e.get("elements", []), "要素")),
           steps=self.next_steps(cur, ("channel/%s/" % p["slug"], "番組へ戻る"), self.next_episode(p, n)))
                self.page(cur, "%s %s" % (p["ja"], self.ep_label(n, e)), body, main_class="page episode-page")

    def build_articles(self):
        for item in self.contents:
            if not (item.get("article") and item.get("status") == "published"):
                continue
            cur = self.item_url(item) + "index.html"
            h = lambda t: self.href(cur, t)
            with open(os.path.join(SRC, item["article"]), encoding="utf-8") as f:
                frag = f.read()
            frag = re.sub(r"^<!--.*?-->\n", "", frag, flags=re.S)
            frag = frag.replace('"@/', '"' + self.href(cur, ""))
            # 日付と <NEW> は回の日付から作る（断片に日付を書くと、決まりとずれたまま残るため）
            if ARTICLE_META not in frag:
                raise SystemExit("src/%s: 日付を入れる目印 %s がありません（article-head の中に置く）" % (item["article"], ARTICLE_META))
            frag = frag.replace(ARTICLE_META, self.date_meta(self.item_date(item), m="am"))
            # 原稿の題の頭の管理番号（2.2.1 など）は画面に出さない（原稿は取り込みの道具がそのまま写すので、ここで外す）
            frag = re.sub(r'(<h1 class="article-title">)\s*\d+\.\d+\.\d+(?:&ensp;|&nbsp;|\s)+', r"\1", frag)
            head, rest = split_after_block(frag, '<div class="article-head">', item["article"])
            first = re.match(r"\s*<(h2|div)\b([^>]*)>", rest, flags=re.I)
            if not (first and {"h2": "article-answer", "div": "article-body"}[first.group(1).lower()] in class_list(first.group(2))):
                raise SystemExit("src/%s: article-head の次は <h2 class=\"article-answer\"> か <div class=\"article-body\"> にする" % item["article"])
            # 冒頭の写真は、参考（tei-ku.com）と同じく、ゆっくり拡大しながら次の写真へ溶け替える（動きは js/main.js）
            slides = "\n".join('      <img class="hs-img%s" src="%s"%s alt="" decoding="async">' % (
                " is-on" if i == 0 else "", esc(h("assets/" + name)) if i == 0 else BLANK_GIF,
                "" if i == 0 else ' data-src="%s"' % esc(h("assets/" + name)))
                for i, name in enumerate(item.get("hero", [])))
            hero = ('    <div class="article-hero" data-m="ahero" aria-hidden="true">\n%s\n    </div>\n' % slides) if slides else ""
            focus = (' style="object-position: %s"' % item["portrait_focus"]) if item.get("portrait_focus") else ""
            portrait = ('  <figure class="article-portrait" data-m="aport"><img src="%s" alt="%s" loading="lazy" decoding="async"%s></figure>\n' % (
                esc(h("assets/" + item["portrait"])), esc(item["portrait_alt"]), focus)) if item.get("portrait") else ""
            if item.get("prologue"):
                ep_p = self.program(item["program"])
                where = '<a href="%s">%s</a> #0' % (h("channel/%s/" % ep_p["slug"]), esc(ep_p["ja"]))
                others, steps = "", self.next_steps(cur, ("channel/%s/" % ep_p["slug"], "番組へ戻る"))
            else:
                ep_p, ep_e, ep_items = self.find_episode(item)
                n = self.number_of(ep_p, ep_e)
                where = '<a href="%s">%s %s</a>' % (h(self.episode_url(ep_p, ep_e)), esc(ep_p["ja"]), esc(self.ep_label(n, ep_e)))
                # 記事の後ろ（人物の写真の前。戻しの指示）に、同じ回のほかの形（今の記事を除く）と次の一歩
                others = self.section("同じ回を、ほかの形で", self.cards(
                    [self.view_card(cur, c, ep_p, ep_e) for c in ep_items if c["id"] != item["id"] and c.get("status") == "published"], "cards-view"), "article-episode")
                steps = self.next_steps(cur, (self.episode_url(ep_p, ep_e), "この回へ戻る"), self.next_episode(ep_p, n))
            body = """
  <div class="article-top">
{hero}  <div class="content article">
    <p class="article-ep">{where}</p>
{head}
  </div>
  </div>
  <div class="content article" id="article-start">
{rest}
  </div>
  <div class="content">
  {others}
    {steps}
  </div>
{portrait}  <div class="home-end article-end">{logo}</div>
""".format(hero=hero, where=where, head=head.rstrip("\n"), rest=rest.strip("\n"), others=others, steps=steps, portrait=portrait,
           logo=self.logo(cur, "home-logo", m="lma"))
            self.page(cur, "%s %s" % (item.get("badge", ""), item["title"]), body, main_class="page article-page")
            for old in item.get("redirect_from", []):
                self.redirect(old, self.item_url(item), item["title"])

    def build_do(self):
        # 開いている扉が Device だけの間は、Do を押したら道具の一覧へ直接行く（do/ は一覧へ送る）
        self.redirect("do/index.html", self.gate("do")["url"], self.gate("do")["name"])
        self.build_device()
        for prod in self.device["products"]:
            self.build_product(prod)

    def shown_price(self, v):
        """Device 表の販売価格は税抜なので、総額表示（税込）にして出す。"""
        rule = self.site.get("price", {})
        if rule.get("sheet") == "税抜":
            return v["price"] * (100 + rule.get("tax_percent", 10)) // 100
        return v["price"]

    def price_label(self, prod):
        prices = [self.shown_price(v) for v in prod["variants"]]
        return yen(min(prices)) + ("~" if len(set(prices)) > 1 else "")

    def tax_label(self):
        label = self.site.get("price", {}).get("label", "")
        return ' <span class="tax">%s</span>' % esc(label) if label else ""

    def device_search(self, action=None):
        """検索欄とお店の絞り込み。道具が DEVICE_SEARCH_MIN に満たない間は出さない。"""
        if len(self.device["products"]) < DEVICE_SEARCH_MIN:
            return ""
        counts = {}
        for prod in self.device["products"]:
            counts[self.shop_of(prod)["slug"]] = counts.get(self.shop_of(prod)["slug"], 0) + 1
        pills = ['<button class="pill is-active" type="button" data-shop="">すべて</button>']
        for s_ in self.site["shops"]:
            pills.append('<button class="pill%s" type="button" data-shop="%s">%s</button>' % (
                "" if counts.get(s_["slug"]) else " is-empty", esc(s_["slug"]), esc(s_["name"])))
        form = """    <form class="dev-search" role="search" action="{action}"{method} data-m="dsearch">
      <label class="visually-hidden" for="dev-q">道具を探す</label>
      <input id="dev-q"{name} type="search" placeholder="道具を探す" autocomplete="off">
      <button type="submit" aria-label="探す"><span class="search-icon" aria-hidden="true"></span></button>
    </form>""".format(action=action or "#", method=' method="get"' if action else "", name=' name="q"' if action else "")
        if action:
            return form
        return form + """
    <div class="pills" role="group" aria-label="お店で絞り込む" data-m="dpills">
      <div class="pill-row">{p1}</div>
      <div class="pill-row">{p2}</div>
    </div>""".format(p1="".join(pills[:(len(pills) + 1) // 2]), p2="".join(pills[(len(pills) + 1) // 2:]))

    def build_device(self):
        cur = "do/device/index.html"
        g = self.gate("do")
        body = """
  <div class="content wide">
    {head}
    {nav}
    {search}
    <ul class="dev-grid" data-m="dgrid">
{cards}
    </ul>
    <p class="pending-note dev-empty" role="status" hidden>該当する道具は、まだ載せていません（順に追加します）。</p>
  </div>
""".format(head=self.gate_head(g), nav=self.local_nav(cur, g, "do/device/"), search=self.device_search(),
           cards="\n".join(self.product_card(cur, prod) for prod in self.device["products"]))
        self.page(cur, "Device | Do", body, main_class="page device-page")

    def build_product(self, prod):
        cur = self.product_url(prod) + "index.html"
        h = lambda t: self.href(cur, t)
        shop = self.shop_of(prod)
        thumbs = "\n".join('          <li><button class="thumb" type="button" aria-label="%s（%s）の写真を表示"><img src="%s" width="720" height="720" loading="lazy" decoding="async" alt=""></button></li>' % (
            esc(prod["name"]), esc(v["color"]), esc(h("assets/device/" + v["image"]))) for v in prod["variants"])
        colors = "\n".join("""          <li>
            <img src="{img}" width="720" height="720" loading="lazy" decoding="async" alt="{name}（{color}）">
            <p class="pc-color">{color}</p>
            <p class="price">{price}</p>
          </li>""".format(img=esc(h("assets/device/" + v["image"])), name=esc(prod["name"]), color=esc(v["color"]),
                          price=esc(yen(self.shown_price(v))) + self.tax_label()) for v in prod["variants"])
        feats = "\n".join("""      <figure class="feature">
        <img src="{img}" loading="lazy" decoding="async" alt="">
        <figcaption>
          <h3 class="feature-ttl">{ttl}</h3>
          <p>{body}</p>
        </figcaption>
      </figure>""".format(img=esc(h("assets/device/" + f["image"])), ttl=lines(f["title"]), body=lines(f["body"])) for f in prod["features"])
        # 出てくる回: contents.json の device にこの商品の ID を書いたコンテンツの回を、回カードで並べる（無ければ出さない）
        media, seen = [], set()
        for c in self.contents:
            if str(prod["id"]) not in [str(x) for x in c.get("device", [])] or c.get("prologue"):
                continue
            ep_p, ep_e, ep_items = self.find_episode(c)
            if (ep_p["slug"], ep_e["key"]) in seen:
                continue
            seen.add((ep_p["slug"], ep_e["key"]))
            media.append(self.episode_card(cur, ep_p, self.number_of(ep_p, ep_e), ep_e, ep_items, show_program=True))
        media_html = ("\n    " + self.section("出てくる回", self.cards(media), "product-media")) if media else ""
        media_html += ("\n    " + self.section("置いている間", self.element_chips(cur, prod.get("elements", []), "要素"))) if prod.get("elements") else ""
        # 写真は横に並べてスクロールで送る（スマホは指で送り「1/N」を出す。PC は下の小さな写真で選ぶ）
        slides = "\n".join('          <li><img src="%s" width="720" height="720"%s decoding="async" alt="%s（%s）"></li>' % (
            esc(h("assets/device/" + v["image"])), "" if i == 0 else ' loading="lazy"', esc(prod["name"]), esc(v["color"]))
            for i, v in enumerate(prod["variants"]))
        body = """
  <div class="content wide">
{nav}
{search}
    <p class="crumb" data-m="pcrumb" data-mt><a href="{home}">Home</a> › <a href="{dev}">{dname}</a> › {shop} › {name}</p>
    <div class="product-top">
      <div class="gallery" data-m="pgal">
        <ul class="gallery-track" tabindex="0" aria-label="{name} の写真（横に送る）">
{slides}
        </ul>
        <p class="gallery-count" data-m="pcount" data-mt aria-hidden="true"><span class="gc-now">1</span>/{count}</p>
        <ul class="gallery-thumbs">
{thumbs}
        </ul>
      </div>
      <div class="product-info">
        <h2 class="pi-head" data-m="phead" data-mt>商品詳細</h2>
        <p class="pi-shop" data-m="pshop" data-mt>{shop}</p>
        <h1 class="pi-name" data-m="pname" data-mt>{name}</h1>
        <p class="pi-label" data-m="plabel" data-mt>販売価格：</p>
        <p class="price price-lg" data-m="pprice" data-mt>{price}{note}</p>
        <a class="buy-btn" href="{ec}" target="_blank" rel="noopener" data-m="pbuy" data-mt>{shop}で買う <span aria-hidden="true">↗</span></a>
      </div>
      <div class="product-colors">
        <h2 class="pi-colors-head" data-m="pchead" data-mt>color: {colornames}</h2>
        <ul class="pi-colors" data-m="pcolors">
{colors}
        </ul>
      </div>
    </div>

    <section class="product-desc">
      <h2 class="line-head" data-m="pdesc" data-mt>商品説明</h2>
      <p class="pd-copy">{copy}</p>
      <div class="prose"><p>{body}</p></div>
    </section>{media}

    <section class="features" aria-label="特徴">
{feats}
    </section>
  </div>
""".format(home=h(""), dev=h("do/device/"), dname=esc(self.gate("do")["name"]), nav="    " + self.gate_head(self.gate("do"), el="p") + "\n    " + self.local_nav(cur, self.gate("do"), self.product_url(prod)), search=self.device_search(h("do/device/")), shop=esc(shop["name"]), name=esc(prod["name"]),
           slides=slides, count=len(prod["variants"]), thumbs=thumbs, price=esc(self.price_label(prod)),
           note=self.tax_label(), ec=esc(prod["ec_url"]),
           colornames=esc(" / ".join(v["color"] for v in prod["variants"])), colors=colors, copy=esc(prod["copy"]),
           body=lines(prod["body"]), feats=feats, media=media_html)
        self.page(cur, prod["name"], body, main_class="page product-page")

    def build_company(self):
        cur = "company/index.html"
        c = self.company
        ph = c["photo"]
        # 章は Notion と同じ開閉（最初は見出しだけ）。デザインの注記どおり、渡された章だけを出す
        chapters = [self.fold_chapter(ch["no"], ch["title"], ["        <p>%s</p>" % esc(x) for x in ch["paragraphs"]], i)
                    for i, ch in enumerate(c["chapters"])]

        def value(v):
            # 住所など、区切りの並び（list）は PC では 1 行、スマホでは区切りごとに改行する
            if isinstance(v, list):
                # 「[ 本社 ]」のような角括弧で始まる区切りは、括弧を行頭の外へぶら下げる（デザインどおり）
                return '<span class="seg-line">%s</span>' % " ".join('<span class="seg%s">%s</span>' % (
                    " seg-bracket" if x.startswith("[") else "", esc(x)) for x in v)
            return esc(v)
        profile = "\n".join('        <div class="pr-row%s%s"><dt>%s :</dt><dd>%s</dd></div>' % (
            {"stack": " pr-stack", "stack-sp": " pr-stack-sp"}.get(r.get("layout", ""), ""), " pr-gap" if r.get("gap_after") else "",
            esc(r["label"]), "".join(value(v) for v in r["value"])) for r in c["profile"])
        def place(x):
            # リンクのある施設は水色のリンク、無いものは本文の色（デザインの注記）
            if x.get("url"):
                return '<a href="%s" target="_blank" rel="noopener">%s <span aria-hidden="true">↗</span></a>' % (esc(x["url"]), esc(x["name"]))
            return esc(x["name"])
        fac = "\n".join("""        <li><p class="fac-name">{name}</p><ul>{items}</ul></li>""".format(
            name=place(f), items="".join("<li>%s</li>" % place(x) for x in f.get("items", []))) for f in c["facilities"])
        body = """
  <div class="content">
    <div class="simple-head">
      <h1 class="sh-en">Company</h1>
      <p class="sh-ja">{title}</p>
    </div>
    <img class="company-photo" src="{photo}" width="{w}" height="{h}" decoding="async" alt="{alt}">

    <div class="chapters">
{chapters}
    </div>

    <section class="profile">
      <h2 class="line-head" data-m="cprof" data-mt>会社概要</h2>
      <dl class="profile-list">
{profile}
      </dl>
      <p class="fac-label">運営施設 :</p>
      <ul class="facilities">
{fac}
      </ul>
    </section>
  </div>
""".format(title=esc(c["title"]), photo=self.href(cur, "assets/" + ph["src"]), w=ph["width"], h=ph["height"], alt=esc(ph["alt"]),
           chapters="\n".join(chapters), profile=profile, fac=fac)
        self.page(cur, "Company", body, main_class="page company-page")

    def build_contact(self):
        cur = "contact/index.html"
        groups = []
        for g in self.company["contact"]:
            desks = []
            for d in g["desks"]:
                rows = ['<p class="desk-name">[ %s ]</p>' % esc(d["name"]),
                        '<p>Tel: <a href="tel:%s">%s</a></p>' % (esc(d["tel"].replace("-", "")), esc(d["tel"]))]
                if d.get("fax"):
                    rows.append('<p>Fax: %s</p>' % esc(d["fax"]))
                rows += ['<p>%s</p>' % esc(x) for x in d.get("notes", [])]
                if d.get("mail"):
                    rows.append('<p><a class="mail" href="mailto:%s">%s</a></p>' % (esc(d["mail"]), esc(d["mail"])))
                desks.append('        <div class="desk">\n          %s\n        </div>' % "\n          ".join(rows))
            groups.append("""    <section class="contact-group">
      <h2 class="cg-head">{name} :</h2>
      <div class="desks">
{desks}
      </div>
    </section>""".format(name=esc(g["group"]), desks="\n".join(desks)))
        body = """
  <div class="content">
    <div class="simple-head">
      <h1 class="sh-en">Contact</h1>
      <p class="sh-ja">お問い合わせ</p>
    </div>
{groups}
  </div>
""".format(groups="\n\n".join(groups))
        self.page(cur, "Contact", body, main_class="page contact-page")

    def build_redirects(self):
        for old, target, label in (("about.html", "notion/", "Notion"),
                                   ("ma-channel.html", "channel/", "Channel"),
                                   ("edge-riders.html", "channel/", "Channel"),
                                   ("beyond-the-vanishing-point.html", "channel/beyond-the-vanishingpoint/", "死を、教えてくれ。"),
                                   # 8 月版の取材後記は、今は #2-2-3（掲載予定）の旧版にあたるので、番組のページへ送る
                                   ("article-2-2-1-postscript.html", "channel/beyond-the-vanishingpoint/", "死を、教えてくれ。")):
            self.redirect(old, target, label)
        # β 版の途中まであった「お店ごとのページ」は、そのお店の商品ページへ送る
        for s in self.site["shops"]:
            prods = [p for p in self.device["products"] if self.shop_of(p)["slug"] == s["slug"]]
            if prods:
                self.redirect("do/device/%s/index.html" % s["slug"], self.product_url(prods[0]), prods[0]["name"])

    def build(self):
        self.build_home()
        self.build_notion()
        self.build_lab()
        self.build_channel()
        self.build_programs()
        self.build_episodes()
        self.build_articles()
        self.build_do()
        self.build_company()
        self.build_contact()
        self.build_redirects()
        return self.pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="書き込まず、repo のファイルと一致するかだけ確かめる")
    a = ap.parse_args()
    pages = Site().build()
    manifest = "\n".join(sorted(pages)) + "\n"
    listed = os.path.join(ROOT, "tools", "generated.txt")
    if a.check:
        bad = []
        for rel, doc in sorted(pages.items()):
            path = os.path.join(ROOT, rel)
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != doc:
                bad.append(rel)
        if not os.path.exists(listed) or open(listed, encoding="utf-8").read() != manifest:
            bad.append("tools/generated.txt")
        stale = leftovers(pages)
        if bad or stale:
            if bad:
                print("生成結果と違うファイル: " + ", ".join(bad))
                print("（css/style.css や js/main.js を直したときも、HTML の ?v= の印が変わるので python3 tools/build.py で生成し直す）")
            if stale:
                print("今は生成していないのに残っている生成物（消すか src/ に戻す）: " + ", ".join(stale))
            return 1
        print("ok: %d ファイルが生成結果と一致" % len(pages))
        return 0
    old = set()
    if os.path.exists(listed):
        old = set(x for x in open(listed, encoding="utf-8").read().split("\n") if x)
    for rel, doc in sorted(pages.items()):
        path = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc)
    with open(listed, "w", encoding="utf-8") as f:
        f.write(manifest)
    stale = sorted(set(leftovers(pages)) | (old - set(pages)))
    print("wrote %d ファイル" % len(pages))
    if stale:
        print("今は生成していないのに残っている生成物（消すか src/ に戻す。--check はこのままだと失敗する）: " + ", ".join(stale))
    return 0


def leftovers(pages):
    """生成の目印（MARK）が付いた HTML のうち、今回生成しなかったもの（公開に残り続けるページ）。"""
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("src", "tools", "node_modules")]
        for name in files:
            if not name.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(base, name), ROOT).replace(os.sep, "/")
            if rel in pages:
                continue
            with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
                if MARK in f.read(4096):
                    found.append(rel)
    return sorted(found)


if __name__ == "__main__":
    sys.exit(main())
