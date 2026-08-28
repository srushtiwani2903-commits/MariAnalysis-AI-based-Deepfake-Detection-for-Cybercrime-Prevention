import { motion } from "framer-motion";
import { ShieldCheckIcon, ShieldExclamationIcon, QuestionMarkCircleIcon } from "@heroicons/react/24/outline";

// Verdict badge: AUTHENTIC / FAKE / INCONCLUSIVE
export default function ResultBadge({ result, confidence }) {
  const config = {
    authentic: {
      icon: ShieldCheckIcon,
      text: "AUTHENTIC",
      cls: "text-emerald-400 border-emerald-400/40 bg-emerald-400/10 shadow-glow",
    },
    fake: {
      icon: ShieldExclamationIcon,
      text: "FAKE DETECTED",
      cls: "text-rose-400 border-rose-400/40 bg-rose-400/10",
    },
    inconclusive: {
      icon: QuestionMarkCircleIcon,
      text: "INCONCLUSIVE",
      cls: "text-amber-400 border-amber-400/40 bg-amber-400/10",
    },
  };
  const c = config[result] || config.inconclusive;
  const Icon = c.icon;

  return (
    <motion.div
      initial={{ scale: 0.7, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 18 }}
      className={`stamp inline-flex items-center gap-3 px-6 py-3 ${c.cls}`}
    >
      <Icon className="w-8 h-8" />
      <div>
        <p className="font-bold text-lg leading-none">{c.text}</p>
        {confidence !== undefined && (
          <p className="text-xs opacity-80 mt-1">Confidence {Math.round(confidence)}%</p>
        )}
      </div>
    </motion.div>
  );
}
