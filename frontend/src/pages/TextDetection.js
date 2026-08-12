import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { DocumentTextIcon, ExclamationTriangleIcon, SparklesIcon } from "@heroicons/react/24/outline";
import ScanLoader from "../components/ScanLoader";
import api from "../api/api";

const MAX_TEXT_BYTES = 20 * 1024 * 1024 * 1024; // 20 GB

export default function TextDetection() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  const analyze = async () => {
    if (new Blob([text]).size > MAX_TEXT_BYTES) {
      setError("Text exceeds the 20 GB limit. Not more than 20 GB will accept.");
      return;
    }
    setError("");
    setAnalyzing(true);
    try {
      const { data } = await api.post("/detect/text", { text, filename: "paste-input.txt" });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.message);
      setAnalyzing(false);
    }
  };

  return (
    <div className="container-app py-10 max-w-4xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 text-white mb-4">
          <DocumentTextIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">AI Text Detection</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-xl mx-auto">
          Paste any text to detect AI-generated content using perplexity, burstiness and
          repetition scoring with sentence-level highlighting.
        </p>
      </motion.div>

      {analyzing ? (
        <ScanLoader text="Computing perplexity, burstiness and sentence anomaly scores…" />
      ) : (
        <div className="space-y-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            placeholder="Paste the text you want to verify here… (minimum 30 characters)"
            className="input !rounded-2xl resize-y font-mono text-sm"
          />
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {text.trim().split(/\s+/).filter(Boolean).length} words · {text.length} characters
            </p>
            <button onClick={analyze} disabled={text.trim().length < 30} className="btn-primary">
              <DocumentTextIcon className="w-5 h-5" /> Analyze Text
            </button>
          </div>
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
              <ExclamationTriangleIcon className="w-5 h-5" /> {error}
            </motion.div>
          )}
          <div className="mt-6 grid sm:grid-cols-3 gap-4">
            {[
              ["Perplexity Score", "Smoothness of token flow - AI text is low"],
              ["Burstiness Score", "Sentence-length variability - AI text is uniform"],
              ["Section Highlighting", "Suspicious sentences are flagged in red"],
            ].map(([t, d]) => (
              <div key={t} className="glass rounded-xl p-4">
                <p className="font-semibold text-sm flex items-center gap-2"><SparklesIcon className="w-4 h-4 text-neon-blue" />{t}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{d}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
