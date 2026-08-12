import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowDownTrayIcon, ArrowLeftIcon, ClockIcon, DocumentArrowDownIcon,
  ScaleIcon, BeakerIcon, FingerPrintIcon, QrCodeIcon, ShieldCheckIcon,
  LockClosedIcon, CubeIcon, CpuChipIcon, WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import ResultBadge from "../components/ResultBadge";
import ConfidenceBar from "../components/ConfidenceBar";
import GlassCard from "../components/GlassCard";
import ScanLoader from "../components/ScanLoader";
import TrustScore from "../components/TrustScore";
import MultiModelVerdicts from "../components/MultiModelVerdicts";
import XaiReasons from "../components/XaiReasons";
import DeepfakeTimeline from "../components/DeepfakeTimeline";
import api from "../api/api";
import { formatDate, riskColor, humanSize } from "../utils/format";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5001/api";

export default function Results() {
  const { scanId } = useParams();
  const location = useLocation();
  const [scan, setScan] = useState(location.state?.result || null);
  const [full, setFull] = useState(null);
  const [loading, setLoading] = useState(!scan);
  const [downloading, setDownloading] = useState(false);
  const [proof, setProof] = useState(null);
  const [proofError, setProofError] = useState("");
  const [registering, setRegistering] = useState(false);
  const [heatmapUrl, setHeatmapUrl] = useState(null);

  useEffect(() => {
    if (!scanId) return;
    let cancelled = false;
    api.get(`/reports/${scanId}/heatmap`, { responseType: "blob" })
      .then(({ data }) => {
        if (!cancelled) setHeatmapUrl(URL.createObjectURL(data));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [scanId]);

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

  const registerCase = async () => {
    setRegistering(true);
    setProofError("");
    try {
      const { data } = await api.post(`/evidence/${scanId}/register`);
      setProof({ registered: true, block: data.block, chain_valid: data.chain_valid, intact: true, case_id: data.case?.case_id });
    } catch (e) {
      setProofError(e.response?.data?.message || e.message);
    } finally {
      setRegistering(false);
    }
  };

  const download = (fmt) => {
    setDownloading(true);
    const token = localStorage.getItem("deepguard-token");
    fetch(`${API_URL}/reports/${scanId}/${fmt}`, {
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
  const models = full?.models || scan.models || [];
  const reasons = full?.reasons || scan.reasons || [];
  const heatmapFile = full?.scan_metadata?.heatmap_file || scan.scan_metadata?.heatmap_file;
  const meta = full?.scan_metadata || scan.scan_metadata || {};
  const aiOrigin = meta.ai_origin || scan.ai_origin || "";
  const suspiciousScale = meta.suspicious_scale !== undefined && meta.suspicious_scale !== ""
    ? Number(meta.suspicious_scale)
    : (scan.suspicious_scale ?? scan.fake_probability);
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
            {aiOrigin && aiOrigin !== "authentic" && (
              <div className={`inline-flex items-center gap-3 px-5 py-2.5 rounded-2xl border ${
                aiOrigin === "ai_generated"
                  ? "text-rose-300 border-rose-400/40 bg-rose-400/10"
                  : "text-amber-300 border-amber-400/40 bg-amber-400/10"
              }`}>
                {aiOrigin === "ai_generated"
                  ? <CpuChipIcon className="w-7 h-7" />
                  : <WrenchScrewdriverIcon className="w-7 h-7" />}
                <div>
                  <p className="font-bold text-base leading-none">
                    {aiOrigin === "ai_generated"
                      ? `AI GENERATED ${scan.scan_type?.toUpperCase()}`
                      : "AI CONVERTED / MANIPULATED"}
                  </p>
                  <p className="text-xs opacity-80 mt-1">
                    {aiOrigin === "ai_generated"
                      ? "Created entirely by an AI generator"
                      : "Authentic media converted or edited using AI tools"}
                  </p>
                </div>
              </div>
            )}
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
            <ConfidenceBar value={suspiciousScale} label="Suspicious Scale" />
            <ConfidenceBar value={scan.fake_probability} label="AI / Fake Probability" />
            <ConfidenceBar value={100 - scan.confidence} label="Alternative Likelihood" />
            {suspiciousScale > scan.fake_probability && (
              <p className="text-xs text-amber-300 bg-amber-400/10 border border-amber-400/30 rounded-xl px-4 py-3 flex items-center gap-2">
                <WrenchScrewdriverIcon className="w-4 h-4" />
                Suspicion boosted because AI tools were likely used to convert or edit this media.
              </p>
            )}
          </div>
        </div>

        {/* Trust score + heatmap strip */}
        <div className="mt-8 grid lg:grid-cols-2 gap-6 pt-6 border-t border-slate-200 dark:border-white/10">
          <TrustScore value={full?.trust_score ?? scan.trust_score} />
          {heatmapFile && heatmapUrl && (
            <div className="flex items-center gap-4">
              <img
                src={heatmapUrl}
                alt="Manipulation heatmap"
                className="w-24 h-24 rounded-xl object-cover border border-slate-200 dark:border-white/10"
              />
              <div>
                <p className="text-sm font-semibold">Manipulation Heatmap</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Red regions are where the file most likely shows signs of AI editing.
                </p>
              </div>
            </div>
          )}
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
          <Link to={`/verify/scan/${scanId}`} className="btn-secondary">
            <LockClosedIcon className="w-5 h-5" /> Verify Proof
          </Link>
        </div>

        {/* Blockchain proof */}
        {(proof || proofError) && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-400/5 px-4 py-3 text-sm">
        {proofError && <p className="text-rose-400">{proofError}</p>}
        {proof && (
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
            <span className="flex items-center gap-1.5"><CubeIcon className="w-4 h-4 text-emerald-400" />
              Block #{proof.block?.index ?? proof.block_index ?? "—"}</span>
            <span>Status: <b className={proof.intact ? "text-emerald-400" : "text-rose-400"}>
              {proof.intact ? "TAMPER-EVIDENT ✓" : "INVALID"}
            </b></span>
            <span className="font-mono text-slate-500 dark:text-slate-400">hash: {(proof.block?.hash || "").slice(0, 24)}…</span>
            {(proof.block?.case_id || proof.case_id) && <span>Case: <b>{(proof.block?.case_id || proof.case_id)}</b></span>}
          </div>
        )}
          </motion.div>
        )}
        {!proof && !proofError && (
          <button onClick={registerCase} disabled={registering} className="mt-4 text-xs text-emerald-400 hover:underline">
            {registering ? "Anchoring to blockchain…" : "No blockchain proof yet — anchor this scan to the evidence ledger (generates a case ID)"}
          </button>
        )}
      </motion.div>

      {/* XAI explanation */}
      <div className="grid lg:grid-cols-3 gap-6">
        <GlassCard className="lg:col-span-2">
          <h2 className="font-bold mb-3 flex items-center gap-2">
            <ScaleIcon className="w-5 h-5 text-neon-blue" /> Why this verdict?
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{scan.explanation}</p>

          <div className="mt-5">
            <XaiReasons reasons={reasons} />
          </div>

          {models.length > 0 && (
            <div className="mt-5">
              <h3 className="text-sm font-semibold mb-3">Multi-Model Ensemble</h3>
              <MultiModelVerdicts models={models} />
            </div>
          )}

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
            Download the PDF or QR report to keep this check on record or share it with others.
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
          If this {scan.scan_type} was flagged as a deepfake, these steps can help you respond.
        </p>
        <div className="grid sm:grid-cols-3 gap-4 text-sm">
          {[
            ["Verify the source", "Confirm the sender through a second channel before trusting or forwarding."],
            ["Don't share / repost", "Spreading a detected fake makes it worse — report it instead."],
            ["Backup evidence", "Save this report as your record for authorities or platforms."],
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
          {scan.scan_type === "video" && sections[0]?.start !== undefined && (
            <div className="mb-5">
              <DeepfakeTimeline segments={sections} />
            </div>
          )}
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
