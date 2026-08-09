import { motion } from "framer-motion";

// Leaderboard of most-common deepfake types (global analytics).
export default function Leaderboard({ entries }) {
  if (!entries || entries.length === 0) return null;
  const max = Math.max(...entries.map((e) => e.count), 1);
  const podium = ["from-amber-400 to-yellow-500", "from-slate-300 to-slate-400", "from-orange-400 to-amber-500"];
  return (
    <div className="space-y-3">
      {entries.map((e, i) => (
        <motion.div
          key={e.type}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.06 }}
          className="flex items-center gap-3"
        >
          <span className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold text-white bg-gradient-to-br ${podium[i] || "from-neon-blue to-neon-purple"}`}>
            {i + 1}
          </span>
          <div className="flex-1">
            <div className="flex justify-between text-sm mb-1">
              <span className="font-medium">{e.type}</span>
              <span className="font-mono text-slate-500 dark:text-slate-400">{e.count} cases</span>
            </div>
            <div className="h-2.5 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                whileInView={{ width: `${(e.count / max) * 100}%` }}
                viewport={{ once: true }}
                transition={{ duration: 0.8, delay: i * 0.08 }}
                className={`h-full rounded-full bg-gradient-to-r ${podium[i] || "from-neon-blue to-neon-purple"}`}
              />
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
