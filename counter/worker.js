// 間｜MA — Home の「現在、N 人が平場に立ちました。」の N を数える口（Cloudflare Worker ＋ Durable Object）
//
// - POST /hit   … 本番（ma-jpn.com）の Home を開いた人を 1 日 1 人 1 回だけ数え、いまの N を返す
// - GET  /count … 数えずに N を返す（プレビュー・手元・確認用）
// - GET  /      … 生存確認
//
// 数え方: 来た人の IP は保存せず、「その日だけの合言葉（salt）＋日付＋IP」の SHA-256 の一部だけを
// 当日の表に置く。同じ組が既にあれば増やさない。表は前日分まで残して古い日は消す。
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
    let salt = this._get("salt");
    if (!salt) {
      salt = randomHex(16);
      this._set("salt", salt);
    }
    const h = (await sha256hex(salt + "|" + day + "|" + ip)).slice(0, 32);
    let total = Number(this._get("total") || 0);
    const seen = this.sql.exec("SELECT 1 FROM visits WHERE day = ? AND h = ?", day, h).toArray().length > 0;
    if (!seen) {
      this.sql.exec("INSERT INTO visits (day, h) VALUES (?, ?)", day, h);
      total += 1;
      this._set("total", String(total));
    }
    this.sql.exec("DELETE FROM visits WHERE day < ?", jstDay(-1));
    return total;
  }
}
