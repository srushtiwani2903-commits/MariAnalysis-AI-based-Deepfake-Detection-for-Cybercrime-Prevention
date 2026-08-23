import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  PhotoIcon, FilmIcon, MusicalNoteIcon, DocumentTextIcon,
  ExclamationTriangleIcon, ShieldExclamationIcon, LinkIcon,
} from "@heroicons/react/24/outline";
import FileUpload from "../components/FileUpload";
import ScanLoader from "../components/ScanLoader";
import api from "../api/api";

const GB = 1024;
const MEDIA = [
  {
    key: "image", title: "Image", desc: "PNG, JPG, WebP, BMP, TIFF",
    icon: PhotoIcon, color: "accent-imgscan-dark from-neon-blue to-neon-cyan",
    accept: ".png,.jpg,.jpeg,.webp,.bmp,.tiff", maxMB: 1 * GB,
    loader: "Running error-level analysis, texture stats and metadata forensics…",
    engine: "Kaggle reference: real-and-fake-face-detection",
  },
  {
    key: "video", title: "Video", desc: "MP4, AVI, MOV, MKV, WebM",
    icon: FilmIcon, color: "from-neon-purple to-fuchsia-500",
    accept: ".mp4,.avi,.mov,.mkv,.webm", maxMB: 20 * GB,
    loader: "Extracting frames, detecting faces, running temporal analysis…",
    engine: "Kaggle reference: deepfake-videos-dataset",
  },
  {
    key: "audio", title: "Audio", desc: "MP3, WAV, OGG, FLAC, M4A",
    icon: MusicalNoteIcon, color: "from-pink-500 to-rose-400",
    accept: ".mp3,.wav,.ogg,.flac,.m4a", maxMB: 10 * GB,
    loader: "Computing spectrogram, spectral flatness and MFCC features…",
    engine: "Kaggle reference: audio-deepfake-detection-dataset",
  },
  {
    key: "text", title: "Text", desc: "Paste or type content",
    icon: DocumentTextIcon, color: "from-amber-400 to-orange-500",
    accept: ".txt,.md,.csv", maxMB: 20 * GB,
    loader: "Computing perplexity, burstiness and sentence anomaly scores…",
    engine: "Kaggle reference: ai-vs-human-text-classification",
  },
];

const MAX_TEXT_BYTES = 20 * 1024 * 1024 * 1024; // 20 GB

export default function ScanHub() {
  const navigate = useNavigate();
  const [active, setActive] = useState("image");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [scanningUrl, setScanningUrl] = useState(false);
  const current = MEDIA.find((m) => m.key === active);

  const analyzeFile = async (f) => {
    setError("");
    setAnalyzing(true);
    try {
      const form = new FormData();
      form.append("file", f);
      const { data } = await api.post(`/detect/${active}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.response?.data?.message || err.message);
      setAnalyzing(false);
    }
  };

  const analyzeText = async () => {
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
      setError(err.response?.data?.message || err.message);
      setAnalyzing(false);
    }
  };

  const analyzeUrl = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setError("");
    setScanningUrl(true);
    try {
      const { data } = await api.post("/detect/url", { url: url.trim(), media_type: active });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.response?.data?.message || err.message);
    } finally {
      setScanningUrl(false);
    }
  };

  return (
    <div className="container-app py-10 max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <ShieldExclamationIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Scan Center</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Pick a media type below, drop your file, and MariAnalysis will check it for
          signs of AI generation or manipulation — then suggest what to do next.
        </p>
      </motion.div>

      {/* Media type selector */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {MEDIA.map((m, i) => {
          const isActive = active === m.key;
          return (
            <motion.button
              key={m.key}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              onClick={() => { setActive(m.key); setError(""); }}
              className={`relative text-left rounded-2xl p-5 border-2 transition-all duration-300 ${
                isActive
                  ? "border-neon-blue bg-neon-blue/10 shadow-glow"
                  : "border-slate-200 dark:border-white/10 glass hover:border-neon-blue/40"
              }`}
            >
              <span className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${m.color} text-white mb-3`}>
                <m.icon className="w-6 h-6" />
              </span>
              <h3 className="font-bold">{m.title}</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{m.desc}</p>
              {isActive && (
                <span className="absolute top-3 right-3 text-[10px] font-bold text-neon-blue uppercase">Active</span>
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Active scanner panel */}
      <motion.div
        key={active}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-6 sm:p-8"
      >
        <div className="flex items-center gap-3 mb-6">
          <span className={`inline-flex p-2.5 rounded-xl bg-gradient-to-br ${current.color} text-white`}>
            <current.icon className="w-6 h-6" />
          </span>
          <div>
            <h2 className="text-xl font-bold">{current.title} Detection</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">{current.engine}</p>
          </div>
        </div>

        {analyzing ? (
          <ScanLoader text={current.loader} />
        ) : active === "text" ? (
          <div className="space-y-4">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={9}
              placeholder="Paste the text you want to verify here… (minimum 30 characters)"
              className="input !rounded-2xl resize-y font-mono text-sm"
            />
            <div className="flex items-center justify-between gap-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {text.trim().split(/\s+/).filter(Boolean).length} words · {text.length} characters
              </p>
              <button onClick={analyzeText} disabled={text.trim().length < 30} className="btn-primary">
                <DocumentTextIcon className="w-5 h-5" /> Analyze Text
              </button>
            </div>
          </div>
        ) : (
          <>
            <FileUpload accept={current.accept} maxMB={current.maxMB} onFile={analyzeFile}
              label={`Drop a ${current.title.toLowerCase()} to analyze`} />
            <form onSubmit={analyzeUrl} className="mt-6 flex flex-col sm:flex-row gap-3 items-end">
              <div className="flex-1 w-full">
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 flex items-center gap-1">
                  <LinkIcon className="w-3.5 h-3.5" /> Or scan {current.title.toLowerCase()} from a URL
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={`https://example.com/file.${current.key === "video" ? "mp4" : current.key === "audio" ? "mp3" : "jpg"}`}
                  className="w-full bg-white/70 dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-neon-blue/50"
                />
              </div>
              <button type="submit" disabled={scanningUrl} className="btn-secondary !py-2.5">
                {scanningUrl ? "Scanning…" : "Scan URL"}
              </button>
            </form>
          </>
        )}

        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="mt-5 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
            <ExclamationTriangleIcon className="w-5 h-5" /> {error}
          </motion.div>
        )}
      </motion.div>

      {/* Detection + prevention explainer */}
      <div className="mt-8 grid sm:grid-cols-3 gap-4">
        {[
          ["Scan", "Your file is analyzed using the built-in detection engines plus the Kaggle reference data."],
          ["Detect", "You get an AI probability, a risk level, and a breakdown of which features point to a fake."],
          ["Prevent", "Download a PDF/CSV report with practical steps to stay safe."],
        ].map(([t, d], i) => (
          <motion.div key={t} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.08 }}
            className="glass rounded-xl p-5">
            <p className="font-bold flex items-center gap-2 mb-1">
              <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-neon-blue to-neon-purple text-white text-xs flex items-center justify-center">{i + 1}</span>
              {t}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">{d}</p>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
