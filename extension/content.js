// DeepGuard content script: shows an inline badge on images the user right-click
// scans. The background service worker posts results here via tabs.sendMessage.
(() => {
  const badges = new Map(); // imageUrl -> { verdict, fakeProbability, trustScore, explanation }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "DEEPGUARD_RESULT") {
      decorateImages(msg);
      sendResponse({ ok: true });
    }
    return true;
  });

  function decorateImages(msg) {
    const imgs = [...document.querySelectorAll("img")];
    for (const img of imgs) {
      badges.set(img.src, msg);
      const badge = makeBadge(msg);
      const rect = img.getBoundingClientRect();
      if (rect.width > 40 && rect.height > 40) {
        positionBadge(img, badge);
        badge.addEventListener("click", (e) => {
          e.stopPropagation();
          window.open(`https://localhost:5000/docs`, "_blank");
        });
      }
    }
  }

  function makeBadge({ verdict, fakeProbability }) {
    const b = document.createElement("div");
    const color = verdict === "FAKE" ? "#fb7185" : verdict === "UNCERTAIN" ? "#fbbf24" : "#34d399";
    b.textContent = `DeepGuard: ${verdict} ${fakeProbability}%`;
    Object.assign(b.style, {
      position: "absolute",
      zIndex: "2147483647",
      top: "6px",
      left: "6px",
      padding: "3px 8px",
      borderRadius: "8px",
      background: color,
      color: "#0b1020",
      fontSize: "11px",
      fontWeight: "700",
      fontFamily: "system-ui, sans-serif",
      pointerEvents: "auto",
      cursor: "pointer",
      boxShadow: "0 2px 8px rgba(0,0,0,.35)",
    });
    return b;
  }

  function positionBadge(img, badge) {
    const parent = img.closest("a, figure, div, picture") || document.body;
    if (!badge.parentNode) {
      const pos = getComputedStyle(parent).position;
      if (pos === "static") parent.style.position = "relative";
      parent.appendChild(badge);
    }
  }
})();
