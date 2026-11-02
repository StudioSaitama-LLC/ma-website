// 間｜MA — Home の「現在、N 人が平場に立ちました。」の N を数える口（Cloudflare Worker ＋ Durable Object）
//
// - POST /hit   … 本番（ma-jpn.com）の Home を開いた接続元を 1 日 1 回だけ数え、いまの N を返す
// - GET  /count … 数えずに N を返す（プレビュー・手元・確認用）
// - GET  /      … 生存確認
//
// 数え方: 来た人の IP そのものは保存しない。「毎日替わる合言葉（salt）＋日付＋接続元」の SHA-256 の
// 一部（記号）だけを当日の表に置き、同じ記号が既にあれば増やさない。接続元は IPv4 はそのまま、IPv6 は
// 回線単位の先頭 64 ビットに丸める（アドレスを替えても同じ回線は 1 回）。日が替わって最初の呼び出しのときに
// 前日までの表と合言葉を消す（静かな日は次の呼び出しまで残る。読まれはしない）。
// 日付は日本時間で区切る。数える（POST）のは本番の住所から来たときだけ受け付ける。

import { DurableObject } from "cloudflare:workers";

const PRODUCTION = new Set(["https://ma-jpn.com", "https://www.ma-jpn.com"]);
const READ_ONLY = [
  /^https:\/\/studiosaitama-llc\.github\.io$/,
  /^https:\/\/[a-z0-9-]+\.ma-website-preview-501\.pages\.dev$/,
  /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/,
];

function allowedOrigin(origin, write) {
  if (!origin) return null;
  if (PRODUCTION.has(origin)) return origin;
  if (!write && READ_ONLY.some((re) => re.test(origin))) return origin;
  return null;
}

function corsHeaders(origin) {
  const headers = { "cache-control": "no-store" };
  if (origin) {
    headers["access-control-allow-origin"] = origin;
    headers["access-control-allow-methods"] = "GET, POST, OPTIONS";
    headers["access-control-max-age"] = "86400";
    headers["vary"] = "Origin";
  }
  return headers;
}

function json(body, status, origin) {
  const headers = corsHeaders(origin);
  headers["content-type"] = "application/json; charset=utf-8";
  return new Response(JSON.stringify(body), { status, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    const stub = env.COUNTER.get(env.COUNTER.idFromName("main"));

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(allowedOrigin(origin, false)) });
    }
    if (request.method === "GET" && url.pathname === "/count") {
      return json({ count: await stub.count() }, 200, allowedOrigin(origin, false));
    }
    if (request.method === "POST" && url.pathname === "/hit") {
      const allow = allowedOrigin(origin, true);
      if (!allow) return json({ error: "origin not allowed" }, 403, null);
      const ip = request.headers.get("CF-Connecting-IP") || "";
      return json({ count: await stub.hit(ip) }, 200, allow);
    }
    if (request.method === "GET" && url.pathname === "/") {
      return new Response("ma-counter ok\n", { status: 200, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
    }
    return json({ error: "not found" }, 404, null);
  },
};

function jstDay(offsetDays) {
  const t = Date.now() + 9 * 3600 * 1000 + (offsetDays || 0) * 86400 * 1000;
  return new Date(t).toISOString().slice(0, 10);
}

async function sha256hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

// 接続元の鍵: IPv4 はそのまま。IPv6 は先頭 4 つの区切り（64 ビット＝家庭や会社の回線に配られる単位）に丸める。
// IPv4 を IPv6 に包んだ形（::ffff:1.2.3.4）は IPv4 として扱う
function ipKey(ip) {
  if (!ip.includes(":")) return ip;
  const parts = ip.split("::");
  const left = parts[0] ? parts[0].split(":") : [];
  const right = parts.length > 1 && parts[1] ? parts[1].split(":") : [];
  const last = right.length ? right[right.length - 1] : (left.length ? left[left.length - 1] : "");
  if (last.includes(".")) return last;
  const groups = parts.length > 1 ? left.concat(Array(Math.max(0, 8 - left.length - right.length)).fill("0"), right) : left;
  return groups.slice(0, 4).map((g) => (parseInt(g || "0", 16) || 0).toString(16)).join(":") + "::/64";
}

function randomHex(bytes) {
  const a = new Uint8Array(bytes);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

export class Counter extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS visits (day TEXT NOT NULL, h TEXT NOT NULL, PRIMARY KEY (day, h))");
  }

  _get(key) {
    const rows = this.sql.exec("SELECT v FROM meta WHERE k = ?", key).toArray();
    return rows.length ? rows[0].v : null;
  }

  _set(key, value) {
    this.sql.exec("INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", key, value);
  }

  async count() {
    return Number(this._get("total") || 0);
  }

  async hit(ip) {
    const day = jstDay(0);
    const saltKey = "salt:" + day;
    let salt = this._get(saltKey);
    if (!salt) {
      salt = randomHex(16);
      this._set(saltKey, salt);
    }
    const h = (await sha256hex(salt + "|" + day + "|" + ipKey(ip))).slice(0, 32);
    let total = Number(this._get("total") || 0);
    const seen = this.sql.exec("SELECT 1 FROM visits WHERE day = ? AND h = ?", day, h).toArray().length > 0;
    if (!seen) {
      this.sql.exec("INSERT INTO visits (day, h) VALUES (?, ?)", day, h);
      total += 1;
      this._set("total", String(total));
    }
    // 当日分だけ持つ: 前日までの表と合言葉は、日が替わって最初の呼び出しで消す
    this.sql.exec("DELETE FROM visits WHERE day < ?", day);
    this.sql.exec("DELETE FROM meta WHERE k LIKE 'salt%' AND k < ?", saltKey);
    return total;
  }
}
