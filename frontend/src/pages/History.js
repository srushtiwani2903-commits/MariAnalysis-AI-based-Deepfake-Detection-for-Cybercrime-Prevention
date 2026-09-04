import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  MagnifyingGlassIcon, TrashIcon, ArrowDownTrayIcon,
  ClockIcon, ExclamationTriangleIcon, FunnelIcon,
} from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import api from "../api/api";
import { humanSize, timeAgo } from "../utils/format";

const FILTERS = ["all", "image", "video", "audio", "text"];
const RESULTS = ["all", "fake", "authentic", "inconclusive"];

export default function History() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [type, setType] = useState("all");
  const [result, setResult] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page, limit: 10 });
    if (q) params.set("q", q);
    if (type !== "all") params.set("type", type);
    if (result !== "all") params.set("result", result);
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
  }, [page, q, type, result]);

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

  return (
    <div className="container-app py-10 space-y-6">
      <div className="flex items-center gap-3">
        <span className="p-2.5 rounded-xl bg-neon-blue/10 text-neon-blue"><ClockIcon className="w-6 h-6" /></span>
        <div>
          <h1 className="text-2xl font-bold">Scan History</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{total} scans recorded</p>
        </div>
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
            <select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} className="input !w-auto">
              {FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <select value={result} onChange={(e) => { setResult(e.target.value); setPage(1); }} className="input !w-auto">
              {RESULTS.map((r) => <option key={r} value={r}>result: {r}</option>)}
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
                    {s.result.toUpperCase()}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{s.filename}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      #{s.id} · {s.scan_type} · {humanSize(s.file_size)} · {timeAgo(s.created_at)}
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
