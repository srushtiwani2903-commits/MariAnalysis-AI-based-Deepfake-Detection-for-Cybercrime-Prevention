import { motion } from "framer-motion";

// Full-screen / in-card AI processing animation
export default function ScanLoader({ text = "Analyzing with AI models..." }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-6">
      <div className="relative w-28 h-28">
        <motion.div
          className="absolute inset-0 rounded-full border-2 border-neon-blue/40"
          animate={{ rotate: 360 }}
          transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute inset-2 rounded-full border-2 border-neon-purple/50 border-t-neon-purple"
          animate={{ rotate: -360 }}
          transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute inset-5 rounded-full bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white"
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 1.2, repeat: Infinity }}
        >
          <svg className="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-9-9" strokeLinecap="round" />
            <path d="M21 3v6h-6" strokeLinecap="round" />
          </svg>
        </motion.div>
        <span className="absolute -inset-3 rounded-full border border-neon-blue/20 animate-pulse-slow" />
      </div>

      <div className="w-64 h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
        <motion.div
          className="h-full bg-gradient-to-r from-neon-blue to-neon-purple shimmer"
          initial={{ width: "0%" }}
          animate={{ width: "100%" }}
          transition={{ duration: 2.4, repeat: Infinity }}
        />
      </div>

      <p className="terminal-cursor font-mono text-sm text-neon-blue/90">{text}</p>
    </div>
  );
}
