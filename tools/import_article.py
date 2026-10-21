#!/usr/bin/env python3
"""Magazine の原稿（Word）を、記事の断片と contents.json の題・冒頭に写す（原稿といつも合わせるため）。

使い方:
  # 原稿を Google ドキュメントで開き「ファイル → ダウンロード → ウェブページ（.html）」で書き出したものを渡す
  python3 tools/import_article.py <原稿.html> --id 2-2-4 --article src/articles/2-2-4.html \
      --photo "1_1320_Miyajima Photography.jpg=ep224-1.jpg" ... [--alt "ep224-2.jpg=説明"] ...
  python3 tools/import_article.py <原稿.html> --id 2-2-3 --meta-only   # 掲載予定: 題と冒頭だけ
  （--check を付けると書き換えず、ずれだけを出す）

- 標準ライブラリだけで動く。原稿の決まり（まなかの Word のひな形）:
  1 行目に冒頭の写真「(写真: ○○.jpg)」→ 記事の種類（随想記事・編集後記など）→「YYYY/MM/DD MA Magazine/2-2-N」
  → 副題 → Place: / Words: / Photo: → 赤字の「(記事タイトル:)」の次の行が記事のタイトル → 本文。
  本文の太字の行は見出し、「(写真: ○○)」は写真、その次の赤字「（写真キャプション）」に続く行（空行まで）が説明。
  赤字はひな形の指示なので、ページには出さない。最後の行が写真なら、記事の終わりに画面いっぱいに出す写真にする。
- 書くもの:
  --article を付けたとき: 記事の断片（src/articles/）と、contents.json の caption（記事のタイトル）・date（原稿の日付）・
  hero（冒頭の写真）・portrait（終わりの写真）。写真の名前は --photo で原稿の名前 → assets/ の名前に読み替える。
  --meta-only のとき: contents.json の title（記事のタイトル）と excerpt（本文の冒頭 400 字）。
- 原稿の文は手を入れずに写す（誤字らしき所も原稿のまま）。
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTENTS = os.path.join(ROOT, "src", "contents.json")
RED = re.compile(r"color:#(?:ee0000|ff0000|c00000|e00000)", re.I)
PHOTO = re.compile(r"^[(（]\s*写真\s*[:：]\s*(.+?)\s*[)）]$")
DATE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})\s+MA\s+Magazine/(\d+-\d+-\d+)$")


def lines_of(path):
    """Google ドキュメントの HTML 書き出しを、行（文字・太字か・赤字か・リンク）の並びにする。"""
    t = open(path, encoding="utf-8").read()
    css = re.search(r"<style[^>]*>(.*?)</style>", t, re.S)
    cls = {m.group(1): m.group(2) for m in re.finditer(r"\.(c\d+)\{([^}]*)\}", css.group(1) if css else "")}
    body = re.search(r"<body[^>]*>(.*)</body>", t, re.S)
    body = re.sub(r"</(p|h\d|li)>", "\n", body.group(1) if body else t)
    rows, cur = [], {"text": "", "bold": False, "red": False, "links": []}

    def newline():
        rows.append(cur.copy())
        cur.update(text="", bold=False, red=False, links=[])

    for m in re.finditer(r'<span class="([^"]*)"[^>]*>(.*?)</span>|<a [^>]*href="([^"]*)"[^>]*>|(\n)', body, re.S):
        if m.group(4):
            newline()
            continue
        if m.group(3):
            href = html.unescape(m.group(3))
            # Google ドキュメントは外へのリンクを https://www.google.com/url?q=… で包むので、元の URL に戻す
            q = re.match(r"https?://www\.google\.com/url\?q=([^&]+)", href)
            cur["links"].append(urllib.parse.unquote(q.group(1)) if q else href)
            continue
        style = ";".join(cls.get(x, "") for x in m.group(1).split())
        bold, red = "700" in style, bool(RED.search(style))
        parts = re.split(r"<br\s*/?>", m.group(2))
        for i, part in enumerate(parts):
            if i:
                newline()
            text = html.unescape(re.sub(r"<[^>]+>", "", part))
            if text.strip():
                cur["bold"] = cur["bold"] or bold
                cur["red"] = cur["red"] or red
            cur["text"] += text
    newline()
    for r in rows:
        r["text"] = r["text"].replace(" ", " ").rstrip()
    return rows


def parse(rows):
    """ひな形の決まりに沿って、頭（種類・日付・副題・Place など）・記事のタイトル・本文の塊に分ける。"""
    i, n = 0, len(rows)
    skip = lambda: [r for r in rows[i:] if r["text"].strip()]  # noqa: E731
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
    i += 1
    while i < n and not rows[i]["text"].strip():
        i += 1
    doc["title"] = rows[i]["text"].strip() if i < n else ""
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
            flush()
            doc["blocks"].append(("h", t))
        else:
            block.append(r["text"].strip())
        i += 1
    flush()
    if doc["blocks"] and doc["blocks"][-1][0] == "photo":
        doc["portrait"] = doc["blocks"].pop()[1]["name"]
    return doc


def excerpt(doc, limit=400):
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
    out = ["<!-- 元: 原稿「%s」（tools/import_article.py で作成。直すときは原稿を直して作り直す。画像の @/ はサイトの最上位を指す） -->" % e(src_name),
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
    ap.add_argument("source", help="原稿を Google ドキュメントからウェブページ（.html）で書き出したもの")
    ap.add_argument("--id", required=True, help="contents.json の番号（2-2-4 など）")
    ap.add_argument("--article", help="書き出す記事の断片（src/articles/2-2-4.html など）")
    ap.add_argument("--meta-only", action="store_true", help="記事はまだ載せない。contents.json の題と冒頭だけ写す")
    ap.add_argument("--photo", action="append", default=[], help="原稿の写真の名前=assets/ の名前")
    ap.add_argument("--alt", action="append", default=[], help="assets/ の名前=写真の説明（読み上げ用）")
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
        text = fragment(doc, os.path.basename(a.source), photos, alts, sizes)
        old = open(os.path.join(ROOT, a.article), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, a.article)) else ""
        if a.check:
            print(("記事の断片がずれている: " if old != text else "記事の断片は同じ: ") + a.article)
        elif old != text:
            open(os.path.join(ROOT, a.article), "w", encoding="utf-8").write(text)
            print("書いた: " + a.article)
        want["caption"] = doc["title"]
        if doc["date"]:
            want["date"] = doc["date"]
        if doc["hero"]:
            want["hero"] = [photos[doc["hero"]]]
        if doc["portrait"]:
            want["portrait"] = photos[doc["portrait"]]
        want["article"] = os.path.relpath(os.path.join(ROOT, a.article), os.path.join(ROOT, "src"))
        want.pop("excerpt", None)
    changed = {k: (item.get(k), want.get(k)) for k in set(item) | set(want) if item.get(k) != want.get(k)}
    for k, (x, y) in sorted(changed.items()):
        print("%s #%s %s: %r → %r" % ("ずれている" if a.check else "更新", a.id, k, x, y))
    if a.check:
        return 1 if changed else 0
    if changed:
        contents[contents.index(item)] = want
        with open(CONTENTS, "w", encoding="utf-8") as f:
            f.write(json.dumps(contents, ensure_ascii=False, indent=2) + "\n")
        print("src/contents.json を書き換えた。python3 tools/build.py で生成し直す")
    return 0


if __name__ == "__main__":
    sys.exit(main())
