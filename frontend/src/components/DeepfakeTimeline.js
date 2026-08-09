import { motion } from "framer-motion";

// Segment-wise verdict timeline for videos: each frame range gets a verdict.
export default function DeepfakeTimeline({ segments }) {
  if (!segments || segments.length === 0) return null;
  const total = segments.reduce((acc, s) => acc + (s.end - s.start), 1);
  const colorFor = (p) => (p >= 62 ? "#fb7185" : p >= 42 ? "#fbbf24" : "#34d399");

  return (
    <div>
      <h3 className="text-sm font-semibold mb-3">Segment Timeline</h3>
      <div className="flex w-full h-8 rounded-full overflow-hidden bg-slate-200 dark:bg-white/10">
        {segments.map((s, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: `${((s.end - s.start) / total) * 100}%` }}
            transition={{ delay: i * 0.07 }}
            title={`${s.start}s-${s.end}s · fake ${s.fake_probability}%`}
            className="h-full border-r border-white/60 dark:border-white/10"
            style={{ backgroundColor: colorFor(s.fake_probability) }}
          />
        ))}
      </div>
      <div className="flex justify-between mt-2 text-[10px] font-mono text-slate-400">
        <span>0:00</span>
        <span>0:{String(total).padStart(2, "0")}</span>
      </div>
      <div className="mt-2 space-y-1.5">
        {segments.map((s, i) => {
          const c = colorFor(s.fake_probability);
          return (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="w-10 h-2.5 rounded-full shrink-0" style={{ backgroundColor: c }} />
              <span className="font-mono text-slate-500 dark:text-slate-400">
                {s.start}s–{s.end}s
              </span>
              <span className="font-semibold" style={{ color: c }}>
                {s.prediction} ({Math.round(s.fake_probability)}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
