// DeepGuard extension background service worker.
// Listens for context-menu clicks on images and calls the /api/keys/extend/analyze
// endpoint with the user's stored API key.

const API_URL = "http://localhost:5000/api";

// --- Context menu ------------------------------------------------------------------
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "deepguard-check-image",
    title: "DeepGuard: check image for AI / deepfake",
    contexts: ["image"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "deepguard-check-image") return;
  chrome.storage.local.get("apiKey", ({ apiKey }) => {
    if (!apiKey) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "DeepGuard",
        message: "No API key set. Open the extension popup and paste your MariAnalysis API key.",
      });
      return;
    }
    analyzeImage(info.srcUrl, apiKey, tab?.id);
  });
});

async function analyzeImage(url, apiKey, tabId) {
  try {
    const res = await fetch(`${API_URL}/extend/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "Analysis failed");

    const r = data.result;
    const fake = r.fake_probability ?? 0;
    const verdict = fake >= 62 ? "FAKE" : fake >= 42 ? "UNCERTAIN" : "REAL";

    const notif = {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: `DeepGuard: ${verdict} (${Math.round(fake)}% fake)`,
      message: `${r.explanation || ""}\nTrust score ${Math.round(r.trust_score ?? 0)}/100 · ${r.risk_level ?? "low"} risk`,
    };
    chrome.notifications.create(notif);

    // Show inline result on the page if possible.
    if (tabId !== undefined) {
      chrome.tabs.sendMessage(tabId, {
        type: "DEEPGUARD_RESULT",
        verdict,
        fakeProbability: Math.round(fake),
        trustScore: Math.round(r.trust_score ?? 0),
        explanation: r.explanation || "",
      }).catch(() => {});
    }
  } catch (err) {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "DeepGuard",
      message: err.message,
    });
  }
}
