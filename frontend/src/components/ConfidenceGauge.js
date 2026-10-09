import { motion } from "framer-motion";

// Semi-circular needle gauge for the interactive confidence meter.
// Colour thresholds line up with the backend verdict bands:
//   < 42 authentic (green) | 42-59 inconclusive (amber) | >= 60 fake (rose)
export default function ConfidenceGauge({ value, label = "Confidence" }) {
  const v = Math.round(Math.max(0, Math.min(100, value ?? 0)));
  // Angle from -90 (0%) to +90 (100%)
  const angle = -90 + (v / 100) * 180;
  const color = v >= 60 ? "#fb7185" : v >= 42 ? "#fbbf24" : "#34d399";

  // Gauge geometry (SVG view-box units).
  const CX = 100, CY = 110;
  const NEEDLE = 71; // needle length so the tip dot rides on the arc

  // Threshold ticks drawn along the arc (42% and 60%).
  const tick = (pct) => {
    const a = (-90 + (pct / 100) * 180) * (Math.PI / 180);
    const r1 = 66, r2 = 78;
    return {
      x1: CX + r1 * Math.sin(a),
      y1: CY - r1 * Math.cos(a),
      x2: CX + r2 * Math.sin(a),
      y2: CY - r2 * Math.cos(a),
    };
  };

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
      <svg width="200" height="132" viewBox="0 0 200 132">
        {grad}
        <path d="M 20 110 A 80 80 0 0 1 180 110" stroke="url(#gaugeArc)"
          strokeWidth="14" fill="none" strokeLinecap="round"
          className="opacity-25" />
        <path d="M 20 110 A 80 80 0 0 1 180 110" stroke="url(#gaugeArc)"
          strokeWidth="14" fill="none" strokeLinecap="round"
          strokeDasharray={`${(v / 100) * 251.3} 251.3`}
          style={{ transition: "stroke-dasharray 0.7s cubic-bezier(0.22,1,0.36,1)" }} />
        {/* Threshold ticks */}
        {[42, 60].map((p) => {
          const t = tick(p);
          return <line key={p} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
            stroke="#0f172a" strokeWidth="2" strokeLinecap="round" className="dark:stroke-white/70" />;
        })}
        {/* Needle + its tip dot rotate together around the pivot dot, so the
            needle stays attached to the dot while sweeping 0% -> 100%. */}
        <g
          style={{
            transform: `rotate(${angle}deg)`,
            transformOrigin: `${CX}px ${CY}px`,
            transformBox: "view-box",
            transition: "transform 0.9s cubic-bezier(0.22,1,0.36,1)",
          }}
        >
          <line x1={CX} y1={CY} x2={CX} y2={CY - NEEDLE} stroke={color}
            strokeWidth="3" strokeLinecap="round" />
          <circle cx={CX} cy={CY - NEEDLE} r="5" fill={color}
            stroke="#0f172a" strokeWidth="1.5" className="dark:stroke-slate-900" />
        </g>
        {/* Pivot dot the needle is anchored to */}
        <circle cx={CX} cy={CY} r="7" fill={color} />
      </svg>
      {/* Percentage sits below the pivot dot so it never overlaps it */}
      <motion.span
        key={v}
        initial={{ scale: 1.4, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="font-mono text-3xl font-bold -mt-2"
        style={{ color }}
      >
        {v}%
      </motion.span>
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
