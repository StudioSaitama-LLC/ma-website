/* 間｜MA — ページ共通の動き
   - 色の切り替え（青地 / 灰地）。ページを読む前に <head> の小さなスクリプトが前回の選択を戻している
   - メニュー（全画面）の開閉
   - 章の開閉（最初は一部だけ見せ、矢印で全部 ↔ 一部）
   - 番組の回（details）は、#ep-… で来たときに開く
   - Device Room の検索とお店の絞り込み */

(function () {
  var root = document.documentElement;

  function syncToggle() {
    var light = root.classList.contains("light");
    document.querySelectorAll(".theme-toggle").forEach(function (b) {
      b.querySelector(".tt-label").textContent = light ? "Light" : "Dark";
      b.querySelector(".tt-icon").textContent = light ? "☼" : "☾";
      b.setAttribute("aria-pressed", light ? "true" : "false");
    });
  }

  function openFromHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    var el = document.getElementById(id);
    if (el && el.tagName === "DETAILS") el.open = true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncToggle();
    document.querySelectorAll(".theme-toggle").forEach(function (b) {
      b.addEventListener("click", function () {
        root.classList.toggle("light");
        try {
          localStorage.setItem("ma-theme", root.classList.contains("light") ? "light" : "dark");
        } catch (e) {}
        syncToggle();
      });
    });

    // ---------- メニュー ----------
    var overlay = document.getElementById("site-menu");
    var openBtn = document.querySelector(".menu-btn");
    var closeBtn = overlay && overlay.querySelector(".menu-close");
    if (overlay && openBtn && closeBtn) {
      var setOpen = function (open) {
        overlay.classList.toggle("open", open);
        document.body.classList.toggle("menu-open", open);
        overlay.setAttribute("aria-hidden", open ? "false" : "true");
        openBtn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) closeBtn.focus();
      };
      openBtn.addEventListener("click", function () { setOpen(true); });
      closeBtn.addEventListener("click", function () { setOpen(false); openBtn.focus(); });
      // 同じページ内へのリンクではページが変わらないので、踏んだら閉じる
      overlay.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("click", function () { setOpen(false); });
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && overlay.classList.contains("open")) {
          setOpen(false);
          openBtn.focus();
        }
      });
    }

    // ---------- 章の開閉 ----------
    document.querySelectorAll(".fold").forEach(function (f) {
      var btn = f.querySelector(".fold-toggle");
      var body = f.querySelector(".fold-body");
      if (!btn || !body) return;
      if (body.scrollHeight <= 200) {
        btn.hidden = true;
        return;
      }
      var set = function (open) {
        f.classList.toggle("is-folded", !open);
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      };
      set(false);
      btn.addEventListener("click", function () {
        var opening = f.classList.contains("is-folded");
        set(opening);
        if (!opening) f.scrollIntoView({ block: "start" });
      });
    });

    // ---------- 番組の回 ----------
    openFromHash();
    window.addEventListener("hashchange", openFromHash);

    // ---------- 商品の写真 ----------
    var main = document.querySelector(".gallery-main");
    if (main) {
      var thumbs = document.querySelectorAll(".gallery-thumbs img");
      thumbs.forEach(function (t, i) {
        if (i === 0) t.classList.add("is-current");
        t.addEventListener("click", function () {
          main.src = t.src;
          main.alt = t.alt;
          thumbs.forEach(function (x) { x.classList.toggle("is-current", x === t); });
        });
      });
    }

    // ---------- Device Room ----------
    var grid = document.querySelector(".dev-grid");
    var q = document.getElementById("dev-q");
    if (grid && q) {
      var pills = document.querySelectorAll(".pill");
      var empty = document.querySelector(".dev-empty");
      var shop = "";
      var apply = function () {
        var term = (q.value || "").trim().toLowerCase();
        var shown = 0;
        grid.querySelectorAll(".dev-card").forEach(function (c) {
          var ok = (!shop || c.dataset.shop === shop) &&
            (!term || (c.dataset.text || "").toLowerCase().indexOf(term) >= 0);
          c.hidden = !ok;
          if (ok) shown++;
        });
        if (empty) empty.hidden = shown > 0;
      };
      pills.forEach(function (p) {
        p.setAttribute("aria-pressed", p.classList.contains("is-active") ? "true" : "false");
        p.addEventListener("click", function () {
          shop = p.dataset.shop || "";
          pills.forEach(function (x) {
            x.classList.toggle("is-active", x === p);
            x.setAttribute("aria-pressed", x === p ? "true" : "false");
          });
          apply();
        });
      });
      q.addEventListener("input", apply);
      if (q.form) q.form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
      var wanted = location.hash.slice(1);
      pills.forEach(function (p) { if (wanted && p.dataset.shop === wanted) p.click(); });
    }
  });
})();
