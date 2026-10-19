#!/usr/bin/env python3
"""荒井さんの Device 表（xlsx）から、サイトに載せる商品だけを src/device.json に書き出す。

使い方:
  python3 tools/import_device.py <Device_YYYYMMDD.xlsx> --ids 2 [--sheet β版] [--out src/device.json]

- 標準ライブラリだけで動く（openpyxl 不要）。
- 1 行目を見出し行として、列名で値を取る（列の並びが変わっても読める）。
- 同じ商品 ID の行は「色違い」としてまとめる。商品全体の値（質問・仕様・特徴など）は、
  最初に値が入っている行のものを使う（荒井さんの表は 2 行目以降が空いていることがあるため）。
"""
import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EC_URL = "https://manaka-store.com/products/detail/{id}"


def col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def string_item(si):
    """文字列セルの中身。ふりがな（rPh）は文字に含めない。"""
    parts = []
    for child in si:
        if child.tag == "{%s}t" % NS["m"]:
            parts.append(child.text or "")
        elif child.tag == "{%s}r" % NS["m"]:
            parts.extend(t.text or "" for t in child.findall("m:t", NS))
    text = "".join(parts)
    # Excel はセル内の改行コード（CR）などを _x000D_ の形で保存する
    text = re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_sheet(path, sheet_hint):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append(string_item(si))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels.findall("rel:Relationship", NS)}
    chosen = None
    for s in wb.find("m:sheets", NS):
        name = s.get("name")
        if sheet_hint is None or sheet_hint in name:
            chosen = (name, targets[s.get("{%s}id" % NS["r"])])
            break
    if chosen is None:
        raise SystemExit("シートが見つかりません: %s" % sheet_hint)
    name, target = chosen
    target = target.lstrip("/")
    if not target.startswith("xl/"):
        target = "xl/" + target
    rows = []
    for row in ET.fromstring(z.read(target)).iter("{%s}row" % NS["m"]):
        values = {}
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                inline = c.find("m:is", NS)
                val = string_item(inline) if inline is not None else ""
            else:
                val = v.text if v is not None else ""
            values[col_index(c.get("r"))] = val
        if values:
            width = max(values) + 1
            rows.append([values.get(i, "") for i in range(width)])
    return name, rows


def num(v):
    v = (v or "").strip()
    if re.fullmatch(r"\d+(\.0+)?", v):
        return int(float(v))
    return v or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--ids", required=True, help="載せる商品 ID（カンマ区切り）")
    ap.add_argument("--sheet", default="β版", help="シート名に含まれる文字")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "src", "device.json"))
    a = ap.parse_args()
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    sheet, rows = read_sheet(a.xlsx, a.sheet)
    head = [h.strip() for h in rows[0]]

    def cell(r, name):
        i = head.index(name) if name in head else -1
        return (r[i] if 0 <= i < len(r) else "").strip()

    products = []
    for pid in ids:
        mine = [r for r in rows[1:] if cell(r, "商品ID") == pid]
        if not mine:
            raise SystemExit("商品 ID %s が見つかりません" % pid)

        def first(name):
            for r in mine:
                v = cell(r, name)
                if v:
                    return v
            return ""

        highlights = []
        for k in (1, 2):
            q, ans = first("トップハイライト:%d（問）" % k), first("トップハイライト:%d（答）" % k)
            if q:
                highlights.append({"q": q, "a": ans})
        specs = [{"label": k, "value": first(k)} for k in ("サイズ", "素材", "生産地") if first(k)]
        features = []
        for k in range(1, 5):
            img, ttl, body = first("特徴%d　画像" % k), first("特徴%d　コピー" % k), first("特徴%d　本文" % k)
            if img or ttl or body:
                features.append({"image": img, "title": ttl, "body": body})
        variants = [{"color": cell(r, "色"), "list_price": num(cell(r, "通常価格")),
                     "price": num(cell(r, "販売価格")), "image": cell(r, "メイン画像")} for r in mine]
        products.append({
            "id": pid,
            "name": first("商品名"),
            "shop": first("所属名"),
            "category": first("商品"),
            "copy": first("商品説明コピー"),
            "body": first("商品説明本文"),
            "highlights": highlights,
            "specs": specs,
            "features": features,
            "variants": variants,
            "ec_url": EC_URL.format(id=pid),
        })
    out = {"source": os.path.basename(a.xlsx), "sheet": sheet, "products": products}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("wrote %s（%d 商品・%d 色）" % (a.out, len(products), sum(len(p["variants"]) for p in products)))


if __name__ == "__main__":
    sys.exit(main())
