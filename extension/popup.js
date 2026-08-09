// DeepGuard popup logic: save API key + quick URL analysis.
const API_URL = "http://localhost:5000/api";
const keyInput = document.getElementById("apiKey");
const urlInput = document.getElementById("imgUrl");
const statusEl = document.getElementById("status");
const saveBtn = document.getElementById("saveBtn");
const analyzeBtn = document.getElementById("analyzeBtn");

// Restore saved key on open.
chrome.storage.local.get("apiKey", ({ apiKey }) => {
  if (apiKey) {
    keyInput.value = apiKey;
    showStatus("Key loaded. Right-click any image to scan it.", "ok");
  }
});

saveBtn.addEventListener("click", () => {
  const key = keyInput.value.trim();
  if (!key) { showStatus("Please paste a key first.", "warn"); return; }
  chrome.storage.local.set({ apiKey: key }, () => {
    showStatus("API key saved. Right-click any image → DeepGuard.", "ok");
  });
});

analyzeBtn.addEventListener("click", async () => {
  const apiKey = keyInput.value.trim();
  const url = urlInput.value.trim();
  if (!apiKey) { showStatus("Save your API key first.", "warn"); return; }
  if (!url) { showStatus("Paste an image URL first.", "warn"); return; }

  analyzeBtn.disabled = true;
  showStatus("Analyzing…", "");
  try {
    const res = await fetch(`${API_URL}/extend/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "Analysis failed");
    renderResult(data.result);
  } catch (err) {
    showStatus(err.message, "fake");
  } finally {
    analyzeBtn.disabled = false;
  }
});

function renderResult(r) {
  const fake = Math.round(r.fake_probability ?? 0);
  const trust = Math.round(r.trust_score ?? 0);
  const cls = fake >= 62 ? "fake" : fake >= 42 ? "warn" : "ok";
  const label = fake >= 62 ? "FAKE SUSPECTED" : fake >= 42 ? "UNCERTAIN" : "LIKELY REAL";
  const color = fake >= 62 ? "#fb7185" : fake >= 42 ? "#fbbf24" : "#34d399";

  statusEl.className = cls;
  statusEl.innerHTML = `
    <b>${label}</b> — ${fake}% fake<br>
    <span style="opacity:.7">${r.explanation || ""}</span>
    <div class="bar"><div style="width:${fake}%; background:${color}"></div></div>
    <span style="opacity:.7">Trust ${trust}/100 · ${r.risk_level ?? "low"} risk · ${r.processing_time_ms}ms</span>`;
}

function showStatus(text, cls) {
  statusEl.className = cls || "";
  statusEl.textContent = text;
}
