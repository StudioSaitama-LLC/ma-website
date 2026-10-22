#!/usr/bin/env python3
"""Magazine の原稿（Word）を、記事の断片と contents.json の題・冒頭に写す（原稿といつも合わせるため）。

使い方:
  # 原稿の Word（.docx）をそのまま渡す。Google ドキュメントで開き「ファイル → ダウンロード → ウェブページ（.html）」で
  # 書き出したものも読める
  python3 tools/import_article.py <原稿.docx> --id 2-2-4 --article src/articles/2-2-4.html \
      --photo "1_1320_Miyajima Photography.jpg=ep224-1.jpg" ... [--alt "ep224-2.jpg=説明"] ... [--badge 企画背景]
  python3 tools/import_article.py <原稿.docx> --id 2-2-3 --meta-only   # 掲載予定: 題と冒頭だけ
  （--check を付けると書き換えず、ずれだけを出す）

- 標準ライブラリだけで動く。.docx は zipfile と xml で読み、Word の run の太字（w:b）と文字色（w:color）を
  スタイルの継承（docDefaults → 段落スタイル → 文字スタイル → run の直接の指定）も含めて見る。
  改行（w:br）と段落の終わりで行を分ける。図の文字枠と、古いソフト向けの予備（mc:Fallback）・削除の履歴（w:del）は読まない。
  原稿の決まり（まなかの Word のひな形）:
  1 行目に冒頭の写真「(写真: ○○.jpg)」→ 記事の種類（随想記事・編集後記など）→「YYYY/MM/DD MA Magazine/2-2-N」
  → 副題 → Place: / Words: / Photo: → 赤字の「(記事タイトル:)」の次の行が記事のタイトル → 本文。
  本文の太字の行は見出し、「(写真: ○○)」は写真、その次の赤字「（写真キャプション）」に続く行（空行まで）が説明。
  赤字はひな形の指示なので、ページには出さない。最後の行が写真なら、記事の終わりに画面いっぱいに出す写真にする。
- 書くもの:
  --article を付けたとき: 記事の断片（src/articles/）と、contents.json の caption（記事のタイトル）・date（原稿の日付）・
  hero（冒頭の写真）・portrait（終わりの写真）・words（Words: の書き手）。写真の名前は --photo で原稿の名前 → assets/ の
  名前に読み替える。記事の種類は原稿のものを出す（サイトの分け方と違うときは --badge で contents.json の badge に揃える）。
  --meta-only のとき: contents.json の title（記事のタイトル）と excerpt（本文の冒頭 230 字＝PC の 4 行ぶん）。
- 原稿の文は手を入れずに写す（誤字らしき所も原稿のまま）。
"""
import argparse
import html
import json
import os
import re
import sys
import stat
import tempfile
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTENTS = os.path.join(ROOT, "src", "contents.json")
BOLD = re.compile(r"font-weight\s*:\s*(?:[6-9]00|bold)", re.I)
PHOTO = re.compile(r"^[(（]\s*写真\s*[:：]\s*(.+?)\s*[)）]$")
DATE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})\s+MA\s+Magazine/(\d+-\d+-\d+)$")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
HYPERLINK = re.compile(r'HYPERLINK\s+(?:\\[a-z]\s+)*"([^"]+)"')


def make_row(segs, links):
    """行の文字の断片（文字・太字か・赤字か）とリンクから、行を作る（HTML と Word で同じ決まり）。"""
    text = "".join(t for t, _, _ in segs)
    visible = [(b, r) for t, b, r in segs if t.strip()]
    # 太字・赤字は、行の文字がすべてそうなときだけ（一部だけ太字の本文を見出しにしない・一部だけ赤字の本文を落とさない）
    return {"text": text.replace("\u00a0", " ").rstrip(),
            "bold": bool(visible) and all(b for b, _ in visible),
            "red": bool(visible) and all(r for _, r in visible),
            "partly_red": any(r for _, r in visible) and not all(r for _, r in visible),
            "links": list(links)}


class _Reader(HTMLParser):
    """本文の HTML を、行（文字・太字か・赤字か・リンク）の並びにする。class の無い文字も、リンクの中の文字も拾う。"""

    BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "tr"}

    def __init__(self, cls):
        super().__init__(convert_charrefs=True)
        self.cls, self.styles, self.href, self.skip = cls, [], None, 0
        self.rows, self.segs, self.links = [], [], []

    def _style(self, attrs):
        a = dict(attrs)
        return ";".join(self.cls.get(x, "") for x in (a.get("class") or "").split()) + ";" + (a.get("style") or "")

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        elif tag == "br":
            self.newline()
        elif tag == "span":
            self.styles.append(self._style(attrs))
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            # Google ドキュメントは外へのリンクを https://www.google.com/url?q=… で包むので、元の URL に戻す
            q = re.match(r"https?://www\.google\.com/url\?q=([^&]+)", href)
            self.href = urllib.parse.unquote(q.group(1)) if q else href
            # ページに出すのは http(s) のリンクだけ（Google の内部のしおり・mailto・javascript などは出さない）
            if re.match(r"https?://", self.href or ""):
                self.links.append(self.href)

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.newline()

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        elif tag == "span" and self.styles:
            self.styles.pop()
        elif tag == "a":
            self.href = None
        elif tag in self.BLOCKS:
            self.newline()

    def handle_data(self, data):
        if self.skip:
            return
        style = ";".join(self.styles)
        self.segs.append((data, bool(BOLD.search(style)), is_red(style)))

    def newline(self):
        self.rows.append(make_row(self.segs, self.links))
        self.segs, self.links = [], []


def is_red(style):
    """色の指定が赤か（赤が強く、緑と青が弱い）。"""
    for m in re.finditer(r"(?<![-\w])color\s*:\s*#([0-9a-f]{6}|[0-9a-f]{3})\b", style, re.I):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if r >= 0xA0 and g <= 0x60 and b <= 0x60:
            return True
    return False


def lines_of(path):
    """原稿（Word の .docx か、Google ドキュメントの HTML 書き出し）を、行（文字・太字か・赤字か・リンク）の並びにする。"""
    if zipfile.is_zipfile(path):
        return docx_lines(path)
    t = open(path, encoding="utf-8").read()
    css = re.search(r"<style[^>]*>(.*?)</style>", t, re.S)
    cls = {m.group(1): m.group(2) for m in re.finditer(r"\.([A-Za-z_][\w-]*)\{([^}]*)\}", css.group(1) if css else "")}
    body = re.search(r"<body[^>]*>(.*)</body>", t, re.S)
    rd = _Reader(cls)
    rd.feed(body.group(1) if body else t)
    rd.close()
    rd.newline()
    return rd.rows


def _rpr_props(rpr):
    """run の書式（w:rPr）のうち、太字と文字色の指定だけを取り出す（指定の無いものは入れない）。"""
    out = {}
    if rpr is None:
        return out
    b = rpr.find(W + "b")
    if b is not None:
        # <w:b/> と <w:b w:val="1|true|on"/> は太字、<w:b w:val="0|false|off"/> は太字を外す
        out["bold"] = (b.get(W + "val") or "true").lower() in ("1", "true", "on")
    c = rpr.find(W + "color")
    if c is not None:
        out["color"] = c.get(W + "val") or "auto"
    return out


class _DocxStyles:
    """styles.xml の既定（docDefaults）と、スタイルの継承（basedOn）をたどった太字・文字色。"""

    def __init__(self, z):
        self.base, self.styles, self.default = {"bold": False, "color": "auto"}, {}, {}
        try:
            root = ET.fromstring(z.read("word/styles.xml"))
        except KeyError:
            return
        self.base.update(_rpr_props(root.find(W + "docDefaults/" + W + "rPrDefault/" + W + "rPr")))
        for s in root.findall(W + "style"):
            based = s.find(W + "basedOn")
            self.styles[s.get(W + "styleId")] = (based.get(W + "val") if based is not None else None, s.find(W + "rPr"))
            if s.get(W + "default") in ("1", "true"):
                self.default[s.get(W + "type")] = s.get(W + "styleId")

    def resolve(self, sid, seen=()):
        if not sid or sid not in self.styles or sid in seen:
            return {}
        based, rpr = self.styles[sid]
        out = self.resolve(based, seen + (sid,))
        out.update(_rpr_props(rpr))
        return out

    def paragraph(self, p):
        """段落の書式の土台（既定 → 段落スタイル）。"""
        ppr = p.find(W + "pPr")
        ps = ppr.find(W + "pStyle") if ppr is not None else None
        out = dict(self.base)
        out.update(self.resolve(ps.get(W + "val") if ps is not None else self.default.get("paragraph")))
        return out

    def run(self, para, r):
        """run の書式（段落の土台 → 文字スタイル → run の直接の指定）。"""
        rpr = r.find(W + "rPr")
        rs = rpr.find(W + "rStyle") if rpr is not None else None
        out = dict(para)
        out.update(self.resolve(rs.get(W + "val") if rs is not None else self.default.get("character")))
        out.update(_rpr_props(rpr))
        return out


class _DocxReader:
    """document.xml の本文を、HTML の読みと同じ行（文字・太字か・赤字か・リンク）の並びにする。"""

    def __init__(self, z):
        self.styles = _DocxStyles(z)
        self.rels = {}
        try:
            for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
                if r.get("TargetMode") == "External":
                    self.rels[r.get("Id")] = r.get("Target") or ""
        except KeyError:
            pass
        self.rows, self.segs, self.links, self.fields, self.skipped_boxes = [], [], [], [], 0

    def newline(self):
        self.rows.append(make_row(self.segs, self.links))
        self.segs, self.links = [], []

    def link(self, href):
        # ページに出すのは http(s) のリンクだけ（文書の中のしおり・mailto などは出さない）
        if re.match(r"https?://", href or ""):
            self.links.append(href)

    def blocks(self, node):
        """本文の段落を順に読む（表は行・枡の順に、内容の枠 w:sdt などは中身を読む）。"""
        for child in node:
            if child.tag == W + "p":
                self.paragraph(child)
            elif child.tag == W + "tbl":
                for tr in child.findall(W + "tr"):
                    for tc in tr.findall(W + "tc"):
                        self.blocks(tc)
            elif child.tag in (W + "sdt", W + "sdtContent", W + "customXml", W + "ins", W + "moveTo", MC + "AlternateContent", MC + "Choice"):
                self.blocks(child)

    def paragraph(self, p):
        self.inline(p, self.styles.paragraph(p))
        self.newline()

    def inline(self, node, para):
        for child in node:
            tag = child.tag
            if tag == W + "r":
                self.run(child, para)
            elif tag == W + "hyperlink":
                if child.get(REL + "id") in self.rels:
                    self.link(self.rels[child.get(REL + "id")])
                self.inline(child, para)
            elif tag == W + "fldSimple":
                m = HYPERLINK.search(child.get(W + "instr") or "")
                if m:
                    self.link(m.group(1))
                self.inline(child, para)
            elif tag in (W + "del", W + "moveFrom", MC + "Fallback", W + "pPr", W + "rPr", W + "sdtPr", W + "sdtEndPr"):
                continue  # 削除の履歴・古いソフト向けの予備・書式は読まない
            else:
                self.inline(child, para)  # w:ins・w:smartTag・w:sdt・w:sdtContent など、中身を読む

    def run(self, r, para):
        props = self.styles.run(para, r)
        color = props.get("color") or "auto"
        bold, red = bool(props.get("bold")), bool(re.fullmatch(r"[0-9A-Fa-f]{6}", color)) and is_red("color:#" + color)
        for c in r:
            tag = c.tag
            if tag == W + "t":
                if not (self.fields and self.fields[-1]["in_code"]):
                    self.segs.append((c.text or "", bold, red))
            elif tag in (W + "br", W + "cr"):
                self.newline()
            elif tag in (W + "tab", W + "ptab"):
                self.segs.append(("\t", bold, red))
            elif tag == W + "noBreakHyphen":
                self.segs.append(("-", bold, red))
            elif tag == W + "ruby":
                base = c.find(W + "rubyBase")  # ふりがな（w:rt）は読まず、親文字だけ
                if base is not None:
                    self.inline(base, para)
            elif tag == W + "fldChar":
                kind = c.get(W + "fldCharType")
                if kind == "begin":
                    self.fields.append({"code": "", "in_code": True})
                elif kind == "separate" and self.fields:
                    self.fields[-1]["in_code"] = False
                    m = HYPERLINK.search(self.fields[-1]["code"])
                    if m:
                        self.link(m.group(1))
                elif kind == "end" and self.fields:
                    self.fields.pop()
            elif tag == W + "instrText":
                if self.fields:
                    self.fields[-1]["code"] += c.text or ""
            elif tag in (W + "drawing", W + "pict", MC + "AlternateContent", W + "object"):
                if any((t.text or "").strip() for t in c.iter(W + "t")):
                    self.skipped_boxes += 1


def docx_lines(path):
    """Word の .docx を、行（文字・太字か・赤字か・リンク）の並びにする。"""
    z = zipfile.ZipFile(path)
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    rd = _DocxReader(z)
    if body is not None:
        rd.blocks(body)
    if rd.segs:
        rd.newline()
    if rd.skipped_boxes:
        print("注意: 図の中の文字（文字枠）が %d つあり、取り込んでいない（本文に要るなら原稿の本文に移す）" % rd.skipped_boxes, file=sys.stderr)
    return rd.rows


def parse(rows):
    """ひな形の決まりに沿って、頭（種類・日付・副題・Place など）・記事のタイトル・本文の塊に分ける。"""
    i, n = 0, len(rows)
    doc = {"hero": None, "badge": "", "date": "", "number": "", "subtitle": "", "cred": [], "title": "", "blocks": [], "portrait": None}
    while i < n and not rows[i]["text"].strip():
        i += 1
    m = PHOTO.match(rows[i]["text"].strip()) if i < n else None
    if m:
        doc["hero"] = m.group(1)
        i += 1
    head = []
    while i < n and not (rows[i]["red"] and "記事タイトル" in rows[i]["text"]):
        if rows[i]["text"].strip():
            head.append(rows[i]["text"].strip())
        i += 1
    if i >= n:
        raise SystemExit("原稿に赤字の「(記事タイトル:)」が無い（ひな形と違う）")
    for h in head:
        d = DATE.match(h)
        if d:
            doc["date"], doc["number"] = "%s-%s-%s" % d.group(1, 2, 3), d.group(4)
        elif re.match(r"(Place|Words|Photo)\s*:", h):
            if h.split(":", 1)[1].strip():
                doc["cred"].append(h)
        elif not doc["badge"]:
            doc["badge"] = h
        elif not doc["subtitle"]:
            doc["subtitle"] = h
    if not doc["date"]:
        raise SystemExit("原稿の頭に「YYYY/MM/DD MA Magazine/2-2-N」の行が読めない（全角の / などで崩れていないか）: %r" % head)
    i += 1
    while i < n and not rows[i]["text"].strip():
        i += 1
    doc["title"] = rows[i]["text"].strip() if i < n else ""
    if not doc["title"]:
        raise SystemExit("「(記事タイトル:)」の次の行に記事のタイトルが無い")
    i += 1
    # 本文: 空行で塊に分ける。太字の行は見出し、写真の行は写真（直後の赤字「写真キャプション」から空行までが説明）
    block = []
    def flush():
        if block:
            doc["blocks"].append(("p", [x for x in block]))
            block.clear()
    while i < n:
        r = rows[i]
        t = r["text"].strip()
        pm = PHOTO.match(t)
        if not t:
            flush()
        elif pm:
            flush()
            # 写真の直後: 赤字の「（写真キャプション）」の行（指示）のあと、空行までが説明。
            # 「（写真キャプション： 説明 …）」のように括弧の中に説明を書いた形（複数行でもよい）も読む
            cap, links, j, marked, inside = [], [], i + 1, False, False
            while j < n and rows[j]["text"].strip():
                ct = rows[j]["text"].strip()
                head = re.match(r"^[(（]\s*写真キャプション\s*[:：]?\s*", ct)
                if head:
                    marked = True
                    ct = ct[head.end():]
                    inside = not re.fullmatch(r"[)）]?", ct)
                    if not inside:
                        ct = ""
                elif not marked:
                    break
                if inside and re.search(r"[)）]$", ct):
                    ct, inside = ct[:-1].rstrip(), False
                if re.fullmatch(r"https?://\S+", ct):
                    links.append(ct)
                elif ct:
                    cap.append(ct)
                links += rows[j]["links"]
                j += 1
            doc["blocks"].append(("photo", {"name": pm.group(1), "caption": cap, "links": list(dict.fromkeys(links))}))
            i = j
            continue
        elif r["red"]:
            pass  # ひな形の指示（ページには出さない）
        elif r["bold"]:
            if r.get("partly_red"):
                print("注意: 一部だけ赤字の見出し（ひな形の指示か本文か確かめる）: %s" % t[:60], file=sys.stderr)
            flush()
            doc["blocks"].append(("h", t))
        elif r.get("partly_red"):
            print("注意: 一部だけ赤字の行（ひな形の指示か本文か確かめる）: %s" % t[:60], file=sys.stderr)
            block.append(t)
        else:
            block.append(r["text"].strip())
        i += 1
    flush()
    if doc["blocks"] and doc["blocks"][-1][0] == "photo":
        doc["portrait"] = doc["blocks"].pop()[1]["name"]
    return doc


def excerpt(doc, limit=230):
    out = ""
    for kind, v in doc["blocks"]:
        if kind == "p":
            for line in v:
                if out and not re.search(r"[。．！？!?」』）)…]$", out):
                    out += " "
                out += line
        if len(out) >= limit:
            break
    return out[:limit]


def fragment(doc, src_name, photos, alts, sizes):
    e = lambda s: html.escape(s, quote=True)  # noqa: E731
    out = ["<!-- 元: #%s の原稿（Word）。tools/import_article.py で作成。直すときは原稿を直して作り直す。画像の @/ はサイトの最上位を指す -->" % e(src_name),
           '    <div class="article-head">']
    if doc["badge"]:
        out.append('      <span class="badge">%s</span>' % e(doc["badge"]))
    out.append("      <!-- build:meta -->")
    out.append('      <h1 class="article-title">%s</h1>' % e(doc["subtitle"]))
    if doc["cred"]:
        out.append('      <div class="article-cred">')
        out += ['        <div>%s</div>' % e(c) for c in doc["cred"]]
        out.append("      </div>")
    out.append("    </div>")
    out.append("")
    out.append('    <h2 class="article-answer">%s</h2>' % e(doc["title"]))
    paras = []

    def close():
        if paras:
            out.append("")
            out.append('    <div class="article-body">')
            out.extend("      <p>%s</p>" % "<br>\n      ".join(e(x) for x in p) for p in paras)
            out.append("    </div>")
            paras.clear()
    for kind, v in doc["blocks"]:
        if kind == "p":
            paras.append(v)
            continue
        close()
        out.append("")
        if kind == "h":
            out.append('    <h2 class="article-answer">%s</h2>' % e(v))
        else:
            name = photos.get(v["name"])
            if not name:
                raise SystemExit("--photo に原稿の写真「%s」の読み替えが無い" % v["name"])
            w, h = sizes[name]
            cap = "<br>".join(e(c) for c in v["caption"])
            for link in v["links"]:
                cap += ('<br>' if cap else "") + '<a href="%s" target="_blank" rel="noopener">%s</a>' % (e(link), e(link))
            out.append('    <figure class="article-figure">')
            out.append('      <img class="article-photo" src="@/assets/%s" width="%d" height="%d" loading="lazy" decoding="async" alt="%s">'
                       % (e(name), w, h, e(alts.get(name, ""))))
            if cap:
                out.append("      <figcaption>%s</figcaption>" % cap)
            out.append("    </figure>")
    close()
    return "\n".join(out) + "\n"


def write_atomic(path, text):
    """同じフォルダの一時ファイルに書いてから置き換える（元の権限を保つ）。"""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".import-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if os.path.exists(path):
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
        else:
            # mkstemp は 0600 で作るので、新しいファイルはふつうの権限（umask に従う 0666）にする
            mask = os.umask(0)
            os.umask(mask)
            os.chmod(tmp, 0o666 & ~mask)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def image_size(path):
    """JPEG / PNG の幅と高さ（標準ライブラリだけで読む）。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    raise SystemExit("画像の大きさが読めない: %s" % path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="原稿の Word（.docx）か、Google ドキュメントからウェブページ（.html）で書き出したもの")
    ap.add_argument("--id", required=True, help="contents.json の番号（2-2-4 など）")
    ap.add_argument("--article", help="書き出す記事の断片（src/articles/2-2-4.html など）")
    ap.add_argument("--meta-only", action="store_true", help="記事はまだ載せない。contents.json の題と冒頭だけ写す")
    ap.add_argument("--photo", action="append", default=[], help="原稿の写真の名前=assets/ の名前")
    ap.add_argument("--alt", action="append", default=[], help="assets/ の名前=写真の説明（読み上げ用）")
    ap.add_argument("--badge", help="原稿の記事の種類の代わりに出す種類（サイトの分け方＝contents.json の badge に揃えるとき）")
    ap.add_argument("--check", action="store_true", help="書き換えず、ずれだけを出す")
    a = ap.parse_args()
    doc = parse(lines_of(a.source))
    if doc["number"] and doc["number"] != a.id:
        raise SystemExit("原稿の番号 %s と --id %s が違う" % (doc["number"], a.id))
    with open(CONTENTS, encoding="utf-8") as f:
        contents = json.load(f)
    item = next((c for c in contents if c.get("id") == a.id), None)
    if not item:
        raise SystemExit("contents.json に #%s が無い" % a.id)
    if a.badge:
        doc["badge"] = a.badge
    elif item.get("badge") and doc["badge"] != item["badge"]:
        print("注意: 原稿の記事の種類「%s」と contents.json の badge「%s」が違う（揃えるなら --badge）" % (doc["badge"], item["badge"]), file=sys.stderr)
    want = dict(item)
    if a.meta_only:
        want["title"] = doc["title"]
        want["excerpt"] = excerpt(doc)
    else:
        if not a.article:
            raise SystemExit("--article か --meta-only のどちらかを付ける")
        photos = dict(x.split("=", 1) for x in a.photo)
        alts = dict(x.split("=", 1) for x in a.alt)
        sizes = {n: image_size(os.path.join(ROOT, "assets", n)) for n in photos.values()}
        missing = [x for x in [doc["hero"], doc["portrait"]] + [v["name"] for k, v in doc["blocks"] if k == "photo"] if x and x not in photos]
        if missing:
            raise SystemExit("--photo に原稿の写真の読み替えが無い（何も書いていない）: " + "、".join(missing))
        text = fragment(doc, a.id, photos, alts, sizes)
        old = open(os.path.join(ROOT, a.article), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, a.article)) else ""
        drift = old != text
        if a.check:
            print(("記事の断片がずれている: " if drift else "記事の断片は同じ: ") + a.article)
        elif drift:
            write_atomic(os.path.join(ROOT, a.article), text)
            print("書いた: " + a.article)
        want["caption"] = doc["title"]
        if doc["date"]:
            want["date"] = doc["date"]
        if doc["hero"]:
            want["hero"] = [photos[doc["hero"]]]
        if doc["portrait"]:
            want["portrait"] = photos[doc["portrait"]]
        words = [c.split(":", 1)[1].strip() for c in doc["cred"] if re.match(r"Words\s*:", c)]
        if words:
            want["words"] = words[0]
        want["article"] = os.path.relpath(os.path.join(ROOT, a.article), os.path.join(ROOT, "src"))
        want.pop("excerpt", None)
    changed = {k: (item.get(k), want.get(k)) for k in set(item) | set(want) if item.get(k) != want.get(k)}
    for k, (x, y) in sorted(changed.items()):
        print("%s #%s %s: %r → %r" % ("ずれている" if a.check else "更新", a.id, k, x, y))
    if a.check:
        return 1 if (changed or (not a.meta_only and drift)) else 0
    if changed:
        contents[contents.index(item)] = want
        write_atomic(CONTENTS, json.dumps(contents, ensure_ascii=False, indent=2) + "\n")
        print("src/contents.json を書き換えた。python3 tools/build.py で生成し直す")
    return 0


if __name__ == "__main__":
    sys.exit(main())
