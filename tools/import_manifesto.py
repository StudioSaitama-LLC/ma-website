#!/usr/bin/env python3
"""副社長の MA Notion（Word の docx）を章ごとに分けて src/manifesto.json に書き出す。

使い方:
  python3 tools/import_manifesto.py <About 間 宮嶋孝尚 YYYY／MM／DD.docx> [--out src/manifesto.json]

- 文字の取り込みは標準ライブラリだけで動く。埋め込み画像は macOS の sips で BMP にし、標準ライブラリで余白を切って PNG にする。
- 冒頭の目次から章の題をとる。目次の形は 2 つ読める。
  10/22 版から: 「|Notion」「|感じぬ人」「|2026-10-16」「|宮嶋 孝尚」の後に「0.真面目な提案」…（題の無い「4.」などは飛ばす）
  10/16 版まで: 「感じぬ人 / 宮嶋 孝尚」の後に「第0章：「真面目な提案」」…
- 本文は、最初の段落を第 0 章の見出し、「1.旅のはじまり」「３．おおよそ」のように番号で始まる段落を各章の見出しとみなして分ける。
  見出しは目次の題で「0. 真面目な提案」の形（半角の数字・点・空白）にそろえる。
- 目次にだけあって本文に見出しの無い章は、本文の無い章（paragraphs が空）として題だけ取り込み、続きがあると分かるようにする。
  題は目次の文のまま（「仮）」なども手を入れない）。ただし本文の無い章の題は TITLE_ONLY_TITLES（書き手の指定）を優先し、目次に無い章も題だけ足す。
  本文が届いた章は原稿の題を正とする。
- 段落の中の改行はそのまま残す。文には手を入れない。ただし FIXES に書いた直しだけは当てる（当たらなければ止める）。
- 図の中の文字枠は {"box": [行, ...]} として、その図がある段落の直後に置く。表は取り込まず、注意を出す。
- 埋め込み画像は本文の順で {"figure": "figures/notion-章-番号.png", "alt": "説明"} にし、周囲の白を 24px 残して切り、撮影情報のない PNG を assets/ に置く。
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
import zlib

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
ROOT = Path(__file__).resolve().parent.parent

# 原稿に当てる直し（段落の終わりの文字列 → 置き換え）。指定されたものだけ書く。
# 当たる段落がちょうど 1 つでなければ止める（原稿が替わったら見直す）。
# 11/17 版では該当の一節が書き直されたため、10/22 版の末尾「ｆ」の直しを外した。
FIXES = []

# 本文がまだ無い章の題は、書き手の指定（2026-11-19）を正とする（原稿の目次は 11 章までで、題も古い）。
# 表は本文の無い章にだけ効く。本文が届いた章は、原稿の題を正とする（その章はこの表から外してよい）
TITLE_ONLY_TITLES = {
    7: "仮）Y字路",
    8: "仮）調が転がる",
    9: "仮）医者の不養生",
    10: "仮）AIのばかやろー",
    11: "仮）感ずる人",
    12: "仮）旅の終わり",
}

# 本文の図番号に対応する説明。Word 内部の図の名前・番号は使わない。
FIGURE_ALTS = {
    5: [
        "人から Step1 情報、新たな行動原理を経て Step2 処理・Step3 目的・Step4 行動・Step5 成果へ進む流れ",
        "人から Step1 情報、感ずる行動原理を経て Step2 感受・Step3 感情・Step4 行動・Step5 受容へ進む流れ",
        "突然の雨という同じ情報が、思考の岐路で 2 つに分かれる。新たな行動原理は 雨雲が深い→濡れずに帰社→天気・コンビニ・路線を調べる→予定どおり帰社、感ずる行動原理は あの日の雨に似ている→切なくどこか懐かしい→雨宿りしてぼーっとする→少し身軽な心持ちで帰社",
        "1980 年から 2020 年まで 10 年ごとの棒グラフ。感ずる・その他・新たな、の行動原理の割合の移り変わりと、インターネット・スマートフォン・SNS・クラウド・AI の登場。新たな行動原理が年を追って増える",
    ],
}


def read_bmp_rgb(data):
    """無圧縮の 24/32 ビット BMP を、上から並ぶ RGB の行にする。"""
    if len(data) < 54 or data[:2] != b"BM":
        raise SystemExit("図の BMP ヘッダーが壊れています")
    offset, header_size = struct.unpack_from("<II", data, 10)
    width, height, planes, depth, compression = struct.unpack_from("<iiHHI", data, 18)
    if (header_size < 40 or offset < 14 + header_size or width <= 0 or height == 0
            or planes != 1 or depth not in (24, 32) or compression != 0):
        raise SystemExit("図の BMP は無圧縮の 24/32 ビット画像である必要があります")
    stride = ((width * depth + 31) // 32) * 4
    if offset + stride * abs(height) > len(data):
        raise SystemExit("図の BMP 画素が途中で切れています")
    rows = []
    step = depth // 8
    for y in range(abs(height)):
        source_y = y if height < 0 else height - 1 - y
        start = offset + source_y * stride
        row = bytearray()
        for x in range(width):
            pixel = start + x * step
            b, g, r = data[pixel:pixel + 3]
            alpha = data[pixel + 3] if depth == 32 else 255
            row.extend((value * alpha + 255 * (255 - alpha) + 127) // 255
                       for value in (r, g, b))
        rows.append(bytes(row))
    return width, abs(height), rows


def cropped_figure_png(data):
    """白でない画素の周囲を 24px 残し、決まった区画だけの PNG にする。"""
    width, height, rows = read_bmp_rgb(data)
    left, top, right, bottom = width, height, -1, -1
    for y, row in enumerate(rows):
        for x in range(width):
            if min(row[x * 3:x * 3 + 3]) < 250:
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
    if right < 0:
        raise SystemExit("図が白一色のため、余白を切り出せません")
    left, top = max(0, left - 24), max(0, top - 24)
    right, bottom = min(width, right + 25), min(height, bottom + 25)
    pixels = b"".join(b"\x00" + row[left * 3:right * 3] for row in rows[top:bottom])

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload)))

    header = struct.pack(">IIBBBBB", right - left, bottom - top, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"sRGB", b"\x00")
            + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b""))


def export_figures(docx, chapters):
    """埋め込み画像の余白を切り、撮影情報を持たない PNG を公開する。"""
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
            converted = staging / (stem + ".bmp")
            subprocess.run(["sips", "-s", "format", "bmp", str(source), "--out", str(converted)],
                           check=True, capture_output=True)
            clean = cropped_figure_png(converted.read_bytes())
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
            # 番号は NFKC で読むが、題は原稿の文字のまま（全角の「）」なども変えない）
            raw = re.match(r"^\s*[0-9０-９]+\s*[.．]\s*(.*)$", line)
            toc.append((int(n.group(1)), (raw.group(1) if raw else n.group(2)).strip()))
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
    have = set(ch["no"] for ch in chapters)
    for no, t in toc:
        if no not in have:
            chapters.append({"no": no, "title": t, "heading": "%d. %s" % (no, t), "paragraphs": []})
            have.add(no)
            print("注意: 「%d. %s」は本文が無いので、題だけ取り込みました" % (no, t), file=sys.stderr)
    for no, t in sorted(TITLE_ONLY_TITLES.items()):
        ch = next((c for c in chapters if c["no"] == no), None)
        if ch is None:
            chapters.append({"no": no, "title": t, "heading": "%d. %s" % (no, t), "paragraphs": []})
            print("注意: 「%d. %s」は原稿の目次に無いので、指定の題だけ足しました" % (no, t), file=sys.stderr)
        elif ch["paragraphs"]:
            print("注意: 第%d章は本文が届いたので、原稿の題「%s」を使いました（TITLE_ONLY_TITLES の第%d章は外してよい）"
                  % (no, ch["title"], no), file=sys.stderr)
        elif ch["title"] != t:
            print("注意: 「%s」の題を、指定の「%s」にしました" % (ch["heading"], t), file=sys.stderr)
            ch["title"], ch["heading"] = t, "%d. %s" % (no, t)
    chapters.sort(key=lambda c: c["no"])
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
