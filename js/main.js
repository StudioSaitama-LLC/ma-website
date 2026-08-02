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
        openBtn.setAttribute("aria-expanded", open ? "true" : "false");
      };
      setOpen(false);

      openBtn.addEventListener("click", function () { setOpen(true); });
      overlay.querySelector(".menu-close").addEventListener("click", function () {
        setOpen(false);
        openBtn.focus();
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
      var pad = function (n) { return String(n).padStart(6, "0").split("").join(" "); };
      var n = 0;
      digits.textContent = pad(0);
      var t = setInterval(function () {
        n++;
        digits.textContent = pad(n);
        if (n >= target) clearInterval(t);
      }, 260);
    }
  });
})();
