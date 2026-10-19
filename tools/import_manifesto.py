#!/usr/bin/env python3
"""副社長のマニフェスト（Notion から書き出した docx）を章ごとに分けて src/manifesto.json に書き出す。

使い方:
  python3 tools/import_manifesto.py <Notion_YYYYMMDD.docx> [--out src/manifesto.json]

- 標準ライブラリだけで動く。
- 冒頭の目次（「第0章：「真面目な提案」」の形）から章の題をとる。
- 本文は、最初の段落を第 0 章の見出し、「１．発端」のように番号で始まる段落を各章の見出しとみなして分ける。
- 段落の中の改行はそのまま残す。文には手を入れない。
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


def para_text(p):
    out = []
    for n in p.iter():
        if n.tag == W + "t":
            out.append(n.text or "")
        elif n.tag == W + "br":
            out.append("\n")
        elif n.tag == W + "tab":
            out.append("\t")
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
            paras.append(para_text(child))

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
    for raw in paras:
        text = raw.strip()
        if not text:
            continue
        m = numbered.match(unicodedata.normalize("NFKC", text))
        if current is None:
            current = {"no": toc[0][0], "heading": text, "paragraphs": []}
            chapters.append(current)
            continue
        if m and len(text) <= 20:
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
    chars = sum(len(p) for c in chapters for p in c["paragraphs"])
    print("wrote %s（%d 章・本文 %d 字）" % (a.out, len(chapters), chars))


if __name__ == "__main__":
    sys.exit(main())
