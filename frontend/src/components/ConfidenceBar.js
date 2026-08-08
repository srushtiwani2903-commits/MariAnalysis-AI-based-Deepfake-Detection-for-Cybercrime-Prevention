import { motion } from "framer-motion";

// Animated confidence / probability progress bar
export default function ConfidenceBar({ value, label, color }) {
  const v = Math.round(Math.max(0, Math.min(100, value)));
  const barColor =
    color ||
    (v >= 65 ? "from-rose-500 to-red-500" : v >= 42 ? "from-amber-400 to-yellow-500" : "from-emerald-400 to-green-500");

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
        <span className="font-mono text-sm font-bold">{v}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
        <motion.div
          className={`h-full rounded-full bg-gradient-to-r ${barColor} glow-progress`}
          initial={{ width: 0 }}
          animate={{ width: `${v}%` }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
