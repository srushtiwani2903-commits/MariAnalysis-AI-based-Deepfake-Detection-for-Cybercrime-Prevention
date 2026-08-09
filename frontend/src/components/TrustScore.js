import { motion } from "framer-motion";

// Circular trust-score gauge (0-100). Green = trustworthy, red = suspicious.
export default function TrustScore({ value, size = 120 }) {
  const v = Math.round(Math.max(0, Math.min(100, value ?? 0)));
  const r = size / 2 - 8;
  const circumference = 2 * Math.PI * r;
  const filled = (v / 100) * circumference;
  const color = v >= 70 ? "#34d399" : v >= 45 ? "#fbbf24" : "#fb7185";

  return (
    <div className="flex items-center gap-4">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} strokeWidth="9"
            className="fill-none stroke-slate-200 dark:stroke-white/10" />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r} strokeWidth="9" fill="none"
            stroke={color} strokeLinecap="round" strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - filled }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-2xl font-bold" style={{ color }}>{v}</span>
          <span className="text-[10px] uppercase tracking-wider text-slate-400">/100</span>
        </div>
      </div>
      <div className="space-y-0.5 text-xs">
        <p className="font-semibold text-slate-600 dark:text-slate-300">Evidence Trust Score</p>
        <p className={v >= 70 ? "text-emerald-400" : v >= 45 ? "text-amber-400" : "text-rose-400"}>
          {v >= 70 ? "Looks authentic" : v >= 45 ? "Mixed — worth a closer look" : "Suspicious content"}
        </p>
        <p className="text-slate-500 dark:text-slate-400 max-w-[16rem]">
          Based on metadata, AI artifacts, compression, face consistency and noise.
        </p>
      </div>
    </div>
  );
}
