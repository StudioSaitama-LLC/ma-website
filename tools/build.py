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
ARTICLE_META = "<!-- build:meta -->"  # 記事の断片で、日付の行を入れる場所


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
            if p.get("illust") and not os.path.exists(os.path.join(ROOT, "assets", "illust", p["illust"])):
                errors.append("programs.json %s: assets/illust/%s が無い" % (p["slug"], p["illust"]))
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
            if c.get("article") and not os.path.exists(os.path.join(SRC, c["article"])):
                errors.append("contents.json #%s: 記事のファイルが無い: src/%s" % (cid, c["article"]))
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
                out.append(({"key": c["id"], "title": c["title"], "caption": c.get("caption", ""),
                             "text": "", "date": c.get("date", "")}, [c]))
        return out

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
                             "title": "「%s / %s」 %s" % (p["en"], p["ja"], e["title"]),
                             "url": "channel/%s/#ep-%s" % (p["slug"], e["key"]), "text": e.get("caption", "")})
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

    def tag(self, text, variant="a", el="h2", id_=None):
        """白い札の見出し（デザインの News・Table of Contents など）。"""
        return '<%s class="tag tag-%s"%s>%s</%s>' % (el, variant, (' id="%s"' % id_) if id_ else "", esc(text), el)

    def frame(self, text, el="h2"):
        """白い線で囲んだ見出し（「間を巡る 4 つの門と 8 つの扉」など）。"""
        return '<%s class="frame-label">%s</%s>' % (el, esc(text), el)

    def gate_head(self, g, el="h1"):
        return ('<div class="gate-head">\n    <%s class="gh-title"><span class="gh-no">Gate %s:</span> <strong>%s</strong></%s>\n'
                '    <p class="gh-sub">%s</p>\n  </div>' % (el, esc(g["no"]), esc(g["en"]), el, esc(g["ja"])))

    def new_badge(self):
        return '<span class="new">&lt;NEW&gt;</span>'

    def status_badge(self, status):
        s = STATUS.get(status, "")
        return ' <span class="status">%s</span>' % s if s else ""

    def illust(self, cur, name, cls, w=None, h=None):
        dims = (' width="%d" height="%d"' % (w, h)) if w and h else ""
        return '<img class="illust %s" src="%s"%s alt="" loading="lazy" decoding="async">' % (
            cls, self.href(cur, "assets/illust/" + name), dims)

    def logo(self, cur, cls="logo-mark"):
        return '<img class="%s" src="%s" width="496" height="512" alt="間｜MA ロゴマーク" loading="lazy" decoding="async">' % (
            cls, self.href(cur, "assets/logo.png"))

    def arrow(self, href, label, cls=""):
        return '<a class="%s" href="%s" aria-label="%s"><span aria-hidden="true">↓</span></a>' % (
            " ".join(x for x in ("arrow-btn", cls) if x), href, esc(label))

    def header(self, cur):
        h = lambda t: self.href(cur, t)
        tabs = []
        for i, key in enumerate(("lab", "channel", "do"), 1):
            g = self.gate(key)
            active = cur.startswith(g["url"])
            tabs.append('<a class="gate-tab gt-%s%s" href="%s"%s><span class="gt-no">Gate %s:</span><span class="gt-box">%s</span></a>'
                        % (key, " is-active" if active else "", h(g["url"]), ' aria-current="page"' if active else "",
                           esc(g["no"]), esc(g["en"])))
        return """<header class="site-header">
  <div class="bar">
    <a class="site-title" href="{home}">{name}</a>
    <button class="menu-btn" type="button" aria-controls="site-menu" aria-expanded="false" aria-label="メニューを開く">
      <span></span><span></span><span></span>
    </button>
  </div>
  <nav class="gate-tabs" aria-label="Gate">
    {tabs}
  </nav>
</header>

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
            cols.append("""      <div class="menu-gate{dim}">
        {head}
        <p class="mg-sub">/ {ja}</p>{ul}
      </div>""".format(dim="" if g["ready"] else " is-dim", head=head, ja=esc(g["ja"]), ul=ul))
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
           figure=self.illust(cur, "figure.png", "menu-figure", 321, 1207))

    def footer(self, cur):
        h = lambda t: self.href(cur, t)
        f = self.site["follow"]
        podcast = '<a href="%s" target="_blank" rel="noopener">Podcast</a>' % esc(f["podcast"]) if f.get("podcast") else "<b>Podcast</b>"
        return """<footer class="site-footer">
  {logo}
  <div class="footer-credit">
    <p>{name}</p>
    <p>Follow us on <a href="{yt}" target="_blank" rel="noopener">YouTube</a> , {podcast} and <a href="{note}" target="_blank" rel="noopener">note</a>.</p>
    <p>©2026, Manaka Ltd.{beta}</p>
  </div>
  <button class="theme-toggle" type="button" aria-label="表示の色を切り替える">
    <span class="tt-knob"></span><span class="tt-label">Dark</span><span class="tt-icon" aria-hidden="true">☾</span>
  </button>
  <div class="footer-links"><a href="{contact}">Contact us</a><a href="{company}">Company</a></div>
</footer>
""".format(logo=self.logo(cur, "footer-logo"), name=esc(self.site["name"]), yt=esc(f["youtube"]), podcast=podcast,
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
<script>document.documentElement.classList.add("js");try{{if(localStorage.getItem("ma-theme")==="light")document.documentElement.classList.add("light")}}catch(e){{}}</script>
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

    def entry_meta(self, date, path, status="published", el="p"):
        parts = []
        if self.is_new(date):
            parts.append(self.new_badge())
        if date:
            parts.append('<span class="em-date">%s</span>' % esc(short_date(date)))
        parts.append('<span class="em-path">%s</span>' % esc(path))
        return '<%s class="entry-meta">%s%s</%s>' % (el, " ".join(parts), self.status_badge(status), el)

    # ---------- コンテンツの部品 ----------

    def tv_media(self, item):
        if item.get("youtube") and item.get("status") == "published":
            return ('<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/%s" title="MA Channel #%s %s" '
                    'loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
                    'picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>'
                    % (esc(item["youtube"]), esc(item["id"]), esc(item["title"])))
        return '<div class="video video-ph"><span class="play" aria-hidden="true"></span><span class="ph-label">%s</span></div>' % (
            STATUS.get(item.get("status"), "") or "準備中")

    def door_block(self, cur, kind, items, level="h2"):
        pf = [x for x in self.site["platforms"] if x["key"] == kind][0]
        out = ['<%s class="door-head">Door: %s <strong>MA Channel / %s</strong></%s>' % (level, esc(pf["door"]), esc(pf["en"]), level)]
        if pf.get("blurb"):
            out.append('<p class="door-blurb">%s</p>' % brs(pf["blurb"]))
        for c in items:
            head = ['<span class="em-path">#%s</span>' % esc(c["id"])]
            if c.get("badge"):
                head.append('<span class="badge">%s</span>' % esc(c["badge"]))
            head.append('<span class="dc-title">%s</span>' % esc(c["title"]))
            block = ['<p class="door-item-head">%s%s</p>' % (" ".join(head), self.status_badge(c.get("status")))]
            if kind == "tv":
                # ひとこと・場所は回の見出し（summary）に出しているので、ここでは動画だけ
                block.append(self.tv_media(c))
            elif kind == "mag":
                text = esc(c.get("excerpt") or c.get("caption") or "")
                if c.get("article") and c.get("status") == "published":
                    text += ' <a class="read-link" href="%s">%sを読む</a>' % (
                        self.href(cur, self.item_url(c)), esc(c.get("badge") or "記事"))
                if text:
                    block.append('<p class="door-text">%s</p>' % text)
            else:
                block.append('<div class="audio-ph"><span class="ph-label">%s</span></div>' % (
                    STATUS.get(c.get("status"), "") or "準備中"))
            out.append('<div class="door-item">\n          %s\n        </div>' % "\n          ".join(block))
        return '<section class="door">\n        %s\n      </section>' % "\n        ".join(out)

    def entry(self, cur, p, e, items, open_=False):
        status = self.episode_status(items)
        lead = items[0] if items else None
        meta = self.entry_meta(e.get("date", ""), self.item_path(lead) if lead else "MA Channel", status, el="span")
        text = [x for x in (e.get("caption"), e.get("text")) if x]
        place = next((c.get("place") for c in items if c.get("place")), "")
        if place:
            text.append("Place: " + place)
        kinds = []
        for k in ("tv", "mag", "radio"):
            ks = [c for c in items if c["kind"] == k]
            if ks:
                kinds.append(self.door_block(cur, k, ks))
        body = "\n      ".join(kinds) or '<p class="pending-note">準備中です。</p>'
        return """    <details class="entry" id="ep-{key}"{open}>
      <summary>
        {meta}
        <span class="entry-title">「{title}」</span>
        {text}<span class="fold-btn" aria-hidden="true"></span>
      </summary>
      <div class="entry-body">
      {body}
      </div>
    </details>""".format(key=esc(e["key"]), open=" open" if open_ else "", meta=meta, title=esc(e["title"]),
                         text=('<span class="entry-text">%s</span>\n        ' % "<br>".join(esc(x) for x in text)) if text else "",
                         body=body)

    # ---------- 各ページ ----------

    def build_home(self):
        cur = "index.html"
        h = lambda t: self.href(cur, t)
        q = self.site["quote"]
        if q.get("lines"):
            quote = "\n".join('    <p>%s</p>' % esc(l) for l in q["lines"])
        else:
            quote = '    <p class="pending-note">%s</p>' % esc(q["pending"])
        gates = []
        for g in self.site["gates"]:
            head = '<span class="gh-no">Gate %s:</span> <strong>%s</strong> / %s' % (esc(g["no"]), esc(g["en"]), esc(g["ja"]))
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
        <p class="toc-head">{head}</p>{doors}
      </li>""".format(dim="" if g["ready"] else " is-dim", head=head,
                      doors=('\n        <ul class="toc-doors">\n          %s\n        </ul>' % "\n          ".join(doors)) if doors else ""))
        news = []
        for n in self.news[:3]:
            title = esc(n["title"])
            if n.get("url"):
                title = '<a href="%s">%s</a>' % (h(n["url"]), title)
            news.append("""      <li class="news-item">
        {meta}
        <p class="news-title">{title}</p>{text}
      </li>""".format(meta=self.entry_meta(n["date"], n["path"]), title=title,
                      text=('\n        <p class="news-text">%s</p>' % esc(n["text"])) if n.get("text") else ""))
        body = """
  <div class="content">
  <h1 class="visually-hidden">{name}</h1>

  <section class="hero" id="top">
    <p class="hero-now">現在、</p>
    <p class="hero-count"><span class="hc-line" aria-hidden="true"></span><span class="hc-num">{visitors}</span></p>
    <p class="hero-text">人が平場に立ちました。</p>
    {figure}
    {arrow1}
  </section>

  <section class="quote" id="quote" aria-label="引用">
{quote}
    <p class="quote-credit">(-{credit})</p>
  </section>

  <div class="hiraba">
    {hiraba}
    {arrow2}
  </div>

  <section class="toc" id="toc">
    {toc_tag}
    <p class="formula"><span>We create of Your MA</span><span>=</span><span>Lab × Ch × Do</span><span class="formula-bar">--------------------</span><span>Notion</span></p>
    {frame}
    <ol class="toc-gates">
{gates}
    </ol>
  </section>

  <section class="news" id="news">
    <div class="news-headrow">
      {news_tag}
      {device}
    </div>
    <ol class="news-list">
{news}
    </ol>
  </section>
  </div>
""".format(name=esc(self.site["name"]), visitors=esc(str(self.site.get("visitors", 1))),
           figure=self.illust(cur, "figure.png", "hero-figure", 321, 1207), arrow1=self.arrow("#quote", "引用へ進む"),
           quote=quote, credit=esc(q["credit"]), hiraba=self.illust(cur, "hiraba.png", "hiraba-illust", 951, 821),
           arrow2=self.arrow("#toc", "目次へ進む"), toc_tag=self.tag("Table of Contents", "b"),
           frame=self.frame("間を巡る 4 つの門と 8 つの扉"), gates="\n".join(gates), news_tag=self.tag("News", "t"),
           device=self.illust(cur, "device.png", "device-illust", 617, 798), news="\n".join(news))
        self.page(cur, None, body, main_class="page home-page")

    def build_notion(self):
        cur = "notion/index.html"
        m = self.manifesto
        n = self.site["notion"]
        chapters = []
        for c in m["chapters"]:
            out = []
            for p in c["paragraphs"]:
                if isinstance(p, dict):
                    out.append('        <div class="manifesto-box">\n%s\n        </div>'
                               % "\n".join("          <p>%s</p>" % esc(l) for l in p["box"]))
                else:
                    out += ['        <p>%s</p>' % esc(l.strip()) for l in p.split("\n") if l.strip()]
            chapters.append("""    <section class="fold chapter" id="ch{no}">
      <h2 class="fold-head">第 {no} 章 : 「{title}」<button class="fold-toggle" type="button" aria-expanded="true" aria-controls="ch{no}-body" aria-label="第 {no} 章を開く・閉じる"></button></h2>
      <div class="fold-body prose" id="ch{no}-body">
{paras}
      </div>
    </section>""".format(no=c["no"], title=esc(c["title"]), paras="\n".join(out)))
        core, steps = n["core"], n["steps"]
        flow = []
        for i, s in enumerate(steps["flow"]):
            flow.append("""        <li class="flow-step fs-{i}">
          <div class="flow-box"><span>Gate {gate}:</span><strong>{en}</strong> <span class="flow-ja">({ja})</span><span>“{verb}”</span></div>
          <ul class="flow-doors">{doors}</ul>
        </li>""".format(i=i, gate=esc(s["gate"]), en=esc(s["en"]), ja=esc(s["ja"]), verb=esc(s["verb"]),
                        doors="".join("<li>%s</li>" % esc(d) for d in s["doors"])))
        body = """
  <div class="content">
    {logo}
    {head}

    <p class="meta-note">「{mtitle}」 / {author}　{version} 版・執筆中のため、内容は書き換わります</p>

{chapters}

    <section class="notion-part" id="core">
      {core_label}
      <div class="part-grid">
        <div class="part-text prose">
          <p>{core_heading}</p>
          <p>{core_lines}</p>
        </div>
        <figure class="spectrum" aria-label="密と間の対比">
          <div class="sp-row">
            <div class="sp-col"><span class="sp-name">密</span><span class="dots dots-dense" aria-hidden="true"></span></div>
            <div class="sp-mid"><span>論理 ⇄ 感覚</span><em>spectrum</em></div>
            <div class="sp-col"><span class="sp-name">間</span><span class="dots dots-sparse" aria-hidden="true"></span></div>
          </div>
          <figcaption>{core_caption}</figcaption>
        </figure>
      </div>
    </section>

    <section class="notion-part" id="steps">
      {steps_label}
      <div class="part-grid">
        <div class="part-text prose">
          <p>{steps_lines}</p>
        </div>
        <figure class="flow" aria-label="間を定める、広める、感化する">
          <div class="flow-root">間｜MA<br>暮らしへの<br>インストール</div>
          <ol class="flow-steps">
{flow}
          </ol>
        </figure>
      </div>
      {book}
    </section>
  </div>
""".format(logo=self.logo(cur, "logo-mark lm-notion"), head=self.gate_head(self.gate("notion")), mtitle=esc(m["title"]),
           author=esc(m["author"]), version=esc(dotted(m["version"])), chapters="\n\n".join(chapters),
           core_label=self.frame(core["label"]), core_heading=esc(core["heading"]), core_lines=brs(core["lines"]),
           core_caption=brs(core["caption"]), steps_label=self.frame(steps["label"]), steps_lines=brs(steps["lines"]),
           flow="\n".join(flow), book=self.illust(cur, "book.png", "book-illust", 341, 375))
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
        intro = "\n".join("      <p>%s</p>" % brs(para) for para in self.site["channel"]["intro"])
        menu = "\n".join('      <li><a href="{url}"><span class="en">{en}</span> / {ja}</a><span class="sub">- {sub} -</span></li>'.format(
            url=h("channel/%s/" % p["slug"]), en=esc(p["en"]), ja=esc(p["ja"]), sub=esc(p["sub"])) for p in self.programs)
        latest = []
        for pf in self.site["platforms"]:
            # 公開済みを先に、その中は日付の新しい順・番号の大きい順。各 Door 3 件まで
            items = sorted((c for c in self.contents if c["kind"] == pf["key"] and not c.get("related")),
                           key=self.latest_key)[:3]
            rows = []
            for c in items:
                p = self.program(c["program"])
                ep = c.get("episode") or c["id"]
                title = '<a href="%s">「%s / %s」 %s</a>' % (h("channel/%s/#ep-%s" % (p["slug"], ep)), esc(p["en"]), esc(p["ja"]), esc(c["title"]))
                text = c.get("caption") or c.get("excerpt") or ""
                rows.append("""        <li class="news-item">
          {meta}
          <p class="news-title">{title}</p>{text}
        </li>""".format(meta=self.entry_meta(self.item_date(c) if c.get("status") == "published" else "",
                                           self.item_path(c), c.get("status")), title=title,
                        text=('\n          <p class="news-text">%s</p>' % esc(text)) if text else ""))
            latest.append("""    <section class="door" id="{key}">
      <h3 class="door-head">Door: {door} <strong>MA Channel / {en}</strong></h3>{blurb}
      <ol class="news-list">
{rows}
      </ol>
    </section>""".format(key=pf["key"], door=esc(pf["door"]), en=esc(pf["en"]),
                         blurb=('\n      <p class="door-blurb">%s</p>' % brs(pf["blurb"])) if pf.get("blurb") else "",
                         rows="\n".join(rows) or '        <li class="pending-note">準備中です。</li>'))
        body = """
  <div class="content">
    {head}

    <div class="intro prose">
{intro}
    </div>

    {logo}
    <section class="channel-menu">
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
""".format(head=self.gate_head(g), intro=intro, logo=self.logo(cur, "logo-mark lm-channel"),
           menu_tag=self.tag("MA Channel Menu", "a"), menu=menu, latest_tag=self.tag("Latest News", "t"),
           latest="\n".join(latest), illust=self.illust(cur, "distribution.png", "distribution-illust", 552, 262))
        self.page(cur, "MA Channel", body)

    def build_programs(self):
        for p in self.programs:
            cur = "channel/%s/index.html" % p["slug"]
            lead = "\n".join("        <p>%s</p>" % brs(para) for para in p.get("lead", [])) or \
                '        <p class="pending-note">番組の紹介文は準備中です。</p>'
            eps = self.episodes(p)
            first_open = next((i for i, (e, items) in enumerate(eps) if self.episode_status(items) == "published"), None)
            entries = "\n\n".join(self.entry(cur, p, e, items, open_=(i == first_open)) for i, (e, items) in enumerate(eps))
            related = [c for c in self.contents if c["program"] == p["slug"] and c.get("related")]
            rel = ""
            if related:
                rel_items = []
                for c in related:
                    rel_items.append('<li class="news-item">%s<p class="news-title">%s%s</p></li>' % (
                        self.entry_meta(self.item_date(c), self.item_path(c), c.get("status")),
                        ('<span class="badge">%s</span> ' % esc(c["badge"])) if c.get("badge") else "", esc(c["title"])))
                rel = """
    <section class="related">
      <h2 class="related-head">関連コンテンツ：{logo}</h2>
      <ul class="news-list">
        {items}
      </ul>
    </section>
""".format(logo=self.logo(cur, "logo-mark lm-related"), items="\n        ".join(rel_items))
            body = """
  <div class="content">
    <div class="program-head">
      <h1 class="ph-title"><span class="en">{en}</span> <span class="ja">/ {ja}</span></h1>
      <p class="ph-sub">- {sub} -</p>
    </div>

    <div class="program-lead">
      <div class="prose">
{lead}
      </div>
      {illust}
    </div>
    {arrow}

    <div class="entries" id="entries">
{entries}
    </div>
{rel}
  </div>
""".format(en=esc(p["en"]), ja=esc(p["ja"]), sub=esc(p["sub"]), lead=lead,
           illust=self.illust(cur, p["illust"], "program-illust") if p.get("illust") else "",
           arrow=self.arrow("#entries", "コンテンツへ進む", "arrow-right"), entries=entries or '    <p class="pending-note">準備中です。</p>',
           rel=rel)
            self.page(cur, "%s / %s" % (p["en"], p["ja"]), body)

    def build_articles(self):
        for item in self.contents:
            if not (item.get("article") and item.get("status") == "published"):
                continue
            cur = self.item_url(item) + "index.html"
            with open(os.path.join(SRC, item["article"]), encoding="utf-8") as f:
                frag = f.read()
            frag = re.sub(r"^<!--.*?-->\n", "", frag, flags=re.S)
            frag = frag.replace('"@/', '"' + self.href(cur, ""))
            # 日付と <NEW> は回の日付から作る（断片に日付を書くと、決まりとずれたまま残るため）
            if ARTICLE_META not in frag:
                raise SystemExit("src/%s: 日付を入れる目印 %s がありません（article-head の中に置く）" % (item["article"], ARTICLE_META))
            frag = frag.replace(ARTICLE_META, self.entry_meta(self.item_date(item), self.item_path(item), item.get("status")))
            p = self.program(item["program"])
            ep = item.get("episode") or item["id"]
            body = """
  <div class="content article">

    <p class="crumb"><a href="{prog}">{en} / {ja}</a> › #{id}</p>

{frag}

    <p class="back-link"><a href="{back}">← {ja} に戻る</a></p>

  </div>
""".format(prog=self.href(cur, "channel/%s/" % p["slug"]), en=esc(p["en"]), ja=esc(p["ja"]), id=esc(item["id"]),
           frag=frag.rstrip("\n"), back=self.href(cur, "channel/%s/#ep-%s" % (p["slug"], ep)))
            self.page(cur, "%s %s" % (item.get("badge", ""), item["title"]), body)
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
    <p class="crumb"><a href="{home}">Home</a> › <a href="{do}">MA Do</a> › Device</p>
    <h1 class="visually-hidden">Device Room</h1>
    <form class="dev-search" role="search" action="#">
      <label class="visually-hidden" for="dev-q">MA Do / Device を検索</label>
      <input id="dev-q" type="search" placeholder="MA Do / Device を検索" autocomplete="off">
      <button type="submit" aria-label="検索"><span class="search-icon" aria-hidden="true"></span></button>
    </form>
    <div class="pills" role="group" aria-label="お店で絞り込む">
      {pills}
    </div>
    <ul class="dev-grid">
{cards}
    </ul>
    <p class="pending-note dev-empty" hidden>該当する商品は、まだ載せていません（順に追加します）。</p>
  </div>
""".format(home=h(""), do=h("do/"), pills="\n      ".join(pills), cards="\n".join(cards))
        self.page(cur, "Device Room", body)

    def build_product(self, prod):
        cur = self.product_url(prod) + "index.html"
        h = lambda t: self.href(cur, t)
        shop = self.shop_of(prod)
        main = prod["variants"][0]
        thumbs = "\n".join('          <li><button class="thumb" type="button" aria-label="%s（%s）の写真を大きく見る"><img src="%s" width="720" height="720" loading="lazy" decoding="async" alt=""></button></li>' % (
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
        qa = "\n".join("        <dt>Q.&ensp;%s</dt>\n        <dd>%s</dd>" % (esc(x["q"]), lines(x["a"])) for x in prod["highlights"])
        specs = "\n".join('        <tr><th scope="row">%s</th><td>%s</td></tr>' % (esc(x["label"]), lines(x["value"])) for x in prod["specs"])
        body = """
  <div class="content wide">
    <p class="crumb"><a href="{home}">Home</a> › <a href="{do}">MA Do</a> › <a href="{dev}">Device</a> › {shop} › {name}</p>
    <div class="product-top">
      <div class="gallery">
        <img class="gallery-main" src="{main}" width="720" height="720" decoding="async" alt="{name}（{color}）">
        <ul class="gallery-thumbs">
{thumbs}
        </ul>
      </div>
      <div class="product-info">
        <p class="pi-shop">{shop}</p>
        <h1 class="pi-name">{name}</h1>
        <p class="pi-label">販売価格：</p>
        <p class="price price-lg">{price}{note}</p>
        <a class="buy-btn" href="{ec}" target="_blank" rel="noopener">ウェブサイトへ移動</a>
        <h2 class="pi-colors-head">color: {colornames}</h2>
        <ul class="pi-colors">
{colors}
        </ul>
      </div>
    </div>

    <section class="product-desc">
      <h2 class="line-head">商品説明</h2>
      <p class="pd-copy">{copy}</p>
      <div class="prose"><p>{body}</p></div>
    </section>

    <section class="features">
{feats}
    </section>

    <section class="product-more">
      <h2 class="line-head">よくあるご質問</h2>
      <dl class="qa">
{qa}
      </dl>
      <h2 class="line-head">仕様</h2>
      <table class="spec">
{specs}
      </table>
      <p><a class="buy-btn" href="{ec}" target="_blank" rel="noopener">{shopname} のウェブサイトへ移動</a></p>
    </section>
  </div>
""".format(home=h(""), do=h("do/"), dev=h("do/device/"), shop=esc(shop["name"]), name=esc(prod["name"]),
           main=esc(h("assets/device/" + main["image"])), color=esc(main["color"]), thumbs=thumbs, price=esc(self.price_label(prod)),
           note=self.tax_label(), ec=esc(prod["ec_url"]),
           colornames=esc(" / ".join(v["color"] for v in prod["variants"])), colors=colors, copy=esc(prod["copy"]),
           body=lines(prod["body"]), feats=feats, qa=qa, specs=specs, shopname=esc(shop["name"]))
        self.page(cur, prod["name"], body)

    def build_company(self):
        cur = "company/index.html"
        c = self.company
        ph = c["photo"]
        chapters = []
        for ch in c["chapters"]:
            chapters.append("""    <section class="fold chapter" id="ch{no}">
      <h2 class="fold-head">第 {no} 章 : 「{title}」<button class="fold-toggle" type="button" aria-expanded="true" aria-controls="ch{no}-body" aria-label="第 {no} 章を開く・閉じる"></button></h2>
      <div class="fold-body prose" id="ch{no}-body">
{paras}
      </div>
    </section>""".format(no=ch["no"], title=esc(ch["title"]), paras="\n".join("        <p>%s</p>" % esc(x) for x in ch["paragraphs"])))
        profile = "\n".join('        <div class="pr-row"><dt>%s :</dt><dd>%s</dd></div>' % (esc(r["label"]), "<br>".join(esc(v) for v in r["value"]))
                            for r in c["profile"])
        fac = "\n".join("""        <li><p class="fac-name">{name}</p><ul>{items}</ul></li>""".format(
            name=esc(f["name"]), items="".join("<li>%s</li>" % esc(x) for x in f["items"])) for f in c["facilities"])
        body = """
  <div class="content">
    <div class="simple-head">
      <h1 class="sh-en">Company</h1>
      <p class="sh-ja">{title}</p>
    </div>
    <img class="company-photo" src="{photo}" width="{w}" height="{h}" decoding="async" alt="{alt}">

{chapters}
    <p class="pending-note">{pending}</p>

    <section class="profile">
      <h2 class="line-head">会社概要</h2>
      <dl class="profile-list">
{profile}
      </dl>
      <p class="fac-label">運営施設 :</p>
      <ul class="facilities">
{fac}
      </ul>
      {logo}
    </section>
  </div>
""".format(title=esc(c["title"]), photo=self.href(cur, "assets/" + ph["src"]), w=ph["width"], h=ph["height"], alt=esc(ph["alt"]),
           chapters="\n\n".join(chapters), pending=esc(c.get("chapters_pending", "")), profile=profile, fac=fac,
           logo=self.logo(cur, "logo-mark lm-company"))
        self.page(cur, "Company", body)

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
      {logo}
    </div>
{groups}
  </div>
""".format(logo=self.logo(cur, "logo-mark lm-contact"), groups="\n\n".join(groups))
        self.page(cur, "Contact us", body)

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
