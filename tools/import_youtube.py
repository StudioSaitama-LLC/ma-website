#!/usr/bin/env python3
"""YouTube の題と説明文の冒頭を src/contents.json に写す（回の題と一言を、いつも YouTube に合わせるため）。

使い方:
  python3 tools/import_youtube.py          # YouTube を読み、変わっていれば contents.json を書き換える
  python3 tools/import_youtube.py --check  # 書き換えず、YouTube とずれている項目だけを出す（ずれていれば終了コード 1）

- 標準ライブラリだけで動く。読むのは contents.json で youtube（動画 ID）があり、公開（published）の項目だけ。
  公開前の動画（限定公開など）の題と説明文を、公開の repo に入れないため。公開でない項目に残っている
  yt_title・yt_lead は取り除く（build.py の検査もこれを止める）。
- 書くのは yt_title（動画の題そのまま）と yt_lead（説明文のうち「TIMELINE」の見出しや「0:00」のような
  時刻で始まる行より前。前後の空行は除く）。build.py はこの 2 つがあれば、回の題と一言にこれを使う。
- 説明文が空の動画は yt_lead を空にする（このときは caption が一言として出る）。
- 読むのは YouTube の動画ページ（ページに埋め込まれた動画の情報）。YouTube 側の作りが変わると読めなくなるので、
  そのときは「読めなかった」と出して終了コード 1 にする（contents.json は書き換えない）。
- 書き換えたあとは python3 tools/build.py で生成し直す。
"""
import argparse
import http.client
import json
import os
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTENTS = os.path.join(ROOT, "src", "contents.json")
WATCH = "https://www.youtube.com/watch?v=%s"
VIDEO_ID = r"[A-Za-z0-9_-]{11}"
TRIES = 3
# 説明文のここから先は一言に入れない: 「TIMELINE」の見出し（【TIMELINE】・■TIMELINE: なども）と、時刻で始まる行
STOP = re.compile(r"\s*(?:[^\w\s]\s*)*TIMELINE\b|\s*\d{1,2}:\d{2}(?::\d{2})?(?!\d)", flags=re.I)


def player_response(html):
    """watch ページに埋め込まれた ytInitialPlayerResponse（JSON）を取り出す。"""
    m = re.search(r"ytInitialPlayerResponse\s*=\s*\{", html)
    if not m:
        raise ValueError("ytInitialPlayerResponse が見つからない")
    start = m.end() - 1
    obj, _ = json.JSONDecoder().raw_decode(html[start:])
    return obj


def lead_of(description):
    """説明文のうち、TIMELINE の見出しか時刻で始まる行より前。行の終わりの空白と、前後の空行は除く。"""
    out = []
    for line in (description or "").replace("\r\n", "\n").split("\n"):
        if STOP.match(line):
            break
        out.append(line.rstrip())
    return "\n".join(out).strip("\n").strip()


def get_page(video_id):
    """動画のページを読む。通信の失敗（時間切れ・429・5xx）と、途中で切れた応答は、間を空けて読み直す。"""
    req = urllib.request.Request(WATCH % video_id, headers={"Accept-Language": "ja,en;q=0.8", "User-Agent": "Mozilla/5.0"})
    last = None
    for attempt in range(TRIES):
        if attempt:
            time.sleep(2 * attempt)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except http.client.IncompleteRead as e:
            # 途中で切れても、題と説明文はページの前のほうにあるので、読めた分で足りることが多い
            data = e.partial
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 or e.code >= 500:
                continue
            raise
        except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
            last = e
            continue
        try:
            return player_response(data.decode("utf-8", errors="replace"))
        except ValueError as e:
            last = e
    raise last


def fetch(video_id):
    pr = get_page(video_id)
    status = (pr.get("playabilityStatus") or {}).get("status", "")
    vd = pr.get("videoDetails") or {}
    if vd.get("videoId") != video_id or not vd.get("title"):
        raise ValueError("動画の情報が読めない（状態: %s）" % (status or "不明"))
    return vd["title"].strip(), lead_of(vd.get("shortDescription", ""))


def with_fields(item, title, lead):
    """youtube の直後に yt_title・yt_lead を置いた新しい項目（並びを保って差分を小さくする）。"""
    out = {}
    for k, v in item.items():
        if k in ("yt_title", "yt_lead"):
            continue
        out[k] = v
        if k == "youtube":
            out["yt_title"] = title
            out["yt_lead"] = lead
    return out


def without_fields(item):
    return {k: v for k, v in item.items() if k not in ("yt_title", "yt_lead")}


def write_atomic(path, text):
    """途中で止まっても元のファイルが壊れないよう、同じフォルダの一時ファイルに書いてから置き換える。"""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".contents-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="書き換えず、YouTube とずれている項目だけを出す")
    a = ap.parse_args()
    with open(CONTENTS, encoding="utf-8") as f:
        contents = json.load(f)
    changed, failed = [], []
    new = []
    for item in contents:
        vid = item.get("youtube", "")
        if not vid or item.get("status") != "published":
            if "yt_title" in item or "yt_lead" in item:
                changed.append("#%s: 公開でない（または動画 ID が無い）ので yt_title・yt_lead を外す" % item.get("id"))
                item = without_fields(item)
            new.append(item)
            continue
        if not re.fullmatch(VIDEO_ID, vid):
            failed.append("#%s: 動画 ID の形が違う: %r" % (item.get("id"), vid))
            new.append(item)
            continue
        try:
            title, lead = fetch(vid)
        except Exception as e:  # 1 本読めなくても、ほかの動画は確かめる
            failed.append("#%s（%s）: %s" % (item.get("id"), vid, e))
            new.append(item)
            continue
        if item.get("yt_title") != title or item.get("yt_lead") != lead:
            changed.append("#%s: 題「%s」／一言「%s」" % (item.get("id"), title, lead.replace("\n", " / ")))
        new.append(with_fields(item, title, lead))
    for line in failed:
        print("読めなかった: " + line, file=sys.stderr)
    for line in changed:
        print(("ずれている: " if a.check else "更新: ") + line)
    if a.check:
        return 1 if (changed or failed) else 0
    if failed:
        # 一部だけ読めた状態で書くと、読めなかった動画の古い題が残ったことに気づきにくいので、書かない
        print("読めなかった動画があるので contents.json は書き換えていない（時間をおいて、もう一度実行する）", file=sys.stderr)
        return 1
    if changed:
        write_atomic(CONTENTS, json.dumps(new, ensure_ascii=False, indent=2) + "\n")
        print("src/contents.json を書き換えた（%d 件）。python3 tools/build.py で生成し直す" % len(changed))
    else:
        print("変更なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
