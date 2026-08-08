import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowDownTrayIcon, ArrowLeftIcon, ClockIcon, DocumentArrowDownIcon,
  ScaleIcon, BeakerIcon, FingerPrintIcon, QrCodeIcon, ShieldCheckIcon,
} from "@heroicons/react/24/outline";
import ResultBadge from "../components/ResultBadge";
import ConfidenceBar from "../components/ConfidenceBar";
import GlassCard from "../components/GlassCard";
import ScanLoader from "../components/ScanLoader";
import api from "../api/api";
import { formatDate, riskColor, humanSize } from "../utils/format";

export default function Results() {
  const { scanId } = useParams();
  const location = useLocation();
  const [scan, setScan] = useState(location.state?.result || null);
  const [full, setFull] = useState(null);
  const [loading, setLoading] = useState(!scan);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (scan) return;
    api
      .get(`/history/${scanId}`)
      .then((res) => setScan(res.data.scan))
      .finally(() => setLoading(false));
  }, [scanId, scan]);

  useEffect(() => {
    if (scan && scan.scan_type) {
      api.get(`/history/${scanId}`).then((res) => setFull(res.data.scan)).catch(() => {});
    }
  }, [scanId, scan]);

  const download = (fmt) => {
    setDownloading(true);
    const token = localStorage.getItem("deepguard-token");
    fetch(`${process.env.REACT_APP_API_URL || "http://localhost:5000/api"}/reports/${scanId}/${fmt}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `marianalysis-report-${scanId}.${fmt}`;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch(() => {})
      .finally(() => setDownloading(false));
  };

  if (loading) return <div className="container-app"><ScanLoader text="Loading detection results…" /></div>;
  if (!scan) return (
    <div className="container-app py-20 text-center">
      <p className="text-slate-400 mb-4">Result not found.</p>
      <Link to="/history" className="btn-primary">Back to History</Link>
    </div>
  );

  const features = full?.model?.features || scan.features || {};
  const sections = full?.suspicious_sections || scan.suspicious_sections || [];
  const summary = `${scan.result} ${scan.filename} confidence ${Math.round(scan.confidence)}% fake probability ${Math.round(scan.fake_probability)}%. ${scan.explanation || ""}`;

  return (
    <div className="container-app py-10 space-y-8">
      {/* Back + header */}
      <div className="flex items-center justify-between">
        <Link to="/history" className="btn-secondary !px-4 !py-2 !text-sm">
          <ArrowLeftIcon className="w-4 h-4" /> History
        </Link>
        <span className="text-xs font-mono text-slate-400">SCAN #{scanId}</span>
      </div>

      {/* Hero result card */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        data-readable={summary}
        className="glass-strong rounded-3xl p-8 relative overflow-hidden"
      >
        <div className="scan-overlay opacity-25" />
        <div className="grid lg:grid-cols-2 gap-8 items-center">
          <div className="space-y-5">
            <ResultBadge result={scan.result} confidence={scan.confidence} />
            <div>
              <h1 className="text-2xl font-bold truncate">{scan.filename}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                {scan.scan_type?.toUpperCase()} · {humanSize(scan.file_size)} · {formatDate(scan.created_at)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className={`text-xs font-bold px-3 py-1.5 rounded-full border border-current/30 ${riskColor(scan.risk_level)}`}>
                RISK: {scan.risk_level?.toUpperCase()}
              </span>
              <span className="text-xs font-bold px-3 py-1.5 rounded-full glass flex items-center gap-1.5">
                <ClockIcon className="w-3.5 h-3.5" /> {scan.processing_time_ms} ms
              </span>
              <span className="text-xs font-bold px-3 py-1.5 rounded-full glass flex items-center gap-1.5">
                <BeakerIcon className="w-3.5 h-3.5" /> {full?.model?.model_name || scan.model || "ensemble-v1"}
              </span>
              {(scan.scan_metadata?.reference_dataset || scan.reference_dataset) && (
                <span title="Reference dataset used to back this scan"
                  className="text-xs font-bold px-3 py-1.5 rounded-full glass flex items-center gap-1.5">
                  <FingerPrintIcon className="w-3.5 h-3.5 text-neon-purple" />
                  Kaggle: {String(scan.scan_metadata?.reference_dataset || scan.reference_dataset).split("/")[0]}
                </span>
              )}
            </div>
          </div>

          {/* Confidence meters */}
          <div className="space-y-5">
            <ConfidenceBar value={scan.confidence} label={`Result Confidence (${scan.result})`} />
            <ConfidenceBar value={scan.fake_probability} label="AI / Fake Probability" />
            <ConfidenceBar value={100 - scan.confidence} label="Alternative Likelihood" />
          </div>
        </div>

        {/* Download bar */}
        <div className="mt-8 flex flex-wrap gap-3 pt-6 border-t border-slate-200 dark:border-white/10">
          <button onClick={() => download("pdf")} disabled={downloading} className="btn-primary">
            <DocumentArrowDownIcon className="w-5 h-5" /> Download PDF
          </button>
          <button onClick={() => download("csv")} disabled={downloading} className="btn-secondary">
            <ArrowDownTrayIcon className="w-5 h-5" /> Export CSV
          </button>
          <button onClick={() => download("qr")} disabled={downloading} className="btn-secondary">
            <QrCodeIcon className="w-5 h-5" /> QR Code
          </button>
        </div>
      </motion.div>

      {/* XAI explanation */}
      <div className="grid lg:grid-cols-3 gap-6">
        <GlassCard className="lg:col-span-2">
          <h2 className="font-bold mb-3 flex items-center gap-2">
            <ScaleIcon className="w-5 h-5 text-neon-blue" /> Explainable AI — Why this verdict?
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{scan.explanation}</p>

          {Object.keys(features).length > 0 && (
            <div className="mt-5">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <FingerPrintIcon className="w-4 h-4 text-neon-purple" /> Influencing Features
              </h3>
              <div className="grid sm:grid-cols-2 gap-3">
                {Object.entries(features).filter(([, v]) => typeof v === "number").slice(0, 8).map(([k, v]) => (
                  <div key={k}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="capitalize text-slate-500 dark:text-slate-400">{k.replace(/_/g, " ")}</span>
                      <span className="font-mono">{typeof v === "number" ? (v * 100).toFixed(0) : v}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-neon-purple to-neon-blue"
                           style={{ width: `${Math.min(100, Math.abs(v) * 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <h2 className="font-bold mb-3 flex items-center gap-2">
            <ShieldCheckIcon className="w-5 h-5 text-emerald-400" /> Recommended Actions
          </h2>
          <ul className="space-y-2.5">
            {(scan.recommendations || "").split("\n").filter(Boolean).map((r, i) => (
              <li key={i} className="text-sm text-slate-600 dark:text-slate-300 flex gap-2">
                <span className="text-emerald-400 font-bold">▸</span> {r}
              </li>
            ))}
          </ul>
          <div className="mt-4 pt-4 border-t border-slate-200 dark:border-white/10 text-xs text-slate-500 dark:text-slate-400">
            Download the forensic PDF / QR report to share this verification and warn others.
          </div>
        </GlassCard>
      </div>

      {/* Prevention center */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-6 sm:p-8">
        <h2 className="font-bold mb-1 flex items-center gap-2">
          <ShieldCheckIcon className="w-6 h-6 text-emerald-400" /> Prevention Guidance
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-5">
          Protecting yourself against {scan.scan_type} deepfakes — act on these steps.
        </p>
        <div className="grid sm:grid-cols-3 gap-4 text-sm">
          {[
            ["Verify the source", "Confirm the sender through a second channel before trusting or forwarding."],
            ["Don't share / repost", "Spreading a detected fake amplifies harm — report it instead."],
            ["Backup evidence", "Save this forensic report as your record for authorities/platforms."],
          ].map(([t, d], i) => (
            <div key={t} className="rounded-2xl bg-white/40 dark:bg-white/5 p-4">
              <span className="inline-flex w-7 h-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 text-white font-bold text-xs mb-2">{i + 1}</span>
              <p className="font-semibold text-emerald-600 dark:text-emerald-400">{t}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{d}</p>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Suspicious sections for text / video timeline */}
      {sections.length > 0 && (
        <GlassCard>
          <h2 className="font-bold mb-4">
            {scan.scan_type === "text" ? "Suspicious Sentences" : "Timeline Analysis (frames / face presence)"}
          </h2>
          <div className="space-y-2 max-h-80 overflow-y-auto pr-2 no-scrollbar">
            {sections.slice(0, 20).map((s, i) => {
              const score = s.score !== undefined ? s.score * 100 : (s.face ? 70 : 30);
              return (
                <div key={i} className={`rounded-xl px-4 py-2.5 text-sm border ${
                  score > 60 ? "border-rose-400/30 bg-rose-400/5 text-rose-300"
                  : score > 40 ? "border-amber-400/30 bg-amber-400/5 text-amber-300"
                  : "border-slate-200 dark:border-white/10"}`}>
                  {s.text ? (
                    <>{s.text}<span className="ml-2 font-mono text-xs opacity-70">[{score.toFixed(0)}% suspicious]</span></>
                  ) : (
                    <span className="font-mono text-xs">
                      t={s.t}s · face={s.face ? "yes" : "no"} · sharpness={s.sharpness}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}

      {/* Metadata */}
      <GlassCard hover={false}>
        <h2 className="font-bold mb-4">File Metadata</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(full?.scan_metadata || scan.metadata || {}).slice(0, 12).map(([k, v]) => (
            <div key={k} className="rounded-xl bg-white/40 dark:bg-white/5 p-3">
              <p className="text-xs text-slate-500 dark:text-slate-400 capitalize">{k.replace(/_/g, " ")}</p>
              <p className="font-mono text-xs mt-1 truncate">{String(v).slice(0, 40)}</p>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
