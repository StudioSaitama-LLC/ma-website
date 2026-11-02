#!/usr/bin/env python3
"""counter/worker.js を Cloudflare Workers に配備する（標準ライブラリだけ・Python 3.9 以上）。

使い方:
  CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… python3 counter/deploy.py          # 配備（初回は Durable Object の移行も）
  CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… python3 counter/deploy.py --check  # 配備せず、いまの状態を見る
  … python3 counter/deploy.py --migrate   # Durable Object のクラスを増やしたとき（MIGRATIONS を直してから）

トークンに要る権限: Workers Scripts の編集。値をコマンド引数・ログ・PR に書かない（環境変数で渡す）。
"""
import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
SCRIPT_NAME = "ma-counter"
COMPATIBILITY_DATE = "2026-10-01"
MIGRATIONS = {"new_tag": "v1", "new_sqlite_classes": ["Counter"]}
BINDINGS = [{"type": "durable_object_namespace", "name": "COUNTER", "class_name": "Counter"}]
HERE = Path(__file__).resolve().parent


def call(method, path, token, body=None, content_type=None):
    data = None
    headers = {"Authorization": "Bearer " + token}
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            data = body
            headers["Content-Type"] = content_type
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                payload = json.loads(res.read().decode())
            break
        except urllib.error.HTTPError as err:
            try:
                payload = json.loads(err.read().decode())
            except Exception:
                payload = {"success": False, "errors": [{"message": "HTTP %s" % err.code}]}
            break
        except (http.client.HTTPException, urllib.error.URLError, OSError) as err:
            # 読み取りの途中切れ・一時的な網の不調。読むだけの GET はやり直す（書く PUT/POST は 1 回で止める）
            if method != "GET" or attempt == 2:
                raise SystemExit("%s %s に失敗: %s" % (method, path, err))
            time.sleep(2 * (attempt + 1))
    if not payload.get("success"):
        raise SystemExit("%s %s に失敗: %s" % (method, path, "; ".join(e.get("message", "?") for e in payload.get("errors", []))))
    return payload.get("result")


def multipart(parts):
    boundary = "----ma-counter-" + uuid.uuid4().hex
    out = bytearray()
    for name, filename, content_type, content in parts:
        out += ("--%s\r\n" % boundary).encode()
        disposition = 'form-data; name="%s"' % name
        if filename:
            disposition += '; filename="%s"' % filename
        out += ("Content-Disposition: %s\r\n" % disposition).encode()
        out += ("Content-Type: %s\r\n\r\n" % content_type).encode()
        out += content if isinstance(content, bytes) else content.encode()
        out += b"\r\n"
    out += ("--%s--\r\n" % boundary).encode()
    return bytes(out), "multipart/form-data; boundary=" + boundary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="配備せず、いまの状態を表示する")
    ap.add_argument("--migrate", action="store_true", help="既存の script でも MIGRATIONS を送る")
    ap.add_argument("--name", default=SCRIPT_NAME, help="script の名前（既定: %(default)s）")
    args = ap.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account:
        sys.exit("CLOUDFLARE_API_TOKEN と CLOUDFLARE_ACCOUNT_ID を環境変数で渡してください")
    base = "/accounts/%s/workers" % account

    existing = call("GET", base + "/scripts", token)
    exists = any(s.get("id") == args.name for s in existing or [])
    subdomain = (call("GET", base + "/subdomain", token) or {}).get("subdomain")
    if not subdomain:
        sys.exit("このアカウントには workers.dev の名前（subdomain）がありません。Cloudflare の Workers の画面で先に決めてください")
    url = "https://%s.%s.workers.dev" % (args.name, subdomain)

    if args.check:
        print(json.dumps({"script": args.name, "exists": exists, "url": url}, ensure_ascii=False))
        if exists:
            settings = call("GET", base + "/scripts/%s/settings" % args.name, token)
            print(json.dumps({"compatibility_date": settings.get("compatibility_date"),
                              "bindings": settings.get("bindings")}, ensure_ascii=False, indent=2))
            print(json.dumps(call("GET", base + "/scripts/%s/subdomain" % args.name, token), ensure_ascii=False))
        return

    metadata = {
        "main_module": "worker.js",
        "compatibility_date": COMPATIBILITY_DATE,
        "bindings": BINDINGS,
        # 呼び出しログ（Workers Logs）は切る。付けると呼び出しごとの要求情報（接続元の IP を含む）が数日残る
        "observability": {"enabled": False},
    }
    if not exists or args.migrate:
        metadata["migrations"] = MIGRATIONS
    body, content_type = multipart([
        ("metadata", None, "application/json", json.dumps(metadata)),
        ("worker.js", "worker.js", "application/javascript+module", (HERE / "worker.js").read_bytes()),
    ])
    result = call("PUT", base + "/scripts/%s" % args.name, token, body, content_type)
    # workers.dev の住所は初回だけ有効にする（あとで意図して止めたものを、配備のたびに戻さない）
    if not exists:
        call("POST", base + "/scripts/%s/subdomain" % args.name, token, {"enabled": True, "previews_enabled": False})
    enabled = (call("GET", base + "/scripts/%s/subdomain" % args.name, token) or {}).get("enabled")
    print(json.dumps({"script": args.name, "deployed": True, "etag": (result or {}).get("etag"),
                      "first_deploy": not exists, "url": url, "url_enabled": enabled}, ensure_ascii=False))


if __name__ == "__main__":
    main()
