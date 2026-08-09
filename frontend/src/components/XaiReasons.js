import { motion } from "framer-motion";
import { CheckCircleIcon, XCircleIcon } from "@heroicons/react/24/outline";

// Explainable-AI reason checklist: which checks passed / failed.
export default function XaiReasons({ reasons }) {
  if (!reasons || reasons.length === 0) return null;
  const passed = reasons.filter((r) => r.passed).length;
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">Detection Reasons</h3>
        <span className="text-xs font-mono text-slate-400">
          {passed}/{reasons.length} passed
        </span>
      </div>
      <div className="space-y-2">
        {reasons.slice(0, 12).map((r, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className={`flex items-start gap-2.5 rounded-xl border px-3 py-2 text-sm ${
              r.passed
                ? "border-emerald-400/30 bg-emerald-400/5"
                : "border-rose-400/30 bg-rose-400/5"
            }`}
          >
            {r.passed ? (
              <CheckCircleIcon className="w-5 h-5 text-emerald-400 shrink-0" />
            ) : (
              <XCircleIcon className="w-5 h-5 text-rose-400 shrink-0" />
            )}
            <div>
              <p className={`font-medium ${r.passed ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}>
                {r.check}
              </p>
              {r.detail && <p className="text-xs text-slate-500 dark:text-slate-400">{r.detail}</p>}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
