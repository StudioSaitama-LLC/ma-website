#!/usr/bin/env python3
"""副社長のマニフェスト（Notion から書き出した docx）を章ごとに分けて src/manifesto.json に書き出す。

使い方:
  python3 tools/import_manifesto.py <Notion_YYYYMMDD.docx> [--out src/manifesto.json]

- 標準ライブラリだけで動く。
- 冒頭の目次（「第0章：「真面目な提案」」の形）から章の題をとる。
- 本文は、最初の段落を第 0 章の見出し、「１．発端」のように番号で始まる段落を各章の見出しとみなして分ける。
- 段落の中の改行はそのまま残す。文には手を入れない。
- 図の中の文字枠は {"box": [行, ...]} として、その図がある段落の直後に置く。表は取り込まず、注意を出す。
"""
import argparse
import datetime
import json
import os
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


def walk(node, out, boxes):
    """段落の文字を集める。

    - 図の文字枠（w:txbxContent）は本文に混ぜず、boxes に枠ごとの段落の並びとして分けて返す。
    - Word は同じ図を新しい形式（mc:Choice）と古いソフト向けの予備（mc:Fallback）の 2 回書くので、
      予備の側は読まない（読むと文が 2 回出る）。
    """
    for child in node:
        if child.tag == MC + "Fallback":
            continue
        if child.tag == W + "txbxContent":
            boxes.append([para_text(p) for p in child.findall(W + "p")])
            continue
        if child.tag == W + "t":
            out.append(child.text or "")
        elif child.tag == W + "br":
            out.append("\n")
        elif child.tag == W + "tab":
            out.append("\t")
        else:
            walk(child, out, boxes)


def para_text(p, boxes=None):
    out = []
    walk(p, out, boxes if boxes is not None else [])
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "src", "manifesto.json"))
    a = ap.parse_args()
    body = ET.fromstring(zipfile.ZipFile(a.docx).read("word/document.xml")).find(W + "body")

    toc_lines, paras = [], []
    for child in body:
        if child.tag == W + "sdt":
            toc_lines += [para_text(p).strip() for p in child.iter(W + "p")]
        elif child.tag == W + "p":
            boxes = []
            paras.append(para_text(child, boxes))
            for box in boxes:
                lines_ = [x.strip() for x in box if x.strip()]
                if lines_:
                    paras.append({"box": lines_})
        elif child.tag == W + "tbl":
            print("注意: 表が 1 つあり、取り込んでいません（必要なら手で src/manifesto.json に足す）", file=sys.stderr)

    title, author, toc = "", "", []
    for line in toc_lines:
        m = re.match(r"^第(\d+)章：「(.+)」$", line)
        if m:
            toc.append((int(m.group(1)), m.group(2)))
        elif "/" in line and not title:
            title, author = [x.strip() for x in line.split("/", 1)]
    if not toc:
        raise SystemExit("目次（第N章：「…」）が見つかりません")

    chapters, current = [], None
    numbered = re.compile(r"^\s*([0-9]+)[.．]\s*(.*)$")
    toc_numbers = set(n for n, _ in toc)
    for raw in paras:
        if isinstance(raw, dict):
            if current is not None:
                current["paragraphs"].append(raw)
            continue
        text = raw.strip()
        if not text:
            continue
        m = numbered.match(unicodedata.normalize("NFKC", text))
        if current is None:
            current = {"no": toc[0][0], "heading": text, "paragraphs": []}
            chapters.append(current)
            continue
        # 見出しとみなすのは「次の章番号」で始まり、目次にある番号の短い段落だけ（本文中の「2. 〜」の箇条と区別する）
        if m and len(text) <= 20 and int(m.group(1)) == current["no"] + 1 and int(m.group(1)) in toc_numbers:
            current = {"no": int(m.group(1)), "heading": text, "paragraphs": []}
            chapters.append(current)
            continue
        current["paragraphs"].append(raw.strip("\n"))

    titles = dict(toc)
    for ch in chapters:
        ch["title"] = titles.get(ch["no"], ch["heading"])
    m = re.search(r"(\d{4})(\d{2})(\d{2})", os.path.basename(a.docx))
    version = "%s-%s-%s" % m.groups() if m else datetime.date.today().isoformat()
    out = {
        "title": title,
        "author": author,
        "version": version,
        "source": os.path.basename(a.docx),
        "chapters": [{"no": c["no"], "title": c["title"], "heading": c["heading"],
                      "paragraphs": c["paragraphs"]} for c in chapters],
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    chars = sum(len(p) if isinstance(p, str) else sum(len(x) for x in p["box"])
                for c in chapters for p in c["paragraphs"])
    print("wrote %s（%d 章・本文 %d 字）" % (a.out, len(chapters), chars))


if __name__ == "__main__":
    sys.exit(main())
