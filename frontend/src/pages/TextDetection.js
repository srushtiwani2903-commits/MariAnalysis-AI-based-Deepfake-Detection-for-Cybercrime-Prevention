import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  DocumentTextIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
  CloudArrowUpIcon,
  XCircleIcon,
} from "@heroicons/react/24/outline";
import ScanLoader from "../components/ScanLoader";
import FileUpload from "../components/FileUpload";
import api from "../api/api";

const MAX_TEXT_BYTES = 20 * 1024 * 1024 * 1024; // 20 GB (backend limit)
const MAX_READ_BYTES = 20 * 1024 * 1024; // don't read giant files into the textarea

export default function TextDetection() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  const loadFileContent = (f) => {
    setError("");
    if (!f) return;
    if (f.size > MAX_READ_BYTES) {
      setError("This file is too large to load into the editor (max 20 MB).");
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => setError("Could not read the file. Please try another one.");
    reader.onload = () => {
      setText(String(reader.result || ""));
      setFileName(f.name || "");
    };
    reader.readAsText(f);
  };

  const analyze = async () => {
    if (new Blob([text]).size > MAX_TEXT_BYTES) {
      setError("Text exceeds the 20 GB limit. Not more than 20 GB will accept.");
      return;
    }
    setError("");
    setAnalyzing(true);
    try {
      const { data } = await api.post("/detect/text", {
        text,
        filename: fileName || "paste-input.txt",
      });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.response?.data?.message || err.message);
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
          Paste any text — or drag & drop a .txt file — to detect AI-generated content using
          perplexity, burstiness and repetition scoring with sentence-level highlighting.
        </p>
      </motion.div>

      {analyzing ? (
        <ScanLoader text="Computing perplexity, burstiness and sentence anomaly scores…" />
      ) : (
        <div className="space-y-4">
          <FileUpload
            accept=".txt,text/plain,text/markdown,.md"
            maxMB={20}
            label="Drop a text file here, or click to browse"
            hint="Accepts .txt and .md — content is loaded into the editor below · Max 20 MB"
            onFile={loadFileContent}
          />

          <div
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragActive(false);
              loadFileContent(e.dataTransfer.files?.[0]);
            }}
            className={`relative rounded-2xl transition-all duration-200 ${
              dragActive ? "ring-2 ring-neon-blue bg-neon-blue/5" : ""
            }`}
          >
            <textarea
              value={text}
              onChange={(e) => { setText(e.target.value); setFileName(""); }}
              rows={10}
              placeholder="Paste the text you want to verify here, or drop a .txt file anywhere on this box… (minimum 30 characters)"
              className="input !rounded-2xl resize-y font-mono text-sm"
            />
            {dragActive && (
              <div className="absolute inset-0 flex flex-col items-center justify-center rounded-2xl bg-slate-900/70 dark:bg-slate-900/80 backdrop-blur-sm pointer-events-none">
                <CloudArrowUpIcon className="w-10 h-10 text-neon-blue" />
                <p className="mt-2 text-sm font-semibold text-white">Release to load the text file</p>
              </div>
            )}
          </div>

          {fileName && (
            <div className="flex items-center gap-2 text-xs text-emerald-500 bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-2.5">
              <DocumentTextIcon className="w-4 h-4" />
              <span className="truncate flex-1">Loaded {fileName}</span>
              <button onClick={() => { setFileName(""); }} className="hover:text-rose-400 transition-colors" aria-label="Clear file">
                <XCircleIcon className="w-4 h-4" />
              </button>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {text.trim().split(/\s+/).filter(Boolean).length} words · {text.length} characters
            </p>
            <div className="flex items-center gap-3">
              <button onClick={analyze} disabled={text.trim().length < 30} className="btn-primary">
                <DocumentTextIcon className="w-5 h-5" /> Analyze Text
              </button>
            </div>
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