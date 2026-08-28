import { motion } from "framer-motion";

// Animated counter stat card
export default function StatCard({ icon: Icon, label, value, suffix = "", color = "from-neon-blue to-neon-purple", delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay, duration: 0.4 }}
      className="glass wob p-5 flex items-center gap-4"
    >
      <span className={`w-12 h-12 shrink-0 wob-sm bg-gradient-to-br ${color} flex items-center justify-center text-white`}>
        <Icon className="w-6 h-6" />
      </span>
      <div>
        <p className="text-2xl font-bold">{value}{suffix}</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      </div>
    </motion.div>
  );
}
