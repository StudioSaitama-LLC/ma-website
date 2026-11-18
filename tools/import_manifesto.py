#!/usr/bin/env python3
"""副社長の MA Notion（Word の docx）を章ごとに分けて src/manifesto.json に書き出す。

使い方:
  python3 tools/import_manifesto.py <About 間 宮嶋孝尚 YYYY／MM／DD.docx> [--out src/manifesto.json]

- 文字の取り込みは標準ライブラリだけで動く。埋め込み画像の PNG 変換には macOS の sips を使う。
- 冒頭の目次から章の題をとる。目次の形は 2 つ読める。
  10/22 版から: 「|Notion」「|感じぬ人」「|2026-10-16」「|宮嶋 孝尚」の後に「0.真面目な提案」…（題の無い「4.」などは飛ばす）
  10/16 版まで: 「感じぬ人 / 宮嶋 孝尚」の後に「第0章：「真面目な提案」」…
- 本文は、最初の段落を第 0 章の見出し、「1.旅のはじまり」「３．おおよそ」のように番号で始まる段落を各章の見出しとみなして分ける。
  見出しは目次の題で「0. 真面目な提案」の形（半角の数字・点・空白）にそろえる（10/22 まなかの指示）。
- 段落の中の改行はそのまま残す。文には手を入れない。ただし FIXES に書いた直しだけは当てる（当たらなければ止める）。
- 図の中の文字枠は {"box": [行, ...]} として、その図がある段落の直後に置く。表は取り込まず、注意を出す。
- 埋め込み画像は本文の順で {"figure": "figures/notion-章-番号.png", "alt": "説明"} にし、撮影情報を除いて assets/ に置く。
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import posixpath
import re
import struct
import subprocess
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
ROOT = Path(__file__).resolve().parent.parent

# 原稿に当てる直し（段落の終わりの文字列 → 置き換え）。まなかの指示があったものだけ書く。
# 当たる段落がちょうど 1 つでなければ止める（原稿が替わったら見直す）。
# 11/17 版では該当の一節が書き直されたため、10/22 版の末尾「ｆ」の直しを外した。
FIXES = []

# 本文の図番号に対応する説明。Word 内部の図の名前・番号は使わない。
FIGURE_ALTS = {
    5: [
        "人から Step1 情報、新たな行動原理を経て Step2 処理・Step3 目的・Step4 行動・Step5 成果へ進む流れ",
        "人から Step1 情報、感ずる行動原理を経て Step2 感受・Step3 感情・Step4 行動・Step5 受容へ進む流れ",
        "突然の雨という同じ情報が、思考の岐路で 2 つに分かれる。新たな行動原理は 雨雲が深い→濡れずに帰社→天気・コンビニ・路線を調べる→予定どおり帰社、感ずる行動原理は あの日の雨に似ている→切なくどこか懐かしい→雨宿りしてぼーっとする→少し身軽な心持ちで帰社",
        "1980 年から 2020 年まで 10 年ごとの棒グラフ。感ずる・その他・新たな、の行動原理の割合の移り変わりと、インターネット・スマートフォン・SNS・クラウド・AI の登場。新たな行動原理が年を追って増える",
    ],
}


def export_figures(docx, chapters):
    """埋め込み画像を取り出し、表示に必要な PNG の区画だけを公開する。"""
    figures = [(ch, p) for ch in chapters for p in ch["paragraphs"]
               if isinstance(p, dict) and "image" in p]
    if not figures:
        return
    with zipfile.ZipFile(docx) as z:
        rels = {r.get("Id"): r for r in ET.fromstring(z.read("word/_rels/document.xml.rels"))}
        counts = {}
        for ch, p in figures:
            no = ch["no"]
            counts[no] = counts.get(no, 0) + 1
            index = counts[no]
            alts = FIGURE_ALTS.get(no, [])
            if index > len(alts):
                raise SystemExit("第%d章の図%dの説明を FIGURE_ALTS に用意してください" % (no, index))
            rel = rels.get(p["image"])
            if rel is None or rel.get("TargetMode") == "External" or not rel.get("Type", "").endswith("/image"):
                raise SystemExit("第%d章の図%dの埋め込み画像が見つかりません" % (no, index))
            member = posixpath.normpath(posixpath.join("word", rel.get("Target", "")))
            if not member.startswith("word/media/"):
                raise SystemExit("埋め込み画像の格納先が word/media/ の外です")
            stem = "notion-%d-%d" % (no, index)
            staging = ROOT / "_agent" / "inputs" / "notion-figures"
            staging.mkdir(parents=True, exist_ok=True)
            source = staging / (stem + Path(member).suffix)
            source.write_bytes(z.read(member))
            converted = staging / (stem + "-converted.png")
            subprocess.run(["sips", "-s", "format", "png", str(source), "--out", str(converted)],
                           check=True, capture_output=True)
            data = converted.read_bytes()
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                raise SystemExit("図%dの PNG 変換に失敗しました" % index)
            clean = bytearray(data[:8])
            offset = 8
            while offset < len(data):
                size = struct.unpack(">I", data[offset:offset + 4])[0]
                end = offset + size + 12
                kind = data[offset + 4:offset + 8]
                if end > len(data):
                    raise SystemExit("図%dの PNG 区画が壊れています" % index)
                if kind in (b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND", b"sRGB", b"gAMA"):
                    clean.extend(data[offset:end])
                offset = end
            name = "figures/" + stem + ".png"
            target = ROOT / "assets" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(clean)
            p.clear()
            p.update(figure=name, alt=alts[index - 1])


def walk(node, out, boxes):
    """段落の文字を集める。

    - 図の文字枠と埋め込み画像は本文に混ぜず、boxes に出現順で分けて返す。
    - Word は同じ図を新しい形式（mc:Choice）と古いソフト向けの予備（mc:Fallback）の 2 回書くので、
      予備の側は読まない（読むと文が 2 回出る）。
    """
    for child in node:
        if child.tag == MC + "Fallback":
            continue
        if child.tag == W + "txbxContent":
            boxes.append({"box": [para_text(p) for p in child.findall(W + "p")]})
            continue
        if child.tag == A + "blip":
            if child.get(R + "embed"):
                boxes.append({"image": child.get(R + "embed")})
        elif child.tag == W + "t":
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
            for item in boxes:
                if "box" in item:
                    lines_ = [x.strip() for x in item["box"] if x.strip()]
                    if lines_:
                        paras.append({"box": lines_})
                else:
                    paras.append(item)
        elif child.tag == W + "tbl":
            print("注意: 表が 1 つあり、取り込んでいません（必要なら手で src/manifesto.json に足す）", file=sys.stderr)

    title, author, toc, dated = "", "", [], ""
    bars = [l[1:].strip() for l in toc_lines if l.startswith("|")]
    for i, l in enumerate(bars):  # 10/22 版: 「|題」「|YYYY-MM-DD」「|書き手」が続く
        date = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s.*)?$", l)
        if date and 0 < i < len(bars) - 1:
            title, dated, author = bars[i - 1], date.group(1), bars[i + 1]
            break
    for line in toc_lines:
        m = re.match(r"^第(\d+)章：「(.+)」$", line)
        n = re.match(r"^(\d+)\.\s*(\S.*)$", unicodedata.normalize("NFKC", line))
        if m:
            toc.append((int(m.group(1)), m.group(2)))
        elif n:
            toc.append((int(n.group(1)), n.group(2).strip()))
        elif "/" in line and not title:
            title, author = [x.strip() for x in line.split("/", 1)]
    if not toc:
        raise SystemExit("目次（「0.題」か「第N章：「…」」）が見つかりません")
    if not (title and author):
        raise SystemExit("目次の上に題と書き手が見つかりません")

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
        if m and len(text) <= 20 and int(m.group(1)) == current["no"] + 1:
            print("注意: 「%s」は章の見出しに見えますが、目次に第%s章が無いので第%d章の本文として取り込みました"
                  "（目次を更新してから取り込み直してください）" % (text, m.group(1), current["no"]), file=sys.stderr)
        current["paragraphs"].append(raw.strip("\n"))

    titles = dict(toc)
    for ch in chapters:
        ch["title"] = titles.get(ch["no"], ch["heading"])
        ch["heading"] = "%d. %s" % (ch["no"], ch["title"])
    for old, new, why in FIXES:
        hits = [(ch, i) for ch in chapters for i, p in enumerate(ch["paragraphs"])
                if isinstance(p, str) and p.endswith(old)]
        if len(hits) != 1:
            raise SystemExit("直し「%s」の当たる段落が %d 個です（1 個のはず）。原稿が替わったら FIXES を見直す: %s"
                             % (old, len(hits), why))
        ch, i = hits[0]
        ch["paragraphs"][i] = ch["paragraphs"][i][:-len(old)] + new
        print("直した: %s（%s）" % (old, why), file=sys.stderr)
    export_figures(a.docx, chapters)
    base = unicodedata.normalize("NFKC", os.path.basename(a.docx))
    m = re.search(r"(\d{4})\D?(\d{2})\D?(\d{2})", base)
    version = "%s-%s-%s" % m.groups() if m else (dated or datetime.date.today().isoformat())
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
    chars = sum(len(p) if isinstance(p, str) else sum(len(x) for x in p.get("box", []))
                for c in chapters for p in c["paragraphs"])
    print("wrote %s（%d 章・本文 %d 字）" % (a.out, len(chapters), chars))


if __name__ == "__main__":
    sys.exit(main())
