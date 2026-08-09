import { motion } from "framer-motion";

// Per-model verdict table for the multi-model ensemble.
export default function MultiModelVerdicts({ models }) {
  if (!models || models.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10">
      <div className="grid grid-cols-3 gap-px bg-slate-200 dark:bg-white/10 text-[11px] uppercase tracking-wider">
        <div className="bg-slate-50 dark:bg-slate-900 px-3 py-2 font-bold text-slate-500">Model</div>
        <div className="bg-slate-50 dark:bg-slate-900 px-3 py-2 font-bold text-slate-500 text-center">Verdict</div>
        <div className="bg-slate-50 dark:bg-slate-900 px-3 py-2 font-bold text-slate-500 text-right">Fake %</div>
      </div>
      {models.map((m, i) => {
        const fake = m.fake_probability ?? 0;
        const color = fake >= 62 ? "text-rose-400" : fake >= 42 ? "text-amber-400" : "text-emerald-400";
        return (
          <motion.div
            key={m.name}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.06 }}
            className="grid grid-cols-3 items-center gap-px border-t border-slate-200 dark:border-white/10 first:border-t-0"
          >
            <div className="px-3 py-2.5 text-sm font-medium">{m.name}</div>
            <div className={`px-3 py-2.5 text-sm font-bold text-center ${color}`}>
              {String(m.prediction || "").toUpperCase()}
            </div>
            <div className="px-3 py-2.5 text-right">
              <span className="font-mono text-sm font-bold">{Number(fake).toFixed(0)}%</span>
              <div className="mt-1 ml-auto h-1 w-20 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                <div className={`h-full ${color} bg-current rounded-full`} style={{ width: `${Math.min(100, fake)}%` }} />
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
