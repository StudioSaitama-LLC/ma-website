/* 間｜MA — ページ共通の動き
   - 色の切り替え（青地 / 灰地）。ページを読む前に <head> の小さなスクリプトが前回の選択を戻している
   - メニュー（全画面）の開閉
   - 章の開閉（最初は一部だけ見せ、矢印で全部 ↔ 一部）
   - 記事の冒頭の写真の切り替え
   - 番組の回（details）は、#ep-… で来たときに開く
   - 商品の写真の送り
   - Device Room の検索とお店の絞り込み（商品ページの検索からは ?q= で来る） */

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
    var id = "";
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (e) { return; }
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
        // 開いている間は、後ろのページに Tab で移れないようにする
        document.querySelectorAll("body > header, body > .gate-bar, body > main, body > footer").forEach(function (el) {
          if (open) el.setAttribute("inert", ""); else el.removeAttribute("inert");
        });
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

    // ---------- 章の開閉（最初は見出しだけ） ----------
    document.querySelectorAll(".fold").forEach(function (f) {
      var btn = f.querySelector(".fold-toggle");
      var body = f.querySelector(".fold-body");
      if (!btn || !body) return;
      var set = function (open) {
        f.classList.toggle("is-folded", !open);
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      };
      set(false);
      btn.addEventListener("click", function () {
        var opening = f.classList.contains("is-folded");
        set(opening);
        if (opening) {
          // 開くと ↓ は消える（デザイン）ので、読み始める本文へフォーカスを移す
          body.setAttribute("tabindex", "-1");
          body.focus({ preventScroll: true });
        } else {
          f.scrollIntoView({ block: "start" });
        }
      });
    });

    // 章の本文の最後の ↑ は、章を閉じて見出しへ戻る
    document.querySelectorAll(".fold-close").forEach(function (b) {
      b.addEventListener("click", function () {
        var f = b.closest(".fold");
        var t = f && f.querySelector(".fold-toggle");
        if (t) { t.click(); t.focus({ preventScroll: true }); }
      });
    });
    // 回の本文の最後の ↑ は、回を閉じる
    document.querySelectorAll(".entry-close").forEach(function (b) {
      b.addEventListener("click", function () {
        var d = b.closest("details");
        if (!d) return;
        d.open = false;
        d.scrollIntoView({ block: "start" });
        var sm = d.querySelector("summary");
        if (sm) sm.focus({ preventScroll: true });
      });
    });

    // ---------- 記事の冒頭の写真（拡大しながら次の写真へ） ----------
    // 上の写真（is-on）が 6 秒で寄りながら消え、真下に待つ次の写真（is-next）が出る。動きを減らす設定なら 1 枚目のまま
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.querySelectorAll(".article-hero").forEach(function (hero) {
      var imgs = hero.querySelectorAll(".hs-img");
      if (imgs.length < 2 || still) return;
      // 2 枚目からは、切り替えが動くページでだけ、開いた時点でまとめて読み込む（動きを減らす設定・JS 無しでは読まない）
      imgs.forEach(function (im) { if (im.dataset.src) { im.src = im.dataset.src; im.removeAttribute("data-src"); } });
      var i = 0;
      var show = function () {
        imgs.forEach(function (im, k) {
          im.classList.toggle("is-on", k === i);
          im.classList.toggle("is-next", k === (i + 1) % imgs.length);
        });
      };
      imgs.forEach(function (im) {
        im.addEventListener("animationend", function () {
          if (!im.classList.contains("is-on")) return;
          i = (i + 1) % imgs.length;
          show();
        });
      });
      show();
      hero.classList.add("is-playing");
    });

    // ---------- 番組の回 ----------
    openFromHash();
    window.addEventListener("hashchange", openFromHash);

    // ---------- 商品の写真 ----------
    // 写真は横に並び、指（スマホ）か下の小さな写真（PC）で送る。今何枚目かを「1/N」に出す
    var track = document.querySelector(".gallery-track");
    if (track) {
      var slides = track.querySelectorAll("li");
      var now = document.querySelector(".gc-now");
      var thumbs = document.querySelectorAll(".gallery-thumbs .thumb");
      // 今どの写真が見えているかは、枠の左端にいちばん近い写真で決める（画面の拡大・縮小があっても合う）
      var nearest = function () {
        var left = track.getBoundingClientRect().left, best = 0, d = Infinity;
        slides.forEach(function (li, k) {
          var x = Math.abs(li.getBoundingClientRect().left - left);
          if (x < d) { d = x; best = k; }
        });
        return best;
      };
      var mark = function (i) {
        if (now) now.textContent = String(i + 1);
        thumbs.forEach(function (x, k) { x.setAttribute("aria-pressed", k === i ? "true" : "false"); });
      };
      // 小さい写真を押したら、送り終わるまで途中の番号を出さない
      var goal = null, goalTimer = null;
      thumbs.forEach(function (t, i) {
        t.addEventListener("click", function () {
          goal = i;
          clearTimeout(goalTimer);
          goalTimer = setTimeout(function () { goal = null; mark(nearest()); }, 1000);
          track.scrollTo({ left: i * track.clientWidth, behavior: still ? "auto" : "smooth" });
          mark(i);
        });
      });
      var tick = null;
      track.addEventListener("scroll", function () {
        if (tick) return;
        tick = setTimeout(function () {
          tick = null;
          var i = nearest();
          if (goal !== null) { if (i !== goal) return; goal = null; }
          mark(i);
        }, 80);
      });
      mark(0);
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
      // 商品ページの検索から ?q=… で来たら、その言葉で絞り込んだ状態で開く
      var asked = "";
      try { asked = new URLSearchParams(location.search).get("q") || ""; } catch (e) {}
      if (asked) { q.value = asked; apply(); }
      var wanted = location.hash.slice(1);
      pills.forEach(function (p) { if (wanted && p.dataset.shop === wanted) p.click(); });
    }
  });
})();
