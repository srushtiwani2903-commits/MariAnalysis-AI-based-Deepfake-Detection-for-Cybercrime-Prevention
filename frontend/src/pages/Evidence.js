import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldExclamationIcon, DocumentArrowDownIcon,
  FingerPrintIcon, EyeIcon, XMarkIcon, ExclamationTriangleIcon,
  CubeIcon, PlusIcon,
} from "@heroicons/react/24/outline";
import api from "../api/api";

// Evidence reporting: flagged deepfakes get a case ID on a blockchain-style
// ledger you can share with platforms or authorities.
export default function Evidence() {
  const [cases, setCases] = useState([]);
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({ scan_id: "", platform: "", notes: "" });

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [{ data: c }, { data: h }] = await Promise.all([
        api.get("/evidence/cases"),
        api.get("/history?limit=100"),
      ]);
      setCases(c.cases || []);
      const reported = new Set((c.cases || []).map((x) => x.scan_id));
      setScans((h.items || []).filter((s) => !reported.has(s.id)));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/evidence/${form.scan_id}/register`, {
        platform: form.platform,
        notes: form.notes,
      });
      setShowForm(false);
      setForm({ scan_id: "", platform: "", notes: "" });
      setDetail({
        case_id: data.case?.case_id,
        status: data.case?.status,
        platform: data.case?.platform,
        notes: data.case?.notes,
        created_at: data.case?.created_at,
        report_hash: data.case?.report_hash,
        block: data.block,
        chain_valid: data.chain_valid,
      });
      await load();
    } catch (err) {
      setError(err.response?.data?.message || err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="container-app py-10 max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 text-white mb-4">
          <ShieldExclamationIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Evidence & Cybercrime Reporting</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Anchor detected deepfakes into an immutable SHA-256 evidence ledger. Each case gets
          an official ID you can share with platforms or authorities.
        </p>
      </motion.div>

      {error && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="mb-6 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
          <ExclamationTriangleIcon className="w-5 h-5" /> {error}
        </motion.div>
      )}

      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <FingerPrintIcon className="w-6 h-6 text-neon-blue" /> Case Registry
        </h2>
        <button onClick={() => { setShowForm((s) => !s); setError(""); }} className="btn-primary">
          <PlusIcon className="w-5 h-5" /> {showForm ? "Close" : "Register Scan"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            onSubmit={submit}
            className="glass-strong rounded-3xl p-6 space-y-4 overflow-hidden mb-8"
          >
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Choose a scan that detected a deepfake to anchor it in the evidence ledger.
            </p>
            {scans.length === 0 ? (
              <p className="text-sm text-amber-400">All your scans are already registered. Run a new scan and it will appear here.</p>
            ) : (
              <>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Scan to report</label>
                  <select value={form.scan_id} onChange={(e) => setForm((f) => ({ ...f, scan_id: e.target.value }))} className="input">
                    <option value="">Select a scan…</option>
                    {scans.map((s) => (
                      <option key={s.id} value={s.id}>
                        #{s.id} · {s.filename} · {s.result} ({Math.round(s.fake_probability || 0)}% fake)
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Platform / source (optional)</label>
                  <input value={form.platform} onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value }))}
                    placeholder="e.g. WhatsApp, Facebook, email, video call" className="input" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Notes (optional)</label>
                  <textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                    rows={3} placeholder="Context for investigators…" className="input !rounded-2xl resize-y" />
                </div>
                <div className="flex justify-end">
                  <button type="submit" disabled={busy || !form.scan_id} className="btn-primary">
                    {busy ? "Anchoring…" : "Register & Get Case ID"}
                  </button>
                </div>
              </>
            )}
          </motion.form>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="text-center py-16 text-slate-400 animate-pulse">Loading cases…</div>
      ) : cases.length === 0 ? (
        <div className="text-center py-16 text-slate-400 glass rounded-3xl">
          No cases registered yet. Your first report helps the fight against deepfake fraud.
        </div>
      ) : (
        <div className="space-y-3">
          {cases.map((c, i) => (
            <motion.div key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
              className="glass rounded-2xl p-4 flex flex-wrap items-center gap-4 justify-between">
              <div className="flex items-center gap-3 min-w-[12rem]">
                <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-neon-blue to-neon-purple text-white text-xs font-bold flex items-center justify-center">
                  <FingerPrintIcon className="w-5 h-5" />
                </span>
                <div>
                  <p className="font-semibold font-mono text-sm">{c.case_id}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {c.scan?.filename} · {c.status}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                  c.block ? "bg-emerald-400/10 text-emerald-400 border border-emerald-400/30" : "bg-amber-400/10 text-amber-400 border border-amber-400/30"
                }`}>
                  {c.block ? "✓ anchored" : "no block"}
                </span>
                <button onClick={() => setDetail(c)} className="btn-secondary !py-1.5 !px-3 text-xs">
                  <EyeIcon className="w-4 h-4" /> View
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {detail && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
            onClick={() => setDetail(null)}>
            <motion.div initial={{ scale: 0.95, y: 10 }} animate={{ scale: 1, y: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-strong rounded-3xl max-w-lg w-full p-6 max-h-[85vh] overflow-y-auto">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <p className="text-xs text-neon-blue font-mono">CASE ID</p>
                  <h3 className="text-2xl font-bold font-mono">{detail.case_id}</h3>
                </div>
                <button onClick={() => setDetail(null)} aria-label="Close">
                  <XMarkIcon className="w-6 h-6" />
                </button>
              </div>
              <div className="space-y-2 text-sm">
                {[["Status", detail.status],
                  ["Platform", detail.platform || "—"],
                  ["Registered", detail.created_at],
                  ["Scan", detail.scan ? `#${detail.scan_id} · ${detail.scan.filename} (${Math.round(detail.scan?.fake_probability || 0)}% fake)` : `#${detail.scan_id}`],
                  ["Report hash", detail.report_hash ? `${detail.report_hash.slice(0, 24)}…` : "—"],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 border-b border-slate-200 dark:border-white/10 pb-2">
                    <span className="text-slate-500 dark:text-slate-400">{k}</span>
                    <span className="font-medium text-right break-all">{v}</span>
                  </div>
                ))}
                <div className="pt-2">
                  <p className="text-slate-500 dark:text-slate-400 text-xs mb-1">Notes</p>
                  <p className="text-sm whitespace-pre-wrap">{detail.notes || "—"}</p>
                </div>
                {detail.block && (
                  <div className="rounded-2xl border border-emerald-400/30 bg-emerald-400/5 p-3">
                    <p className="flex items-center gap-2 font-semibold text-emerald-400 text-xs mb-2">
                      <CubeIcon className="w-4 h-4" /> Blockchain Anchor
                    </p>
                    <div className="space-y-1 font-mono text-[11px] text-slate-500 dark:text-slate-400 break-all">
                      <p>block #{detail.block.index}</p>
                      <p>hash: {detail.block.hash.slice(0, 32)}…</p>
                      <p>prev: {detail.block.prev_hash.slice(0, 20)}…</p>
                      <p>timestamp: {detail.block.timestamp}</p>
                    </div>
                  </div>
                )}
              </div>
              <div className="mt-5 flex gap-3">
                {detail.block && (
                  <Link to={`/verify/scan/${detail.scan_id}`} className="btn-secondary flex-1 justify-center text-xs">
                    Re-verify
                  </Link>
                )}
                <button onClick={() => setDetail(null)} className="btn-primary flex-1 justify-center text-xs">Close</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
