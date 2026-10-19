#!/usr/bin/env python3
"""Notion の「密」「間」の球（assets/figures/dots-dense.svg・dots-sparse.svg）を作る（標準ライブラリだけ）。

使い方: python3 tools/make_spheres.py assets/figures

球の中心と半径は、デザインの PDF（10/16 版・PC）の描画から測った値。

測り方（Drive ビューアの 3200px 描画・PC 1920 基準）: 水色の明るい部分の距離変換の極大＝中心と半径。
明るい部分は下側の濃い縁を含まないので、本当の球は 中心を (-0.075r, +0.125r) ずらし、半径を 1.125 倍にする
（大きい球の色の断面から求めた）。光は右上から。下に濃い影が付く。
"""
import os, sys

DENSE = [(1130, 1482, 8.8), (1171.4, 1483.2, 8), (1174.4, 1503, 8), (1130, 1516.8, 7.8), (1161.2, 1542, 7.6),
         (1150.4, 1474.8, 7), (1150.4, 1520.4, 7), (1136.6, 1499.4, 6.8), (1178, 1539.6, 6.8), (1171.4, 1522.8, 6.4),
         (1157.6, 1496.4, 6.2), (1139.6, 1537.2, 6.2)]
SPARSE = [(1376, 1480.2, 4.8), (1449.2, 1484.4, 4.8), (1401.8, 1527.6, 4.6), (1422.2, 1551.6, 4.6), (1402.4, 1465.2, 3.8),
          (1422.2, 1485.6, 3.8), (1434.8, 1516.8, 3.8), (1368.8, 1511.4, 3.6), (1389.2, 1501.8, 2.4), (1378.4, 1546.2, 2.4),
          (1448, 1537.2, 2), (1409.6, 1505.4, 1.8)]


def spheres(raw):
    return [(x - 0.075 * r, y + 0.125 * r, 1.125 * r) for x, y, r in raw]


def svg(raw, name):
    s = spheres(raw)
    pad = 0.6
    x0 = min(x - r for x, y, r in s) - pad
    y0 = min(y - r for x, y, r in s) - pad
    x1 = max(x + r for x, y, r in s) + pad
    y1 = max(y + r * 1.25 for x, y, r in s) + pad  # 影の分だけ下に余白
    w, h = x1 - x0, y1 - y0
    # 上の球が下の球に重なるように、上から順に描く（デザインも上の球の影が下の球に落ちていない＝下が手前）
    s.sort(key=lambda t: t[1])
    parts = []
    for x, y, r in s:
        cx, cy = x - x0, y - y0
        parts.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="#0e3d62" opacity=".85"/>' % (cx - 0.08 * r, cy + 0.22 * r, r * 0.98))
        parts.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="url(#g)"/>' % (cx, cy, r))
    out = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.2f %.2f" width="%.2f" height="%.2f">'
           '<defs><radialGradient id="g" cx=".55" cy=".42" r=".62" fx=".64" fy=".28">'
           '<stop offset="0" stop-color="#3ef8f5"/><stop offset=".5" stop-color="#1ff2ef"/>'
           '<stop offset=".74" stop-color="#00e0e1"/><stop offset=".88" stop-color="#00c2c3"/>'
           '<stop offset="1" stop-color="#006a6b"/></radialGradient></defs>%s</svg>\n') % (w, h, w, h, "".join(parts))
    return out, (x0, y0, w, h)


if __name__ == "__main__":
    dst = sys.argv[1]
    for raw, name in ((DENSE, "dots-dense"), (SPARSE, "dots-sparse")):
        text, (x0, y0, w, h) = svg(raw, name)
        open(os.path.join(dst, name + ".svg"), "w").write(text)
        print("%s: design x0=%.1f y0=%.1f w=%.1f h=%.1f" % (name, x0, y0, w, h))
