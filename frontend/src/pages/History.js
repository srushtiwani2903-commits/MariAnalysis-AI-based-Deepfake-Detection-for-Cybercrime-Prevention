import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  MagnifyingGlassIcon, TrashIcon, ArrowDownTrayIcon,
  ClockIcon, ExclamationTriangleIcon, FunnelIcon,
  PhotoIcon, FilmIcon, MusicalNoteIcon, DocumentTextIcon,
} from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import api from "../api/api";
import { useAuth } from "../context/AuthContext";
import { humanSize, timeAgo, formatDate } from "../utils/format";

const FILTERS = ["all", "image", "video", "audio", "text"];
const RESULTS = ["all", "fake", "authentic", "inconclusive"];

const API_URL = process.env.REACT_APP_API_URL || "/api";

// Thumbnail shown next to each history entry so it is clear which media was
// scanned. Images (and image posts) render the stored original; videos render a
// first-frame still; anything without a servable file falls back to an icon.
function HistoryThumb({ scan }) {
  const [failed, setFailed] = useState(false);
  const type = scan.scan_type;
  const hasMedia = type === "image" || type === "post" || type === "video";
  const src = `${API_URL}/history/${scan.id}/media`;
  const Icon = type === "video" ? FilmIcon
    : type === "audio" ? MusicalNoteIcon
    : type === "text" || type === "email" ? DocumentTextIcon
    : PhotoIcon;
  return (
    <div className="w-12 h-12 rounded-lg overflow-hidden flex-shrink-0 bg-gradient-to-br from-neon-blue/15 to-neon-purple/15 border border-white/10 flex items-center justify-center">
      {hasMedia && !failed ? (
        type === "video" ? (
          <video
            src={`${src}#t=0.1`}
            className="w-full h-full object-cover"
            muted
            playsInline
            preload="metadata"
            onError={() => setFailed(true)}
          />
        ) : (
          <img
            src={`${src}?thumb=1`}
            alt={scan.filename}
            loading="lazy"
            className="w-full h-full object-cover"
            onError={() => setFailed(true)}
          />
        )
      ) : (
        <Icon className="w-6 h-6 text-neon-blue" />
      )}
    </div>
  );
}

export default function History() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [type, setType] = useState(searchParams.get("type") || "all");
  const [result, setResult] = useState(searchParams.get("result") || "all");
  const [activeTab, setActiveTab] = useState(searchParams.get("type") || "all");
  const [scope, setScope] = useState("self");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const isAdmin = !!user?.is_admin;

  const fetchData = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page, limit: 50 });
    if (q) params.set("q", q);
    if (type !== "all") params.set("type", type);
    if (result !== "all") params.set("result", result);
    if (isAdmin && scope === "all") params.set("scope", "all");
    api
      .get(`/history?${params}`)
      .then((res) => {
        setItems(res.data.items);
        setTotal(res.data.total);
        setError("");
      })
      .catch((err) => {
        if (err.response?.status === 401) {
          setError("Session expired. Please log in again.");
        } else {
          setError(err.message || "Could not load history. Please try again.");
        }
      })
      .finally(() => setLoading(false));
  }, [page, q, type, result, scope, isAdmin]);

  useEffect(() => {
    const t = setTimeout(fetchData, q ? 400 : 0);
    return () => clearTimeout(t);
  }, [fetchData, q]);

  const remove = async (id) => {
    if (!window.confirm("Delete this scan from history?")) return;
    await api.delete(`/history/${id}`);
    fetchData();
  };

  const download = (id, fmt) => {
    fetch(`/api/reports/${id}/${fmt}`, { credentials: "include" })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `marianalysis-report-${id}.${fmt}`;
        a.click();
      })
      .catch(() => {});
  };

  const badge = (r) =>
    r === "fake" ? "bg-rose-500/15 text-rose-400 border-rose-400/30"
    : r === "authentic" ? "bg-emerald-500/15 text-emerald-400 border-emerald-400/30"
    : "bg-amber-500/15 text-amber-400 border-amber-400/30";

  const verdictText = (r) =>
    r === "fake" ? "FAKE" : r === "authentic" ? "REAL" : "UNCERTAIN";

  return (
    <div className="container-app py-10 space-y-6">
      <div className="flex items-center gap-3">
        <span className="p-2.5 rounded-xl bg-neon-blue/10 text-neon-blue"><ClockIcon className="w-6 h-6" /></span>
        <div>
          <h1 className="text-2xl font-bold">Scan History</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{total} scans recorded</p>
        </div>
        {isAdmin && (
          <div className="ml-auto flex items-center gap-1 bg-white/40 dark:bg-white/[0.02] backdrop-blur-xl p-1 rounded-lg border border-slate-200 dark:border-white/10">
            {[
              { key: "self", label: "My Scans" },
              { key: "all", label: "All Scans" },
            ].map((opt) => (
              <button
                key={opt.key}
                onClick={() => { setScope(opt.key); setPage(1); }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  scope === opt.key
                    ? "bg-gradient-to-r from-cyan-400 to-blue-500 text-white shadow"
                    : "text-slate-600 dark:text-slate-300 hover:bg-white/60 dark:hover:bg-white/5"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 bg-white/40 dark:bg-white/[0.02] backdrop-blur-xl p-2 rounded-xl border border-slate-200 dark:border-white/10">
        {[
          { key: "all", label: "All Scans", icon: ClockIcon, color: "from-cyan-400 to-blue-500" },
          { key: "image", label: "Image Scans", icon: PhotoIcon, color: "from-blue-400 to-indigo-500" },
          { key: "video", label: "Video Scans", icon: FilmIcon, color: "from-purple-400 to-violet-500" },
          { key: "audio", label: "Audio Scans", icon: MusicalNoteIcon, color: "from-pink-400 to-rose-500" },
          { key: "text", label: "Text Scans", icon: DocumentTextIcon, color: "from-orange-400 to-red-500" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setActiveTab(tab.key);
              setType(tab.key);
              setPage(1);
            }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.key
                ? `bg-gradient-to-r ${tab.color} text-white shadow-lg`
                : "text-slate-600 dark:text-slate-300 hover:bg-white/60 dark:hover:bg-white/5"
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Filters */}
      <GlassCard hover={false}>
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[220px]">
            <MagnifyingGlassIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              placeholder="Search by filename…"
              className="input !pl-11"
            />
          </div>
          <div className="flex items-center gap-2">
            <FunnelIcon className="w-4 h-4 text-slate-400" />
            <select value={result} onChange={(e) => { setResult(e.target.value); setPage(1); }} className="input !w-auto">
              {RESULTS.map((r) => <option key={r} value={r}>result: {r === "all" ? "all" : verdictText(r)}</option>)}
            </select>
          </div>
        </div>
      </GlassCard>

      {error && (
        <div className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
          <ExclamationTriangleIcon className="w-5 h-5" /> {error}
        </div>
      )}

      {loading ? (
        <GlassCard hover={false} className="py-12 text-center"><p className="terminal-cursor font-mono text-neon-blue">Loading history…</p></GlassCard>
      ) : items.length === 0 ? (
        <GlassCard hover={false} className="py-12 text-center">
          <p className="text-slate-400 mb-3">No scans found.</p>
          <Link to="/detect/image" className="btn-primary">Start a Scan</Link>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {items.map((s, i) => (
            <motion.div key={s.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <GlassCard hover={false} className="!p-4">
                <div className="flex flex-wrap items-center gap-4">
                  <span className={`px-3 py-1.5 rounded-full text-xs font-bold border ${badge(s.result)}`}>
                    {verdictText(s.result)}
                  </span>
                  <HistoryThumb scan={s} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{s.filename}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      #{s.id} · {s.scan_type} · {humanSize(s.file_size)} · {formatDate(s.created_at)} ({timeAgo(s.created_at)})
                      {isAdmin && scope === "all" && s.owner && ` · by ${s.owner}`}
                    </p>
                  </div>
                  <span className="font-mono text-sm font-bold text-neon-blue">
                    {Math.round(s.confidence)}% conf
                  </span>
                  <div className="flex items-center gap-1">
                    <Link to={`/results/${s.id}`} className="btn-secondary !px-3 !py-1.5 !text-xs">View</Link>
                    <button onClick={() => download(s.id, "pdf")} className="btn-secondary !px-3 !py-1.5 !text-xs" title="Download PDF">
                      <ArrowDownTrayIcon className="w-4 h-4" />
                    </button>
                    <button onClick={() => remove(s.id)} className="btn-danger !px-3 !py-1.5 !text-xs" title="Delete">
                      <TrashIcon className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))}

          {/* Pagination */}
          <div className="flex items-center justify-center gap-3 pt-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="btn-secondary !py-2">Previous</button>
            <span className="text-sm text-slate-400 font-mono">Page {page}</span>
            <button onClick={() => setPage((p) => p + 1)} disabled={items.length < 10} className="btn-secondary !py-2">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}
