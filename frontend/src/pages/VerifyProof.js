import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  CubeIcon, FingerPrintIcon, ShieldCheckIcon, XCircleIcon,
  CheckCircleIcon, MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5001/api";

export default function VerifyProof() {
  const { type, id } = useParams();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const verify = async (query) => {
    setLoading(true);
    setError("");
    setData(null);
    try {
      const q = query ?? input.trim();
      if (!q) { setError("Enter a case ID or scan ID first."); return; }
      const isCase = /^DF-\d{4}-\d+$/i.test(q);
      const endpoint = isCase
        ? `/evidence/verify-case/${encodeURIComponent(q)}`
        : `/evidence/verify-scan/${encodeURIComponent(q)}`;
      const res = await fetch(`${API_URL}${endpoint}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.message || "Could not verify.");
      setData(body);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (type && id) verify(id);
    // run once for a shared link; the form handles manual lookups
    // eslint-disable-next-line
  }, [type, id]);

  const result = data?.block || (data?.registered ? data : null);
  const caseInfo = data?.case;
  const intact = Boolean(data?.intact);
  const chainOk = Boolean(data?.chain_valid);

  return (
    <div className="container-app py-12 max-w-3xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 text-white mb-4">
          <ShieldCheckIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Verify Proof</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-xl mx-auto">
          Enter a case ID (like <span className="font-mono">DF-2026-0001</span>) or a scan ID to
          check a deepfake's blockchain evidence. No login needed.
        </p>
      </motion.div>

      <form
        onSubmit={(e) => { e.preventDefault(); verify(); }}
        className="glass-strong rounded-3xl p-6 flex flex-col sm:flex-row gap-3 mb-6"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. DF-2026-0001 or 42"
          className="input flex-1"
        />
        <button type="submit" disabled={loading} className="btn-primary">
          <MagnifyingGlassIcon className="w-5 h-5" /> {loading ? "Checking…" : "Verify"}
        </button>
      </form>

      {error && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="mb-6 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
          <XCircleIcon className="w-5 h-5" /> {error}
        </motion.div>
      )}

      {data && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
          <div className={`rounded-2xl border p-5 flex items-center gap-4 ${
            intact ? "border-emerald-400/40 bg-emerald-400/10" : "border-rose-400/40 bg-rose-400/10"
          }`}>
            {intact ? (
              <CheckCircleIcon className="w-10 h-10 text-emerald-400 shrink-0" />
            ) : (
              <XCircleIcon className="w-10 h-10 text-rose-400 shrink-0" />
            )}
            <div>
              <p className={`font-bold ${intact ? "text-emerald-400" : "text-rose-400"}`}>
                {intact ? "Evidence is intact & tamper-evident" : "Evidence could not be verified"}
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {intact
                  ? "The block hash matches the stored chain and proof-of-work is valid."
                  : "The recorded hash does not match — do not trust this evidence."}
              </p>
            </div>
          </div>

          {caseInfo && (
            <div className="glass rounded-2xl p-5 space-y-2 text-sm">
              <p className="font-semibold flex items-center gap-2">
                <FingerPrintIcon className="w-5 h-5 text-neon-blue" /> Case {caseInfo.case_id}
              </p>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <span className="text-slate-500 dark:text-slate-400">Status</span>
                <span className="font-medium">{caseInfo.status}</span>
                <span className="text-slate-500 dark:text-slate-400">Platform</span>
                <span className="font-medium">{caseInfo.platform || "—"}</span>
                <span className="text-slate-500 dark:text-slate-400">Registered</span>
                <span className="font-medium">{caseInfo.created_at ? new Date(caseInfo.created_at).toLocaleString() : "—"}</span>
              </div>
              {data.scan && (
                <div className="pt-2 border-t border-slate-200 dark:border-white/10">
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Scan outcome</p>
                  <p className="font-medium">
                    {data.scan.result || "—"} · {Math.round(data.scan.fake_probability || 0)}% fake probability
                    · {data.scan.scan_type || "—"}
                  </p>
                </div>
              )}
            </div>
          )}

          {result && (
            <div className="glass rounded-2xl p-5">
              <p className="font-semibold flex items-center gap-2 mb-3">
                <CubeIcon className="w-5 h-5 text-neon-blue" /> Blockchain Block
              </p>
              <div className="space-y-1.5 font-mono text-[11px] text-slate-500 dark:text-slate-400 break-all">
                <p><span className="text-slate-400 dark:text-slate-500">index:</span> #{result.index}</p>
                <p><span className="text-slate-400 dark:text-slate-500">hash:</span> {result.hash}</p>
                <p><span className="text-slate-400 dark:text-slate-500">prev:</span> {result.prev_hash}</p>
                <p><span className="text-slate-400 dark:text-slate-500">timestamp:</span> {result.timestamp}</p>
                <p><span className="text-slate-400 dark:text-slate-500">nonce:</span> {result.nonce}</p>
                {caseInfo?.report_hash && (
                  <p><span className="text-slate-400 dark:text-slate-500">report:</span> {caseInfo.report_hash}</p>
                )}
              </div>
              <p className={`mt-3 text-xs font-semibold ${chainOk ? "text-emerald-400" : "text-rose-400"}`}>
                Full chain valid: {chainOk ? "yes" : "no"}
              </p>
            </div>
          )}

          <div className="text-center text-xs text-slate-500 dark:text-slate-400">
            Want to register new evidence?{" "}
            <Link to="/evidence" className="text-neon-blue hover:underline">Go to the Evidence portal</Link>
          </div>
        </motion.div>
      )}
    </div>
  );
}
