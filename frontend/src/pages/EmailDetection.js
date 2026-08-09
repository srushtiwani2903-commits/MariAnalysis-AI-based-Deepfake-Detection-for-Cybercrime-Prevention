import { useState } from "react";
import { motion } from "framer-motion";
import { EnvelopeIcon, ExclamationTriangleIcon, DocumentCheckIcon, LinkIcon } from "@heroicons/react/24/outline";
import api from "../api/api";

// Email scam / phishing / AI-written detection.
export default function EmailDetection() {
  const [raw, setRaw] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanUrl, setScanUrl] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const analyze = async (e) => {
    e?.preventDefault();
    setError("");
    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.post("/detect/email", { text: raw, subject: "" });
      setResult(data.result || data);
    } catch (err) {
      setError(err.response?.data?.message || err.message);
    } finally {
      setBusy(false);
    }
  };

  const analyzeLink = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setError("");
    setScanUrl(true);
    setResult(null);
    try {
      const { data } = await api.post("/detect/url", { url: url.trim(), media_type: "text" });
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.message || err.message);
    } finally {
      setScanUrl(false);
    }
  };

  const confidence = result?.confidence ?? 0;
  const flag = (result?.confidence ?? 0) >= 55;
  const reasons = result?.reasons || [];

  return (
    <div className="container-app py-10 max-w-4xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-pink-500 to-rose-400 text-white mb-4">
          <EnvelopeIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Email & Phishing Scanner</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Paste a suspicious email (headers + body) to check for phishing patterns, deceptive
          links, urgency tricks and AI-generated wording.
        </p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-6 sm:p-8 space-y-5">
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          rows={10}
          placeholder={"From: support@secur-verify.com\nSubject: Your account will be suspended!\n\nDear customer, click here to confirm your password immediately…"}
          className="input !rounded-2xl resize-y font-mono text-sm"
        />
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {raw.trim().split(/\s+/).filter(Boolean).length} words
          </p>
          <button onClick={analyze} disabled={busy || raw.trim().length < 20} className="btn-primary">
            {busy ? "Scanning…" : "Scan Email"}
          </button>
        </div>

        <div className="flex items-center gap-3">
          <span className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
          <span className="text-xs text-slate-400">or</span>
          <span className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
        </div>

        <form onSubmit={analyzeLink} className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 flex items-center gap-1">
              <LinkIcon className="w-3.5 h-3.5" /> Scan a suspicious link
            </label>
            <input type="url" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="https://suspicious-site.com/verify"
              className="input" />
          </div>
          <button type="submit" disabled={scanUrl} className="btn-secondary self-end">{scanUrl ? "Checking…" : "Check Link"}</button>
        </form>

        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
            <ExclamationTriangleIcon className="w-5 h-5" /> {error}
          </motion.div>
        )}

        {result && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            <div className={`rounded-2xl border px-5 py-4 ${
              flag ? "border-rose-400/40 bg-rose-400/10" : "border-emerald-400/40 bg-emerald-400/10"
            }`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <p className="font-bold flex items-center gap-2">
                  <DocumentCheckIcon className={`w-6 h-6 ${flag ? "text-rose-400" : "text-emerald-400"}`} />
                  {flag ? "Suspicious — phishing indicators found" : "No strong phishing indicators"}
                </p>
                <span className={`font-mono text-2xl font-bold ${flag ? "text-rose-400" : "text-emerald-400"}`}>
                  {confidence.toFixed(0)}%
                </span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-white/20 dark:bg-white/10 overflow-hidden">
                <div className={`h-full ${flag ? "bg-rose-400" : "bg-emerald-400"}`} style={{ width: `${confidence}%` }} />
              </div>
              <p className="text-xs mt-3 text-slate-500 dark:text-slate-400">
                {result.message || "Analysis complete. Review the flagged signals below."}
              </p>
            </div>
            {reasons.length > 0 && (
              <ul className="space-y-2">
                {reasons.slice(0, 10).map((r, i) => (
                  <li key={i} className={`flex items-start gap-2 text-sm rounded-xl px-3 py-2 border ${
                    r.passed === false
                      ? "border-rose-400/30 bg-rose-400/5 text-rose-400"
                      : "border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400"
                  }`}>
                    <span className="mt-0.5">{r.passed === false ? "⚠" : "✓"}</span>
                    <div>
                      <span>{r.check}</span>
                      {r.detail && <span className="opacity-70 text-xs"> — {r.detail}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
