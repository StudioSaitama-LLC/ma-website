/* 間｜MA — shared behaviors */

(function () {
  // ---------- Theme (Light / Dark : 2パターンの明るさ) ----------
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem("ma-theme"); } catch (e) {}
  if (saved === "light") root.classList.add("light");

  function syncToggle() {
    var btns = document.querySelectorAll(".theme-toggle");
    var isLight = root.classList.contains("light");
    btns.forEach(function (b) {
      b.querySelector(".t-label").textContent = isLight ? "Dark ☾" : "Light ☀";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncToggle();

    document.querySelectorAll(".theme-toggle").forEach(function (b) {
      b.addEventListener("click", function () {
        root.classList.toggle("light");
        try {
          localStorage.setItem(
            "ma-theme",
            root.classList.contains("light") ? "light" : "dark"
          );
        } catch (e) {}
        syncToggle();
      });
    });

    // ---------- Header : スクロールでタイトル行が消える ----------
    var header = document.querySelector(".site-header");
    if (header) {
      var onScroll = function () {
        header.classList.toggle("scrolled", window.scrollY > 60);
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }

    // ---------- Menu overlay ----------
    var overlay = document.querySelector(".menu-overlay");
    var openBtn = document.querySelector(".menu-btn");
    if (overlay && openBtn) {
      var setOpen = function (open) {
        overlay.classList.toggle("open", open);
        document.body.classList.toggle("menu-open", open);
        overlay.setAttribute("aria-hidden", open ? "false" : "true");
        openBtn.setAttribute("aria-expanded", open ? "true" : "false");
        openBtn.setAttribute("aria-label", open ? "メニューを閉じる" : "メニューを開く");
      };
      setOpen(false);

      openBtn.addEventListener("click", function () {
        setOpen(!overlay.classList.contains("open"));
      });

      // 同一ページ内アンカー(index.html#ma-lab 等)はページ遷移が起きないため、
      // リンクを踏んだら明示的に閉じないとオーバーレイが画面を覆ったままになる
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

    // ---------- Traffic counter ----------
    var digits = document.querySelector(".traffic .digits");
    if (digits) {
      var target = parseInt(digits.dataset.count || "2", 10);
      var pad = function (n) { return String(n).padStart(6, "0"); };
      var n = 0;
      digits.textContent = pad(0);
      var t = setInterval(function () {
        n++;
        digits.textContent = pad(n);
        if (n >= target) clearInterval(t);
      }, 260);
    }

    // ---------- Home : スクロールに合わせて内容を順次表示 ----------
    var revealItems = document.querySelectorAll(
      ".home-page .poem, .home-page .logo-mark, .home-page .contents-head, .home-page .toc > li"
    );
    if (revealItems.length) {
      revealItems.forEach(function (item) { item.classList.add("reveal-item"); });

      if (!("IntersectionObserver" in window)) {
        revealItems.forEach(function (item) { item.classList.add("is-visible"); });
      } else {
        var revealObserver = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              revealObserver.unobserve(entry.target);
            }
          });
        }, { threshold: 0.08, rootMargin: "0px 0px -8% 0px" });

        revealItems.forEach(function (item) { revealObserver.observe(item); });
      }
    }
  });
})();
