import { motion } from "framer-motion";

// Verdict-tinted sliding gradients: the bar is a red->green gradient and the
// fill reveals it from left to right, so the tip points at what the score means.
// authentic -> green tip at high confidence; fake -> red tip at high confidence.
const TONE_GRADIENTS = {
  authentic: "linear-gradient(90deg, #f43f5e 0%, #fbbf24 55%, #22c55e 100%)",
  fake: "linear-gradient(90deg, #22c55e 0%, #fbbf24 45%, #f43f5e 100%)",
};

// Animated confidence / probability progress bar
export default function ConfidenceBar({ value, label, color, tone }) {
  const v = Math.round(Math.max(0, Math.min(100, value)));
  const styleGrad = TONE_GRADIENTS[tone];
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
          className={`h-full rounded-full glow-progress ${styleGrad ? "" : `bg-gradient-to-r ${barColor}`}`}
          style={styleGrad ? {
            background: styleGrad,
            boxShadow: "0 0 12px rgba(52, 211, 153, 0.25)",
          } : undefined}
          initial={{ width: 0 }}
          animate={{ width: `${v}%` }}
          transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
}