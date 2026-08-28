import { motion } from "framer-motion";

// Gradient verdict scale: green (authentic) -> amber (inconclusive) -> red (fake),
// with a marker positioned at the AI/fake probability. Thresholds mirror the
// backend (_interpret): <42 authentic, <62 inconclusive, >=62 fake.
export default function VerdictScale({ value, result }) {
  const v = Math.round(Math.max(0, Math.min(100, Number(value) || 0)));
  const markerColor =
    result === "fake" ? "bg-rose-500 border-rose-200"
    : result === "authentic" ? "bg-emerald-500 border-emerald-200"
    : "bg-amber-500 border-amber-200";

  return (
    <div className="rounded-2xl p-4 glass">
      <div className="flex items-center justify-between text-[11px] font-bold tracking-wide mb-2">
        <span className="text-emerald-500">AUTHENTIC</span>
        <span className="text-amber-500">INCONCLUSIVE</span>
        <span className="text-rose-500">FAKE</span>
      </div>
      <div className="relative h-3 rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500 shadow-inner">
        <div
          className="absolute top-1/2 -translate-y-1/2 w-px h-6 bg-slate-900/40 dark:bg-white/50"
          style={{ left: "42%" }}
          title="Inconclusive threshold (42%)"
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-px h-6 bg-slate-900/40 dark:bg-white/50"
          style={{ left: "62%" }}
          title="Fake threshold (62%)"
        />
        <motion.div
          className={`absolute -top-1 h-5 w-5 rounded-full border-2 ${markerColor} shadow-lg ring-2 ring-white/40 dark:ring-black/40`}
          initial={{ left: "0%" }}
          animate={{ left: `calc(${v}% - 10px)` }}
          transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-slate-500 dark:text-slate-400">
          Verdict: <b className="uppercase">{result || "—"}</b>
        </span>
        <span className="font-mono text-sm font-bold text-slate-800 dark:text-slate-100">
          {v}% AI probability
        </span>
      </div>
    </div>
  );
}