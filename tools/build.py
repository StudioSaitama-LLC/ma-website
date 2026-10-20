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
import datetime
import html
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
MARK = "<!-- このファイルは tools/build.py が src/ から生成しています。直接編集せず src/ を直して再生成してください。 -->"
STATUS = {"published": "", "editing": "編集中", "planned": "掲載予定"}
KIND = {"tv": "TV", "mag": "Magazine", "radio": "Radio"}
KIND_ORDER = {"tv": 0, "mag": 1, "radio": 2}
NEW_COUNT = 3  # 日付の新しい順にこの件数だけ <NEW> を付ける
NEW_DAYS = 60  # ただし、いちばん新しい日付からこの日数より古いものには付けない
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
        self.pages = {}
        self.validate()
        self.news = self.collect_news()
        dates = sorted(set(n["date"] for n in self.news), reverse=True)
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
                if not re.fullmatch(SLUG, e.get("key", "")):
                    errors.append("programs.json %s: 回の key は英小文字・数字・ハイフンだけ: %r" % (p["slug"], e.get("key")))
                if e["key"] in episodes:
                    errors.append("programs.json: 回の key が重複: %s" % e["key"])
                episodes[e["key"]] = p["slug"]
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
            if bad_date(n.get("date")):
                errors.append("site.json news %r: date は実在する YYYY-MM-DD: %r" % (n.get("title"), n.get("date")))
        photo = self.company.get("photo", {}).get("src")
        if photo and not os.path.exists(os.path.join(ROOT, "assets", photo)):
            errors.append("company.json: assets/%s が無い" % photo)
        if errors:
            raise SystemExit("データに問題があります:\n  " + "\n  ".join(errors))

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

    def item_path(self, item):
        return "MA Channel/%s/%s" % (KIND[item["kind"]], item["id"])

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
        mine = [c for c in self.contents if c["program"] == p["slug"] and not c.get("related")]
        for e in p.get("episodes", []):
            items = sorted((c for c in mine if c.get("episode") == e["key"]),
                           key=lambda c: (KIND_ORDER[c["kind"]], id_key(c)))
            out.append((e, items))
        for c in mine:
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
        tv = self.yt_item(items)
        return tv["yt_title"] if tv else e["title"]

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

    def content(self, cid):
        for c in self.contents:
            if c["id"] == cid:
                return c
        raise SystemExit("contents.json に無い番号: %s" % cid)

    def mag_excerpt(self, c):
        """Magazine の抜き出し。記事があれば本文の冒頭から作る（記事といつも合う）。無ければ excerpt。"""
        if c.get("article"):
            with open(os.path.join(SRC, c["article"]), encoding="utf-8") as f:
                text = article_text(f.read())
            if text:
                return text
        return c.get("excerpt") or c.get("caption") or ""

    def episode_status(self, items):
        if any(c.get("status") == "published" for c in items):
            return "published"
        if any(c.get("status") == "editing" for c in items):
            return "editing"
        return "planned"

    def collect_news(self):
        news = []
        for p in self.programs:
            for e, items in self.episodes(p):
                if not e.get("date") or not items or self.episode_status(items) != "published":
                    continue
                lead = items[0]
                news.append({"date": e["date"], "path": self.item_path(lead),
                             "title": "「%s / %s」 %s" % (p["en"], p["ja"], self.ep_title(e, items)),
                             "url": "channel/%s/#ep-%s" % (p["slug"], e["key"]), "text": flat(self.ep_lines(e, items))})
        for n in self.site.get("news", []):
            news.append({"date": n["date"], "path": n.get("path", "MA"), "title": n["title"], "url": n.get("url", ""),
                         "text": n.get("text", "")})
        return sorted(news, key=lambda n: n["date"], reverse=True)

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
        return ('<div class="gate-head">\n    <%s class="gh-title" data-m="gh" data-mt><span class="gh-no">Gate %s:</span> <strong>%s</strong></%s>\n'
                '    <p class="gh-sub" data-m="gs" data-mt>%s</p>\n  </div>' % (el, esc(g["no"]), esc(g["en"]), el, esc(g["ja"])))

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

    def arrow(self, href, label, cls="", m=None):
        return '<a class="%s" href="%s" aria-label="%s"%s><span aria-hidden="true">↓</span></a>' % (
            " ".join(x for x in ("arrow-btn", cls) if x), href, esc(label), (' data-m="%s"' % m) if m else "")

    def header(self, cur):
        h = lambda t: self.href(cur, t)
        tabs = []
        for key in ("lab", "channel", "do"):
            g = self.gate(key)
            active = cur.startswith(g["url"])
            tabs.append('<a class="gate-tab gt-%s%s" href="%s"%s><span class="gt-no" data-m="tl-%s" data-mt>Gate %s:</span>'
                        '<span class="gt-box" data-m="tb-%s"><span data-m="tt-%s" data-mt>%s</span></span></a>'
                        % (key, " is-active" if active else "", h(g["url"]), ' aria-current="page"' if active else "",
                           key, esc(g["no"]), key, key, esc(g["en"])))
        # サイト名の段はスクロールで流れ、Gate の札の段は上端まで来たら貼り付く（css の .gate-bar）。メニューのボタンは右上に残す
        return """<header class="site-header">
  <a class="site-title" href="{home}" data-m="title" data-mt>{name}</a>
  <button class="menu-btn" type="button" aria-controls="site-menu" aria-expanded="false" aria-label="メニューを開く" data-m="ham">
    <span></span><span></span><span></span>
  </button>
</header>
<nav class="gate-bar" aria-label="Gate">
  <div class="gate-tabs">
    {tabs}
  </div>
</nav>

{menu}""".format(home=h(""), name=esc(self.site["name"]), tabs="\n    ".join(tabs), menu=self.menu(cur))

    def menu(self, cur):
        h = lambda t: self.href(cur, t)
        cols = []
        for g in self.site["gates"]:
            head = '<span class="gh-no">Gate %s:</span> <strong>%s</strong>' % (esc(g["no"]), esc(g["en"]))
            head = ('<a class="mg-head" href="%s">%s</a>' % (h(g["url"]), head)) if g["ready"] else (
                '<a class="mg-head is-dim" href="%s">%s</a>' % (h(g["url"]), head))
            rows = []
            if g["key"] == "channel":
                for p in self.programs:
                    rows.append('<li><a href="%s"><span class="en">%s</span> / %s</a></li>'
                                % (h("channel/%s/" % p["slug"]), esc(p["en"]), esc(p["ja"])))
            elif g["key"] == "do":
                for d in g["doors"]:
                    if d["ready"]:
                        rows.append('<li><a href="%s"><span class="en">%s</span></a></li>' % (h(d["url"]), esc(d["en"])))
                    else:
                        rows.append('<li class="is-dim"><span class="en">%s</span></li>' % esc(d["en"]))
            ul = ('\n        <ul class="mg-list">\n          %s\n        </ul>' % "\n          ".join(rows)) if rows else ""
            cols.append("""      <div class="menu-gate mg-{key}{dim}">
        {head}
        <p class="mg-sub">/ {ja}</p>{ul}
      </div>""".format(key=esc(g["key"]), dim="" if g["ready"] else " is-dim", head=head, ja=esc(g["ja"]), ul=ul))
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
    <div class="menu-links"><a href="{contact}">Contact us</a><a href="{company}">Company</a></div>
  </nav>
  {figure}
</div>
""".format(home=h(""), name=esc(self.site["name"]), cols="\n".join(cols), contact=h("contact/"), company=h("company/"),
           figure=self.illust(cur, "figure", "menu-figure"))

    def footer(self, cur):
        h = lambda t: self.href(cur, t)
        f = self.site["follow"]
        podcast = '<a href="%s" target="_blank" rel="noopener">Podcast</a>' % esc(f["podcast"]) if f.get("podcast") else "<b>Podcast</b>"
        return """<footer class="site-footer">
  <p class="fc-1"><span class="fc-name" data-m="f1" data-mt>{name}</span> <span class="fc-follow" data-m="f2" data-mt>Follow us on <a href="{yt}" target="_blank" rel="noopener">YouTube</a> , {podcast} and <a href="{note}" target="_blank" rel="noopener">note</a>.</span></p>
  <p class="fc-2" data-m="f3" data-mt>©2026, Manaka Ltd.{beta}</p>
  <button class="theme-toggle" type="button" aria-label="表示の色を切り替える" data-m="toggle">
    <span class="tt-knob"></span><span class="tt-label">Dark</span><span class="tt-icon" aria-hidden="true">☾</span>
  </button>
  <p class="footer-links" data-m="flinks"><a href="{contact}">Contact us</a><a href="{company}">Company</a></p>
</footer>
""".format(name=esc(self.site["name"]), yt=esc(f["youtube"]), podcast=podcast,
           note=esc(f["note"]), beta=("　" + esc(self.site["beta_note"])) if self.site.get("noindex") else "",
           company=h("company/"), contact=h("contact/"))

    def page(self, cur, title, body, main_class="page", description=None):
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
<script>document.documentElement.classList.add("js");try{{if(localStorage.getItem("ma-theme")==="light")document.documentElement.classList.add("light")}}catch(e){{}}(function(){{try{{if(!matchMedia("(max-width:359.98px)").matches)return;var d=document.documentElement,z=document.createElement("div");z.style.cssText="position:absolute;visibility:hidden;width:0;height:100vh;zoom:.5";d.appendChild(z);var h=z.getBoundingClientRect().height;z.remove();if(h>0&&h<innerHeight*.75)d.classList.add("zoom-vh")}}catch(e){{}}}})()</script>
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
           css=h("css/style.css"), header=self.header(cur), main_class=main_class, body=body.strip("\n"),
           footer=self.footer(cur), js=h("js/main.js"))
        self.pages[cur] = doc

    def redirect(self, cur, target, label):
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

    def entry_meta(self, date, path, status="published", el="p", m=None):
        parts = []
        if self.is_new(date):
            parts.append(self.new_badge())
        if date:
            parts.append('<span class="em-date">%s</span>' % esc(short_date(date)))
        parts.append('<span class="em-path">%s</span>' % esc(path))
        mm = (' data-m="%s" data-mt' % m) if m else ""
        return '<%s class="entry-meta"%s>%s%s</%s>' % (el, mm, " ".join(parts), self.status_badge(status), el)

    # ---------- コンテンツの部品 ----------

    def tv_media(self, item):
        if item.get("youtube") and item.get("status") == "published":
            return ('<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/%s" title="MA Channel #%s %s" '
                    'loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
                    'picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>'
                    % (esc(item["youtube"]), esc(item["id"]), esc(item["title"])))
        return '<div class="video video-ph"><span class="play" aria-hidden="true"></span><span class="ph-label">%s</span></div>' % (
            STATUS.get(item.get("status"), "") or "準備中")

    def door_block(self, cur, kind, items, level="h2", here=None):
        """回を開いたときの Door（デザインの注記「なければ排除」に合わせ、公開済みのものだけを出す）。"""
        pf = [x for x in self.site["platforms"] if x["key"] == kind][0]
        out = ['<%s class="door-head">Door: %s <strong>MA Channel / %s</strong></%s>' % (level, esc(pf["door"]), esc(pf["en"]), level)]
        if kind == "radio" and pf.get("blurb"):
            out.append('<p class="door-blurb">%s</p>' % brs(pf["blurb"]))
        for c in items:
            if kind == "tv":
                out.append(self.tv_media(c))
            elif kind == "mag":
                text = esc(self.mag_excerpt(c))
                if c.get("article"):
                    # 4 行で切り、4 行目の右に「…… ○○を読む」を置く（css の .door-text.is-clamped。リンクは本文より先に書く）
                    # 本文が 3 行に満たない短い記事では、リンクが 4 行目に残って間が空く（今の記事はどれも長い）
                    if c["id"] == here:
                        more = '<span class="more">…… <span class="read-here">この記事</span></span>'
                    else:
                        more = '<span class="more">…… <a class="read-link" href="%s">%sを読む</a></span>' % (
                            self.href(cur, self.item_url(c)), esc(c.get("badge") or "記事"))
                    out.append('<p class="door-text is-clamped">%s%s</p>' % (more, text))
                else:
                    out.append('<p class="door-text">%s</p>' % text)
            else:
                out.append('<div class="audio-ph"><span class="ph-label">SoundCloud</span></div>')
        return '<section class="door door-%s">\n        %s\n      </section>' % (kind, "\n        ".join(out))

    def entry(self, cur, p, e, items, n, opened=False, id_prefix="ep-", here=None):
        """番組の回。公開済みのコンテンツがあれば ↓ で開き、TV・Magazine・Radio の Door が並ぶ。
        題と一言は YouTube に合わせる（ep_title・ep_lines）。opened=True で開いた状態で出す（記事の後ろ）。"""
        status = self.episode_status(items)
        lead = items[0] if items else None
        meta = self.entry_meta(e.get("date", "") if status == "published" else "",
                               self.item_path(lead) if lead else "MA Channel", status, el="span", m="em%d" % n)
        text = self.ep_lines(e, items)
        place = next((c.get("place") for c in items if c.get("place")), "")
        if place:
            text.append("Place: " + place)
        text_html = ('<span class="entry-text" data-m="ex%d" data-mt>%s</span>' % (n, "<br>".join(esc(x) for x in text))) if text else ""
        if e.get("excerpt"):
            # まだ載せていない記事は、本文の冒頭を 4 行だけ見せる（読むリンクは無い）
            text_html += '<span class="entry-excerpt">%s</span>' % esc(e["excerpt"])
        badge = ('<span class="badge">%s</span> ' % esc(e["badge"])) if e.get("badge") else ""
        title = '<span class="entry-title" data-m="et%d" data-mt>%s%s</span>' % (n, badge, esc(bracket(self.ep_title(e, items))))
        pub = [c for c in items if c.get("status") == "published"]
        if not pub:
            return """    <div class="entry is-planned" id="{pre}{key}">
      {meta}
      {title}
      {text}
    </div>""".format(pre=id_prefix, key=esc(e["key"]), meta=meta, title=title, text=text_html)
        kinds = []
        for k in ("tv", "mag", "radio"):
            ks = [c for c in pub if c["kind"] == k]
            if ks:
                kinds.append(self.door_block(cur, k, ks, here=here))
        return """    <details class="entry" id="{pre}{key}"{open}>
      <summary>
        {meta}
        {title}
        {text}<span class="fold-btn" aria-hidden="true"></span>
      </summary>
      <div class="entry-body">
      {body}
        <p class="fold-end"><button class="entry-close" type="button" aria-label="閉じる"></button></p>
      </div>
    </details>""".format(pre=id_prefix, key=esc(e["key"]), open=" open" if opened else "", meta=meta, title=title,
                         text=text_html, body="\n      ".join(kinds))

    # ---------- 各ページ ----------

    def build_home(self):
        cur = "index.html"
        h = lambda t: self.href(cur, t)
        q = self.site["quote"]
        if q.get("lines"):
            quote = "\n".join('    <p%s>%s</p>' % (' data-m="q1" data-mt' if i == 0 else "", esc(l)) for i, l in enumerate(q["lines"]))
        else:
            quote = '    <p class="pending-note" data-m="q1" data-mt>%s</p>' % esc(q["pending"])
        gates = []
        for i, g in enumerate(self.site["gates"]):
            head = '<span class="gh-no">Gate %s:</span> <strong>%s</strong> <span class="gh-ja">/ %s</span>' % (
                esc(g["no"]), esc(g["en"]), esc(g["ja"]))
            head = ('<a href="%s">%s</a>' % (h(g["url"]), head)) if g["ready"] else head
            doors = []
            for d in g["doors"]:
                label = "Door %s: %s" % (esc(d["no"]), esc(d["en"]))
                if d["ready"] and d.get("url"):
                    doors.append('<li><a href="%s">%s</a></li>' % (h(d["url"]), label))
                elif d["ready"]:
                    doors.append('<li>%s</li>' % label)
                else:
                    doors.append('<li class="is-dim">%s</li>' % label)
            gates.append("""      <li class="toc-gate{dim}">
        <p class="toc-head" data-m="g{i}" data-mt>{head}</p>{doors}
      </li>""".format(dim="" if g["ready"] else " is-dim", head=head, i=i,
                      doors=('\n        <ul class="toc-doors" data-m="d%d" data-mt>\n          %s\n        </ul>' % (i, "\n          ".join(doors))) if doors else ""))
        news = []
        for i, n in enumerate(self.news[:3], 1):
            title = esc(n["title"])
            if n.get("url"):
                title = '<a href="%s">%s</a>' % (h(n["url"]), title)
            # MA Channel の Latest News と同じく、題の下に一言を出す（長いときは 3 行で切る）
            news.append("""      <li class="news-item" data-m="ni{i}">
        {meta}
        <p class="news-title" data-m="nt{i}" data-mt>{title}</p>{text}
      </li>""".format(i=i, meta=self.entry_meta(n["date"], n["path"], m="nm%d" % i), title=title,
                      text=('\n        <p class="news-text" data-m="nx%d" data-mt>%s</p>' % (i, esc(n["text"]))) if n.get("text") else ""))
        body = """
  <h1 class="visually-hidden">{name}</h1>

  <section class="hero" id="top">
    <div class="hero-block">
      <p class="hero-now" data-m="now" data-mt>現在、</p>
      <p class="hero-count" data-m="count"><span class="hc-line" data-m="hcline"></span><span class="hc-num" data-m="hcnum">{visitors}</span></p>
      <p class="hero-text" data-m="htext" data-mt>人が平場に立ちました。</p>
      {figure}
    </div>
    {arrow1}
  </section>

  <section class="quote col" id="quote" aria-label="引用">
{quote}
    <p class="quote-credit" data-m="credit" data-mt>(-{credit})</p>
    {hiraba}
    {arrow2}
  </section>

  <section class="toc col" id="toc">
    {toc_tag}
    <p class="formula" data-m="formula"><span class="fm-left" data-m="fml" data-mt>We create of Your MA <span class="fm-eq">=</span></span><span class="fm-frac"><span class="fm-num" data-m="fmn" data-mt>Lab × Ch × Do</span><span class="fm-bar" aria-hidden="true"></span><span class="fm-den" data-m="fmd" data-mt>Notion</span></span></p>
    {frame}
    <ol class="toc-gates">
{gates}
    </ol>
  </section>

  <section class="news col" id="news">
    {news_tag}
    {device}
    <ol class="news-list">
{news}
    </ol>
  </section>
  <div class="home-end">{homelogo}</div>
""".format(homelogo=self.logo(cur, "home-logo", m="flogo"), name=esc(self.site["name"]), visitors=esc(str(self.site.get("visitors", 1))),
           figure=self.illust(cur, "figure", "hero-figure", m="figure"), arrow1=self.arrow("#quote", "引用へ進む", "arrow-1", m="arrow1"),
           quote=quote, credit=esc(q["credit"]), hiraba=self.illust(cur, "hiraba", "hiraba-illust", m="hiraba"),
           arrow2=self.arrow("#toc", "目次へ進む", "arrow-2", m="arrow2"), toc_tag=self.tag("Table of Contents", "b", m="toctag"),
           frame=self.frame("間を巡る 4 つの門と 8 つの扉", m="frame"), gates="\n".join(gates),
           news_tag=self.tag("News", "t", m="newstag"), device=self.illust(cur, "device", "device-illust", m="device"),
           news="\n".join(news))
        self.page(cur, None, body, main_class="page home-page")

    def fold_chapter(self, no, title, paras, i):
        """章の開閉（最初は見出しだけ。↓ で全文、末尾の ↑ で見出しだけに戻す）。"""
        return """    <section class="fold chapter is-folded" id="ch{no}">
      <h2 class="fold-head"><span data-m="ch{i}" data-mt>第 {no} 章 : 「{title}」</span><button class="fold-toggle" type="button" aria-expanded="false" aria-controls="ch{no}-body" aria-label="第 {no} 章を開く・閉じる"></button></h2>
      <div class="fold-body prose" id="ch{no}-body">
{paras}
        <p class="fold-end"><button class="fold-close" type="button" aria-controls="ch{no}-body" aria-label="第 {no} 章を閉じる"></button></p>
      </div>
    </section>""".format(no=no, title=esc(title), paras="\n".join(paras), i=i)

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
            chapters.append(self.fold_chapter(c["no"], c["title"], out, i))
        core, steps = n["core"], n["steps"]
        flow = []
        for i, st in enumerate(steps["flow"]):
            flow.append("""        <li class="flow-step fs-{i}">
          <div class="flow-box"><span>Gate {gate}:</span><span><strong>{en}</strong> <span class="flow-ja">({ja})</span></span><span>“{verb}”</span></div>
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
  </div>
""".format(logo=self.logo(cur, "logo-mark lm-notion", m="lmn"), head=self.gate_head(self.gate("notion")),
           chapters="\n\n".join(chapters), core_label=self.frame(core["label"], m="corel"), core_heading=esc(core["heading"]),
           core_lines=brs(core["lines"]), dense=self.href(cur, "assets/figures/dots-dense.svg"), sparse=self.href(cur, "assets/figures/dots-sparse.svg"), cap0=esc(cap[0]), cap1=esc(cap[1]), cap2=esc(cap[2]),
           steps_label=self.frame(steps["label"], m="stepl"), steps_lines=brs(steps["lines"]),
           flow="\n".join(flow), book=self.illust(cur, "book", "book-illust", m="book"))
        self.page(cur, "MA Notion", body)

    def build_lab(self):
        cur = "lab/index.html"
        g = self.gate("lab")
        doors = "\n".join('      <li class="is-dim">Door %s: %s</li>' % (esc(d["no"]), esc(d["en"])) for d in g["doors"])
        body = """
  <div class="content">
    {head}
    <ul class="door-list">
{doors}
    </ul>
    <p class="pending-note">MA Lab は準備中です。</p>
  </div>
""".format(head=self.gate_head(g), doors=doors)
        self.page(cur, "MA Lab", body)

    def build_channel(self):
        cur = "channel/index.html"
        h = lambda t: self.href(cur, t)
        g = self.gate("channel")
        intro = "\n".join("      <p%s>%s</p>" % (' data-m="in1" data-mt' if i == 0 else "", brs(para))
                          for i, para in enumerate(self.site["channel"]["intro"]))
        menu = "\n".join("""      <li data-m="pm{i}" data-mt><a href="{url}"><span class="pl-en"><span class="en">{en}</span></span> <span class="pl-ja">/ {ja}</span></a> <span class="sub">- {sub} -</span></li>""".format(
            i=i, url=h("channel/%s/" % p["slug"]), en=esc(p["en"]), ja=esc(p["ja"]), sub=esc(p["sub"])) for i, p in enumerate(self.programs))
        latest = []
        for di, pf in enumerate(self.site["platforms"]):
            # 公開済みを先に、その中は日付の新しい順・番号の大きい順。各 Door 3 件まで
            items = sorted((c for c in self.contents if c["kind"] == pf["key"] and not c.get("related")),
                           key=self.latest_key)[:3]
            rows = []
            for j, c in enumerate(items):
                p = self.program(c["program"])
                ep = c.get("episode") or c["id"]
                yt = c if (c.get("status") == "published" and c.get("yt_title")) else {}
                title = '<a href="%s">「%s / %s」 %s</a>' % (h("channel/%s/#ep-%s" % (p["slug"], ep)), esc(p["en"]), esc(p["ja"]),
                                                          esc(yt.get("yt_title") or c["title"]))
                text = flat((yt.get("yt_lead") or "").split("\n")) or c.get("caption") or c.get("excerpt") or ""
                mk = "l%d%d" % (di, j)
                rows.append("""        <li class="news-item">
          {meta}
          <p class="news-title" data-m="{mk}t" data-mt>{title}</p>{text}
        </li>""".format(meta=self.entry_meta(self.item_date(c) if c.get("status") == "published" else "",
                                           self.item_path(c), c.get("status"), m=mk + "m"), title=title, mk=mk,
                        text=('\n          <p class="news-text" data-m="%sx" data-mt>%s</p>' % (mk, esc(text))) if text else ""))
            latest.append("""    <section class="door" id="{key}">
      <h3 class="door-head" data-m="dh{di}" data-mt>Door: {door} <strong>MA Channel / {en}</strong></h3>
      <ol class="news-list">
{rows}
      </ol>
    </section>""".format(key=pf["key"], door=esc(pf["door"]), en=esc(pf["en"]), di=di,
                         rows="\n".join(rows) or '        <li class="pending-note">準備中です。</li>'))
        body = """
  <div class="content">
    {head}

    <div class="intro prose">
{intro}
    </div>

    <section class="channel-menu">
      {logo}
      {menu_tag}
      <ul class="program-list">
{menu}
      </ul>
    </section>

    <section class="latest">
      {latest_tag}
{latest}
    </section>

    {illust}
  </div>
""".format(head=self.gate_head(g), intro=intro, logo=self.logo(cur, "logo-mark lm-channel", m="lmc"),
           menu_tag=self.tag("MA Channel Menu", "a", m="cmtag"), menu=menu, latest_tag=self.tag("Latest News", "t", m="lntag"),
           latest="\n".join(latest), illust=self.illust(cur, "distribution", "distribution-illust", m="dist"))
        self.page(cur, "MA Channel", body, main_class="page channel-page")

    def build_programs(self):
        for p in self.programs:
            cur = "channel/%s/index.html" % p["slug"]
            lead = "\n".join("        <p%s>%s</p>" % (' data-m="ld1" data-mt' if i == 0 else "", brs(para))
                             for i, para in enumerate(p.get("lead", []))) or \
                '        <p class="pending-note">番組の紹介文は準備中です。</p>'
            eps = self.episodes(p)
            entries = "\n\n".join(self.entry(cur, p, e, items, i + 1) for i, (e, items) in enumerate(eps))
            # 関連コンテンツ＝この番組で related にしたもの＋programs.json の related に番号を並べたもの（ほかの番組の回も入れられる）
            related = [c for c in self.contents if c["program"] == p["slug"] and c.get("related")]
            related += [self.content(cid) for cid in p.get("related", [])]
            related.sort(key=lambda c: (KIND_ORDER[c["kind"]], id_key(c)))
            rel = ""
            if related:
                rel_items = []
                for k, c in enumerate(related):
                    e = dict(self.solo_episode(c), date=self.item_date(c), badge=c.get("badge", ""),
                             excerpt=c.get("excerpt", "") if c.get("status") != "published" else "")
                    rel_items.append(self.entry(cur, self.program(c["program"]), e, [c], 100 + k, id_prefix="rel-"))
                rel = """
    <section class="related">
      <h2 class="related-head" data-m="relh"><span data-mt>関連コンテンツ：</span>{logo}</h2>
      <div class="entries">
{items}
      </div>
    </section>
""".format(logo=self.logo(cur, "logo-mark lm-related"), items="\n".join(rel_items))
            body = """
  <div class="program-top">
    <div class="content">
      <div class="program-head">
        <h1 class="ph-title" data-m="ph" data-mt><span class="en">{en}</span> <span class="ja">/ {ja}</span></h1>
        <p class="ph-sub" data-m="ps" data-mt>- {sub} -</p>
      </div>
      <div class="program-lead prose">
{lead}
      </div>
    </div>
    {illust}
    {logo}
    {arrow}
  </div>

  <div class="content">
    <div class="entries" id="entries">
{entries}
    </div>
{rel}
  </div>
  <div class="program-end">{logo_end}{illust_end}</div>
""".format(en=esc(p["en"]), ja=esc(p["ja"]), sub=esc(p["sub"]), lead=lead,
           illust=self.illust(cur, p["illust"], "program-illust" + (" pc-only" if p.get("illust_sp") == "end" else ""), m="pill") if p.get("illust") else "",
           logo=self.logo(cur, "logo-mark lm-program", m="lmp") if p.get("logo") == "top" else "",
           logo_end=self.logo(cur, "logo-mark lm-end", m="lme") if p.get("logo") == "end" else "",
           illust_end=self.illust(cur, p["illust"], "program-illust-end sp-only", m="pille") if p.get("illust_sp") == "end" else "",
           arrow=self.arrow("#entries", "コンテンツへ進む", "arrow-p", m="parrow"), entries=entries or '    <p class="pending-note">準備中です。</p>',
           rel=rel)
            self.page(cur, "%s / %s" % (p["en"], p["ja"]), body, main_class="page program-page pg-%s" % p["slug"])

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
            frag = frag.replace(ARTICLE_META, self.entry_meta(self.item_date(item), self.item_path(item), item.get("status"), m="am"))
            # 見出しの塊（article-head）までを上の段に、残りを本文の段に分ける。矢印は上の段の右下に置く
            head, rest = split_after_block(frag, '<div class="article-head">', item["article"])
            first = re.match(r"\s*<(h2|div)\b([^>]*)>", rest, flags=re.I)
            if not (first and {"h2": "article-answer", "div": "article-body"}[first.group(1).lower()] in class_list(first.group(2))):
                raise SystemExit("src/%s: article-head の次は <h2 class=\"article-answer\"> か <div class=\"article-body\"> にする（右の矢印と重ならない余白がそこに付く）" % item["article"])
            # 冒頭の写真は、参考（tei-ku.com）と同じく、ゆっくり拡大しながら次の写真へ溶け替える（動きは js/main.js）
            # 2 枚目からは data-src に置き、切り替えが動くとき（js/main.js がページを開いた時点で）に読む。
            # 動きを減らす設定や JS 無しでは 1 枚目だけを出し、残りは読まない（src は 1px の透明な画像）
            slides = "\n".join('      <img class="hs-img%s" src="%s"%s alt="" decoding="async">' % (
                " is-on" if i == 0 else "", esc(h("assets/" + name)) if i == 0 else BLANK_GIF,
                "" if i == 0 else ' data-src="%s"' % esc(h("assets/" + name)))
                for i, name in enumerate(item.get("hero", [])))
            hero = ('    <div class="article-hero" data-m="ahero" aria-hidden="true">\n%s\n    </div>\n' % slides) if slides else ""
            # 記事の終わりは、対象の人物の写真を画面いっぱいに出す（デザインの注記）
            # portrait_focus: 画面いっぱいに切り抜くとき、写真のどこを中心に残すか（例 "68% 50%"）
            focus = (' style="object-position: %s"' % item["portrait_focus"]) if item.get("portrait_focus") else ""
            portrait = ('  <figure class="article-portrait" data-m="aport"><img src="%s" alt="%s" loading="lazy" decoding="async"%s></figure>\n' % (
                esc(h("assets/" + item["portrait"])), esc(item["portrait_alt"]), focus)) if item.get("portrait") else ""
            # 記事の後ろ（人物の写真の前）に、この記事が入っている回の枠を開いた状態で置く（同じ回の TV・ほかの記事へ進める）
            ep_p, ep_e, ep_items = self.find_episode(item)
            episode = self.entry(cur, ep_p, ep_e, ep_items, 200, opened=True, here=item["id"])
            body = """
  <div class="article-top">
{hero}  <div class="content article">
{head}
  </div>
  {arrow}
  </div>
  <div class="content article" id="article-start">
{rest}
  </div>
  <section class="content article-episode" aria-label="この回のコンテンツ">
{episode}
  </section>
{portrait}  <div class="home-end article-end">{logo}</div>
""".format(hero=hero, head=head.rstrip("\n"), rest=rest.strip("\n"), episode=episode, portrait=portrait,
           arrow=self.arrow("#article-start", "本文へ進む", "arrow-a", m="aarrow"),
           logo=self.logo(cur, "home-logo", m="lma"))
            self.page(cur, "%s %s" % (item.get("badge", ""), item["title"]), body, main_class="page article-page")
            for old in item.get("redirect_from", []):
                self.redirect(old, self.item_url(item), "#%s %s" % (item["id"], item["title"]))

    def build_do(self):
        cur = "do/index.html"
        h = lambda t: self.href(cur, t)
        g = self.gate("do")
        rows = []
        for d in g["doors"]:
            label = "Door %s: %s" % (esc(d["no"]), esc(d["en"]))
            if d["ready"]:
                rows.append('      <li><a href="%s">%s</a></li>' % (h(d["url"]), label))
            else:
                rows.append('      <li class="is-dim">%s <span class="status">準備中</span></li>' % label)
        body = """
  <div class="content">
    {head}
    <ul class="door-list">
{rows}
    </ul>
  </div>
""".format(head=self.gate_head(g), rows="\n".join(rows))
        self.page(cur, "MA Do", body)
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

    def build_device(self):
        cur = "do/device/index.html"
        h = lambda t: self.href(cur, t)
        counts = {}
        for prod in self.device["products"]:
            counts[self.shop_of(prod)["slug"]] = counts.get(self.shop_of(prod)["slug"], 0) + 1
        pills = ['<button class="pill is-active" type="button" data-shop="">ALL</button>']
        for s in self.site["shops"]:
            pills.append('<button class="pill%s" type="button" data-shop="%s">%s</button>' % (
                "" if counts.get(s["slug"]) else " is-empty", esc(s["slug"]), esc(s["name"])))
        cards = []
        for prod in self.device["products"]:
            shop = self.shop_of(prod)
            v = prod["variants"][0]
            url = h(self.product_url(prod))
            cards.append("""      <li class="dev-card" data-shop="{slug}" data-text="{text}">
        <a class="dc-img" href="{url}"><img src="{img}" width="720" height="720" loading="lazy" decoding="async" alt="{name}"></a>
        <p class="dc-shop">{shop}</p>
        <p class="dc-name">{name}</p>
        <p class="price">{price}{tax}</p>
        <a class="dc-btn" href="{url}">詳細</a>
      </li>""".format(slug=esc(shop["slug"]), text=esc(" ".join([prod["name"], prod["shop"], prod["category"], prod["copy"]] + [v["color"] for v in prod["variants"]])),
                      url=url, img=esc(h("assets/device/" + v["image"])), name=esc(prod["name"]), shop=esc(shop["name"]),
                      price=esc(self.price_label(prod)), tax=self.tax_label()))
        body = """
  <div class="content wide">
    <h1 class="visually-hidden">Device Room</h1>
    <form class="dev-search" role="search" action="#" data-m="dsearch">
      <label class="visually-hidden" for="dev-q">MA Do / Device を検索</label>
      <input id="dev-q" type="search" placeholder="MA Do / Device を検索" autocomplete="off">
      <button type="submit" aria-label="検索"><span class="search-icon" aria-hidden="true"></span></button>
    </form>
    <div class="pills" role="group" aria-label="お店で絞り込む" data-m="dpills">
      <div class="pill-row">{pills1}</div>
      <div class="pill-row">{pills2}</div>
    </div>
    <ul class="dev-grid" data-m="dgrid">
{cards}
    </ul>
    <p class="pending-note dev-empty" role="status" hidden>該当する商品は、まだ載せていません（順に追加します）。</p>
  </div>
""".format(pills1="".join(pills[:(len(pills) + 1) // 2]), pills2="".join(pills[(len(pills) + 1) // 2:]), cards="\n".join(cards))
        self.page(cur, "Device Room", body, main_class="page device-page")

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
        # 商品の情緒（映像・記事・音声）: contents.json の device にこの商品の ID を書いたコンテンツを、回の枠で並べる（無ければ出さない）
        media, seen = [], set()
        for c in self.contents:
            if str(prod["id"]) not in [str(x) for x in c.get("device", [])]:
                continue
            ep_p, ep_e, ep_items = self.find_episode(c)
            if (ep_p["slug"], ep_e["key"]) in seen:
                continue
            seen.add((ep_p["slug"], ep_e["key"]))
            media.append(self.entry(cur, ep_p, ep_e, ep_items, 300 + len(media), id_prefix="dv-"))
        media_html = ('\n      <div class="entries product-media">\n%s\n      </div>' % "\n".join(media)) if media else ""
        # 写真は横に並べてスクロールで送る（スマホは指で送り「1/N」を出す。PC は下の小さな写真で選ぶ）
        slides = "\n".join('          <li><img src="%s" width="720" height="720"%s decoding="async" alt="%s（%s）"></li>' % (
            esc(h("assets/device/" + v["image"])), "" if i == 0 else ' loading="lazy"', esc(prod["name"]), esc(v["color"]))
            for i, v in enumerate(prod["variants"]))
        body = """
  <div class="content wide">
    <form class="dev-search" role="search" action="{dev}" method="get" data-m="dsearch">
      <label class="visually-hidden" for="dev-q">MA Do / Device を検索</label>
      <input id="dev-q" name="q" type="search" placeholder="MA Do / Device を検索" autocomplete="off">
      <button type="submit" aria-label="検索"><span class="search-icon" aria-hidden="true"></span></button>
    </form>
    <p class="crumb" data-m="pcrumb" data-mt><a href="{home}">Home</a> › <a href="{do}">MA Do</a> › <a href="{dev}">Device</a> › {shop} › {name}</p>
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
        <a class="buy-btn" href="{ec}" target="_blank" rel="noopener" data-m="pbuy" data-mt>ウェブサイトへ移動</a>
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
      <div class="prose"><p>{body}</p></div>{media}
    </section>

    <section class="features" aria-label="特徴">
{feats}
    </section>
  </div>
""".format(home=h(""), do=h("do/"), dev=h("do/device/"), shop=esc(shop["name"]), name=esc(prod["name"]),
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
                return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(x["url"]), esc(x["name"]))
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
      <h1 class="sh-en">Contact us</h1>
      <p class="sh-ja">お問い合わせ</p>
    </div>
{groups}
  </div>
""".format(groups="\n\n".join(groups))
        self.page(cur, "Contact us", body, main_class="page contact-page")

    def build_redirects(self):
        for old, target, label in (("about.html", "notion/", "MA Notion"),
                                   ("ma-channel.html", "channel/", "MA Channel"),
                                   ("edge-riders.html", "channel/", "MA Channel"),
                                   ("beyond-the-vanishing-point.html", "channel/beyond-the-vanishingpoint/", "死を、教えてくれ。")):
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
