import { motion } from "framer-motion";

// Semi-circular needle gauge for the interactive confidence meter.
export default function ConfidenceGauge({ value, label = "Confidence" }) {
  const v = Math.round(Math.max(0, Math.min(100, value ?? 0)));
  // Angle from -90 (0%) to +90 (100%)
  const angle = -90 + (v / 100) * 180;
  const color = v >= 65 ? "#fb7185" : v >= 42 ? "#fbbf24" : "#34d399";

  const grad = (
    <defs>
      <linearGradient id="gaugeArc" x1="0" y1="1" x2="1" y2="1">
        <stop offset="0%" stopColor="#34d399" />
        <stop offset="55%" stopColor="#fbbf24" />
        <stop offset="100%" stopColor="#fb7185" />
      </linearGradient>
    </defs>
  );

  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        <svg width="200" height="120" viewBox="0 0 200 120">
          {grad}
          <path d="M 20 110 A 80 80 0 0 1 180 110" stroke="url(#gaugeArc)"
            strokeWidth="14" fill="none" strokeLinecap="round"
            className="opacity-30" />
          <path d="M 20 110 A 80 80 0 0 1 180 110" stroke="url(#gaugeArc)"
            strokeWidth="14" fill="none" strokeLinecap="round"
            strokeDasharray={`${(v / 100) * 251.3} 251.3`} />
          {/* Needle */}
          <motion.g initial={{ rotate: -90 }} animate={{ rotate: angle }}
            transition={{ duration: 1, ease: "easeOut" }}
            style={{ transformOrigin: "100px 110px" }}>
            <line x1="100" y1="110" x2="100" y2="40" stroke={color}
              strokeWidth="3" strokeLinecap="round" />
          </motion.g>
          <circle cx="100" cy="110" r="7" fill={color} />
        </svg>
        <div className="absolute inset-x-0 bottom-0 text-center">
          <motion.span
            key={v}
            initial={{ scale: 1.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="font-mono text-3xl font-bold" style={{ color }}
          >
            {v}%
          </motion.span>
        </div>
      </div>
      <div className="flex justify-between w-48 text-[10px] uppercase tracking-wider text-slate-400 mt-2">
        <span>Authentic</span>
        <span>0</span>
        <span>100</span>
        <span>Fake</span>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
    </div>
  );
}
