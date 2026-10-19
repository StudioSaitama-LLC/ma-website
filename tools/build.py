#!/usr/bin/env python3
"""src/ のデータから、間｜MA の公開用 HTML を生成する。

使い方:
  python3 tools/build.py          # 生成して上書きする
  python3 tools/build.py --check  # 生成結果と repo のファイルが一致するかだけ確かめる（一致しなければ終了コード 1）

- 標準ライブラリだけで動く（Python 3.9 以上）。
- 生成するのは repo 直下の HTML（GitHub Pages が main の直下をそのまま配信するため）。
  生成したファイルの先頭には「直接編集しない」旨の注記を入れる。直すときは src/ を直してから実行する。
- 生成したファイルの一覧は tools/generated.txt に書く（消えたページを見つけるため）。
"""
import argparse
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


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return html.escape(s or "", quote=True)


def lines(s):
    """改行をそのまま見せる（文に手を入れない）。"""
    return "<br>\n".join(esc(x) for x in (s or "").split("\n"))


def yen(v):
    return "{:,} 円".format(v) if isinstance(v, int) else esc(str(v or ""))


def dotted(d):
    return d.replace("-", ".") if d else ""


class Site:
    def __init__(self):
        self.site = load("site.json")
        self.programs = load("programs.json")
        self.contents = load("contents.json")
        self.device = load("device.json")
        self.manifesto = load("manifesto.json")
        self.pages = {}

    # ---------- 共通部品 ----------

    def href(self, cur, target):
        prefix = "../" * cur.count("/")
        if target == "":
            return prefix or "./"
        return prefix + target

    def nav_label(self, sec):
        no = sec.get("no")
        head = (no + "&ensp;") if no else ""
        return "%s%s / %s" % (head, esc(sec["en"]), esc(sec["ja"]))

    def program(self, slug):
        for p in self.programs:
            if p["slug"] == slug:
                return p
        raise SystemExit("contents.json に未登録の番組: %s" % slug)

    def program_label(self, p):
        return "%s / %s" % (esc(p["en"]), esc(p["ja"]))

    def item_url(self, item):
        return "channel/%s/%s/" % (item["program"], item["id"])

    def header(self, cur):
        s = self.site["sections"]
        h = lambda t: self.href(cur, t)
        menu = [
            '<a href="%s">HOME</a>' % h(""),
            '<a href="%s">%s</a>' % (h("notion/"), self.nav_label(s["notion"])),
            '<span class="dim">%s</span>' % self.nav_label(s["lab"]),
        ]
        menu += ['<span class="menu-child dim">%s</span>' % self.nav_label(c) for c in s["lab"]["children"]]
        menu.append('<a href="%s">%s</a>' % (h("channel/"), self.nav_label(s["channel"])))
        menu += ['<a class="menu-child" href="%s">%s</a>' % (h("channel/%s/" % p["slug"]), self.program_label(p))
                 for p in self.programs]
        menu.append('<a href="%s">%s</a>' % (h("do/"), self.nav_label(s["do"])))
        for c in s["do"]["children"]:
            if c["ready"]:
                menu.append('<a class="menu-child" href="%s">%s</a>' % (h("do/device/"), self.nav_label(c)))
            else:
                menu.append('<span class="menu-child dim">%s</span>' % self.nav_label(c))
        menu += ['<a href="%s">Company / 株式会社まなかについて</a>' % h("company/"),
                 '<a href="%s">Contact us / お問い合わせ</a>' % h("contact/")]
        return """<header class="site-header">
  <div class="header-inner">
    <a class="site-title" href="{home}">{name}</a>
    <div class="header-right">
      <nav class="global-nav">
        <a class="nav-item" href="{notion}">MA Notion</a>
        <span class="nav-item dim">1 MA Lab</span>
        <a class="nav-item" href="{channel}">2 MA Channel</a>
        <a class="nav-item" href="{do}">3 MA Do</a>
      </nav>
      <button class="menu-btn" aria-label="メニューを開く">
        <span></span><span></span><span></span>
      </button>
    </div>
  </div>
</header>

<div class="menu-overlay">
  <nav>
    {menu}
  </nav>
</div>
""".format(home=h(""), name=esc(self.site["name"]), notion=h("notion/"), channel=h("channel/"), do=h("do/"),
           menu="\n    ".join(menu))

    def footer(self, cur):
        h = lambda t: self.href(cur, t)
        f = self.site["follow"]
        podcast = '<a href="%s" target="_blank" rel="noopener">Podcast</a>' % esc(f["podcast"]) if f.get("podcast") else "Podcast"
        return """<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-left">
      <div class="f-title">{name}</div>
      <div>Follow us on <a href="{yt}" target="_blank" rel="noopener">YouTube</a> , {podcast} and <a href="{note}" target="_blank" rel="noopener">note</a>.</div>
      <div class="copyright">©2026, Manaka Ltd.{beta}</div>
    </div>
    <button class="theme-toggle" aria-label="明るさを切り替える">
      <span class="t-label">Light ☀</span><span class="knob"></span>
    </button>
    <div class="footer-links">
      <a href="{company}">Company</a>
      <a href="{contact}">Contact us</a>
    </div>
  </div>
</footer>
""".format(name=esc(self.site["name"]), yt=esc(f["youtube"]), podcast=podcast, note=esc(f["note"]),
           beta=("　" + esc(self.site["beta_note"])) if self.site.get("noindex") else "",
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=Noto+Serif+JP:wght@400;500&family=Roboto+Mono:wght@700&display=swap" rel="stylesheet">
<meta name="description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{name}">
<meta property="og:title" content="{full}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{touch}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="{ico}" sizes="any">
<link rel="icon" type="image/png" href="{png}">
<link rel="apple-touch-icon" href="{touch}">
<link rel="stylesheet" href="{css}">
</head>
<body>

{header}
<main class="{main_class}">
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

    def status(self, item):
        s = STATUS.get(item.get("status", "published"), "")
        return ' <span class="status">%s</span>' % s if s else ""

    def logo(self, cur, deg, style=""):
        return ('<div class="logo-mark" style="transform: rotate(%sdeg);%s">\n'
                '  <img src="%s" width="496" height="512" alt="間｜MA ロゴマーク">\n</div>'
                % (deg, style, self.href(cur, "assets/logo.png")))

    # ---------- 各ページ ----------

    def build_home(self):
        cur = "index.html"
        h = lambda t: self.href(cur, t)
        s = self.site["sections"]
        st = self.site["statement"]
        poem = "\n".join("      <p>%s</p>" % esc(l) for l in st["lines"])
        toc = ['<li class="lv1"><a href="%s">%s</a></li>' % (h("notion/"), self.nav_label(s["notion"]))]
        m = self.manifesto
        toc.append('<li class="sub">- %s / %s -</li>' % (esc(m["title"]), esc(m["author"])))
        toc += ['<li class="lv3"><a href="%s#ch%d">第%d章&ensp;%s</a></li>' % (h("notion/"), c["no"], c["no"], esc(c["title"]))
                for c in m["chapters"]]
        toc.append('<li class="lv1 dim">%s</li>' % self.nav_label(s["lab"]))
        toc += ['<li class="lv2 dim">%s</li>' % self.nav_label(c) for c in s["lab"]["children"]]
        toc.append('<li class="lv1"><a href="%s">%s</a></li>' % (h("channel/"), self.nav_label(s["channel"])))
        for p in self.programs:
            toc.append('<li class="lv2"><a href="%s">%s</a></li>' % (h("channel/%s/" % p["slug"]), self.program_label(p)))
            if p.get("sub"):
                toc.append('<li class="sub">- %s -</li>' % esc(p["sub"]))
        toc.append('<li class="lv1"><a href="%s">%s</a></li>' % (h("do/"), self.nav_label(s["do"])))
        for c in s["do"]["children"]:
            if c["ready"]:
                toc.append('<li class="lv2"><a href="%s">%s</a></li>' % (h("do/device/"), self.nav_label(c)))
                toc.append('<li class="sub">- %s -</li>' % "・".join(esc(d["name"]) for d in self.site["devices"] if d["ready"]))
            else:
                toc.append('<li class="lv2 dim">%s</li>' % self.nav_label(c))
        news = []
        for n in self.site.get("news", []):
            news.append('<li class="lv2">%s&ensp;%s</li>' % (esc(n["date"]), esc(n["title"])))
            if n.get("sub"):
                news.append('<li class="sub">- %s -</li>' % esc(n["sub"]))
        body = """
  <h1 class="visually-hidden">{name}</h1>

  <div class="traffic">
    <span class="label">現在、</span>
    <span class="digits" data-count="2">000000</span>
    <span class="label">人が平場に立ちました。</span>
  </div>

  <div class="content">

    <div class="poem">
{poem}
      <p class="sign">- {sign} -</p>
    </div>

    {logo}

    <h2 class="contents-head">CONTENTS</h2>

    <ol class="toc">
      {toc}
    </ol>

    <h2 class="contents-head">NEWS</h2>

    <ol class="toc">
      {news}
    </ol>

  </div>
""".format(name=esc(self.site["name"]), poem=poem, sign=esc(st["sign"]), logo=self.logo(cur, -6),
           toc="\n      ".join(toc), news="\n      ".join(news))
        self.page(cur, None, body, main_class="page home-page")

    def build_notion(self):
        cur = "notion/index.html"
        sec = self.site["sections"]["notion"]
        m = self.manifesto
        toc = "\n".join('      <li><a href="#ch%d">第%d章&ensp;%s</a></li>' % (c["no"], c["no"], esc(c["title"]))
                        for c in m["chapters"])
        chapters = []
        for c in m["chapters"]:
            # docx では 1 段落の中を改行で区切って書いているため、改行ごとに段落として見せる（文は変えない）
            paras = "\n".join('      <p class="indent">%s</p>' % esc(l.strip())
                              for p in c["paragraphs"] for l in p.split("\n") if l.strip())
            chapters.append("""    <section class="chapter" id="ch{no}">
      <h3 class="chapter-head">第{no}章&ensp;{title}</h3>
      <div class="article-body manifesto-body">
{paras}
      </div>
    </section>""".format(no=c["no"], title=esc(c["title"]), paras=paras))
        last = max(c["no"] for c in m["chapters"])
        body = """
  <div class="content">

    <h1 class="section-head">{label}</h1>

    <div class="lead"><p>{lead}</p></div>

    {logo}

    <div class="manifesto-head">
      <h2 class="manifesto-title">{title}</h2>
      <div class="manifesto-author">{author}</div>
      <div class="manifesto-version">{version} 版・執筆中のため、内容は書き換わります</div>
    </div>

    <ol class="chapter-toc">
{toc}
    </ol>

{chapters}

    <p class="pending-note">第{next}章以降は執筆中です。</p>

  </div>
""".format(label=self.nav_label(sec), lead=esc(sec["lead"]), logo=self.logo(cur, 24), title=esc(m["title"]),
           author=esc(m["author"]), version=esc(dotted(m["version"])), toc=toc, chapters="\n\n".join(chapters),
           next=last + 1)
        self.page(cur, sec["en"], body)

    def tv_card(self, cur, item, show_kind=True):
        if item.get("youtube") and item.get("status") == "published":
            media = ('<iframe class="video-embed" src="https://www.youtube-nocookie.com/embed/%s" title="MA Channel #%s %s" '
                     'loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
                     'picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>'
                     % (esc(item["youtube"]), esc(item["id"]), esc(item["title"])))
        else:
            media = '<div class="video-ph"><span class="play"></span><span class="ph-label">%s</span></div>' % (
                STATUS.get(item.get("status"), "") or "準備中")
        meta = ['<div class="date">#%s%s%s</div>' % (esc(item["id"]),
                                                    ("&ensp;収録 " + esc(dotted(item["recorded"]))) if item.get("recorded") else "",
                                                    self.status(item)),
                '<div class="v-ttl">%s</div>' % esc(item["title"])]
        if item.get("caption"):
            meta.append('<div class="v-cap">%s</div>' % esc(item["caption"]))
        if item.get("place"):
            meta.append('<div class="v-cap">Place&ensp;%s</div>' % esc(item["place"]))
        return """      <div class="video-card">
        {kind}{media}
        <div class="video-meta">
          {meta}
        </div>
        <hr class="dashed">
      </div>""".format(kind=('<div class="kind-label">%s</div>\n        ' % KIND["tv"]) if show_kind else "", media=media,
           meta="\n          ".join(meta))

    def text_card(self, cur, item, show_kind=True):
        kind = ('<div class="kind-label">%s</div>\n        ' % KIND[item["kind"]]) if show_kind else ""
        head = '<div class="date">#%s%s</div>' % (esc(item["id"]), self.status(item))
        title = esc(item["title"])
        if item.get("badge"):
            title = '<span class="badge">%s</span> %s' % (esc(item["badge"]), title)
        parts = [head, '<div class="v-ttl">%s</div>' % title]
        if item.get("caption"):
            parts.append('<div class="v-cap">%s</div>' % esc(item["caption"]))
        if item.get("excerpt"):
            more = ""
            if item.get("article") and item.get("status") == "published":
                more = '<span class="more">・・・<a class="note-btn" href="%s">記事を読む ↗</a></span>' % self.href(cur, self.item_url(item))
            parts.append('<p class="excerpt">%s%s</p>' % (esc(item["excerpt"]), more))
        return """      <div class="text-card">
        {kind}{parts}
        <hr class="dashed">
      </div>""".format(kind=kind, parts="\n        ".join(parts))

    def card(self, cur, item, show_kind=True):
        if item["kind"] == "tv":
            return self.tv_card(cur, item, show_kind)
        return self.text_card(cur, item, show_kind)

    def build_channel(self):
        cur = "channel/index.html"
        h = lambda t: self.href(cur, t)
        sec = self.site["sections"]["channel"]
        progs = []
        for p in self.programs:
            items = [c for c in self.contents if c["program"] == p["slug"]]
            counts = "・".join("%s %d" % (KIND[k], n) for k, n in
                              [(k, sum(1 for c in items if c["kind"] == k)) for k in ("tv", "mag", "radio")] if n)
            progs.append("""      <div class="series-item">
        <div class="series-ttl"><a href="{url}">{label}</a></div>
        <div class="series-sub">{sub}</div>
        <div class="series-count">{counts}</div>
      </div>""".format(url=h("channel/%s/" % p["slug"]), label=self.program_label(p),
                       sub=("- %s -" % esc(p["sub"])) if p.get("sub") else "", counts=esc(counts)))
        platforms = []
        for pf in self.site["platforms"]:
            items = sorted((c for c in self.contents if c["kind"] == pf["key"]),
                           key=lambda c: [int(x) for x in c["id"].split("-")])
            cards = "\n".join(self.card(cur, c, show_kind=False) for c in items) or '      <p class="pending-note">準備中です。</p>'
            platforms.append("""    <h2 class="contents-head" id="{key}">{no}&ensp;{en} / {ja}<span class="via">（{via}）</span></h2>
    <div class="video-list">
{cards}
    </div>""".format(key=pf["key"], no=esc(pf["no"]), en=esc(pf["en"]), ja=esc(pf["ja"]), via=esc(pf["via"]), cards=cards))
        body = """
  <div class="content">

    <h1 class="section-head">{label}</h1>

    <div class="lead"><p>{lead}</p><p>配信プラットフォームごとに並べ、番組ごとにも見られるようにしています。</p></div>

    {logo}

    <h2 class="contents-head">PROGRAMS / 番組</h2>
    <div class="series">
{progs}
    </div>

{platforms}

  </div>
""".format(label=self.nav_label(sec), lead=esc(sec["lead"]), logo=self.logo(cur, 140, " margin-right: 10%;"),
           progs="\n".join(progs), platforms="\n\n".join(platforms))
        self.page(cur, sec["en"], body)

    def build_programs(self):
        for p in self.programs:
            cur = "channel/%s/index.html" % p["slug"]
            items = [c for c in self.contents if c["program"] == p["slug"]]
            main = [c for c in items if not c.get("related")]
            related = [c for c in items if c.get("related")]
            lead = "\n      <div class=\"gap\"></div>\n".join(
                "\n".join("      <p>%s</p>" % esc(l) for l in para) for para in p.get("lead", []))
            if not lead:
                lead = '      <p class="pending-note">番組の紹介文は準備中です。</p>'
            cards = "\n".join(self.card(cur, c) for c in main)
            if related:
                cards += '\n      <div class="related-label">関連コンテンツ：</div>\n' + "\n".join(self.card(cur, c) for c in related)
            body = """
  <div class="content">

    <div class="crumb"><a href="{channel}">2&ensp;MA Channel</a></div>
    <h1 class="section-head">{label}</h1>

    <div class="lead">
{lead}
    </div>

    {logo}

    <div class="video-list">
{cards}
    </div>

  </div>
""".format(channel=self.href(cur, "channel/"), label=self.program_label(p), lead=lead,
           logo=self.logo(cur, 140, " margin-right: 10%;"), cards=cards)
            self.page(cur, p["ja"], body)

    def build_articles(self):
        for item in self.contents:
            if not (item.get("article") and item.get("status") == "published"):
                continue
            cur = self.item_url(item) + "index.html"
            with open(os.path.join(SRC, item["article"]), encoding="utf-8") as f:
                frag = f.read()
            frag = re.sub(r"^<!--.*?-->\n", "", frag, flags=re.S)
            frag = frag.replace('"@/', '"' + self.href(cur, ""))
            p = self.program(item["program"])
            body = """
  <div class="content">

    <div class="crumb"><a href="{prog}">{plabel}</a>&ensp;#{id}</div>

{frag}

    <div class="back-link"><a href="{prog}">← {pja} に戻る</a></div>

  </div>
""".format(prog=self.href(cur, "channel/%s/" % p["slug"]), plabel=self.program_label(p), id=esc(item["id"]),
           frag=frag.rstrip("\n"), pja=esc(p["ja"]))
            self.page(cur, "%s %s" % (item.get("badge", ""), item["title"]), body)
            for old in item.get("redirect_from", []):
                self.redirect(old, self.item_url(item), "#%s %s" % (item["id"], item["title"]))

    def build_do(self):
        s = self.site["sections"]["do"]
        cur = "do/index.html"
        rows = []
        for c in s["children"]:
            if c["ready"]:
                rows.append('<li class="lv2"><a href="%s">%s</a></li>' % (self.href(cur, "do/device/"), self.nav_label(c)))
            else:
                rows.append('<li class="lv2 dim">%s <span class="status">準備中</span></li>' % self.nav_label(c))
        body = """
  <div class="content">
    <h1 class="section-head">{label}</h1>
    <div class="lead"><p>{lead}</p></div>
    {logo}
    <ol class="toc">
      {rows}
    </ol>
  </div>
""".format(label=self.nav_label(s), lead=esc(s["lead"]), logo=self.logo(cur, 60), rows="\n      ".join(rows))
        self.page(cur, s["en"], body)

        cur = "do/device/index.html"
        dev = [c for c in s["children"] if c["en"] == "Device"][0]
        rows = []
        for d in self.site["devices"]:
            if d["ready"]:
                rows.append('<li class="lv2"><a href="%s">%s</a></li>' % (self.href(cur, "do/device/%s/" % d["slug"]), esc(d["name"])))
            else:
                rows.append('<li class="lv2 dim">%s <span class="status">準備中</span></li>' % esc(d["name"]))
        body = """
  <div class="content">
    <div class="crumb"><a href="{do}">3&ensp;MA Do</a></div>
    <h1 class="section-head">{label}</h1>
    <div class="lead"><p>まなかの事業、サービス・プロダクト（仏壇・供養・空間装置）を並べる場所です。</p></div>
    <ol class="toc">
      {rows}
    </ol>
  </div>
""".format(do=self.href(cur, "do/"), label=self.nav_label(dev), rows="\n      ".join(rows))
        self.page(cur, "Device", body)
        self.build_store()

    def build_store(self):
        cur = "do/device/manaka-store/index.html"
        h = lambda t: self.href(cur, t)
        blocks = []
        for p in self.device["products"]:
            skus = "\n".join("""        <li class="sku">
          <img src="{img}" width="720" height="720" loading="lazy" decoding="async" alt="{name}（{color}）">
          <div class="sku-color">{color}</div>
          <div class="sku-price">{price}</div>
        </li>""".format(img=h("assets/device/" + v["image"]), name=esc(p["name"]), color=esc(v["color"]),
                        price=yen(v["price"])) for v in p["variants"])
            qa = "\n".join("        <dt>Q.&ensp;%s</dt>\n        <dd>%s</dd>" % (esc(x["q"]), lines(x["a"])) for x in p["highlights"])
            specs = "\n".join("        <tr><th>%s</th><td>%s</td></tr>" % (esc(x["label"]), lines(x["value"])) for x in p["specs"])
            feats = "\n".join("""      <figure class="feature">
        <img src="{img}" loading="lazy" decoding="async" alt="{alt}">
        <figcaption>
          <h3 class="feature-ttl">{ttl}</h3>
          <p>{body}</p>
        </figcaption>
      </figure>""".format(img=h("assets/device/" + f["image"]), alt=esc(f["title"].replace("\n", "")),
                          ttl=lines(f["title"]), body=lines(f["body"])) for f in p["features"])
            blocks.append("""    <article class="product">
      <div class="product-shop">{shop}&ensp;/&ensp;{cat}</div>
      <h2 class="product-name">{name}</h2>
      <p class="product-copy">{copy}</p>

      <ul class="sku-grid">
{skus}
      </ul>

      <p><a class="buy-btn" href="{ec}" target="_blank" rel="noopener">{shop} で見る・買う ↗</a></p>

      <div class="article-body product-body"><p>{body}</p></div>

      <h3 class="product-sub">よくあるご質問</h3>
      <dl class="qa">
{qa}
      </dl>

      <h3 class="product-sub">仕様</h3>
      <table class="spec">
{specs}
      </table>

      <h3 class="product-sub">特徴</h3>
      <div class="features">
{feats}
      </div>

      <p><a class="buy-btn" href="{ec}" target="_blank" rel="noopener">{shop} で見る・買う ↗</a></p>
    </article>""".format(shop=esc(p["shop"]), cat=esc(p["category"]), name=esc(p["name"]), copy=esc(p["copy"]),
                         skus=skus, ec=esc(p["ec_url"]), body=lines(p["body"]), qa=qa, specs=specs, feats=feats))
        body = """
  <div class="content">
    <div class="crumb"><a href="{dev}">3.2&ensp;Device</a></div>
    <h1 class="section-head">祈りの道具屋まなか</h1>
{blocks}
  </div>
""".format(dev=h("do/device/"), blocks="\n\n".join(blocks))
        self.page(cur, "祈りの道具屋まなか", body)

    def build_simple(self):
        for cur, en, ja in (("company/index.html", "Company", "株式会社まなかについて"),
                            ("contact/index.html", "Contact us", "お問い合わせ")):
            body = """
  <div class="content">
    <h1 class="section-head">{en} / {ja}</h1>
    <p class="pending-note">準備中です。</p>
  </div>
""".format(en=esc(en), ja=esc(ja))
            self.page(cur, en, body)

    def build_redirects(self):
        for old, target, label in (("about.html", "notion/", "MA Notion"),
                                   ("ma-channel.html", "channel/", "MA Channel"),
                                   ("edge-riders.html", "channel/", "MA Channel"),
                                   ("beyond-the-vanishing-point.html", "channel/beyond-the-vanishingpoint/", "死を、教えてくれ。")):
            self.redirect(old, target, label)

    def build(self):
        self.build_home()
        self.build_notion()
        self.build_channel()
        self.build_programs()
        self.build_articles()
        self.build_do()
        self.build_simple()
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
        if bad:
            print("生成結果と違うファイル: " + ", ".join(bad))
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
    stale = sorted(old - set(pages))
    print("wrote %d ファイル" % len(pages))
    if stale:
        print("前回は生成していたが今回は生成しなかったファイル（手で確認して消す）: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    sys.exit(main())
