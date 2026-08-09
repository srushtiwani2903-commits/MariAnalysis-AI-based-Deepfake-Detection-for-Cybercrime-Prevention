import { motion } from "framer-motion";
import {
  MagnifyingGlassIcon, CameraIcon, CpuChipIcon, SparklesIcon,
  ScaleIcon, ShieldCheckIcon,
} from "@heroicons/react/24/outline";

// Visual AI pipeline showing the forensic processing stages.
const DEFAULT_STEPS = [
  { icon: MagnifyingGlassIcon, title: "Metadata & Provenance", desc: "EXIF, GPS, editing history" },
  { icon: CameraIcon, title: "ELA & Compression", desc: "Resave artifacts, ghost JPEGs" },
  { icon: CpuChipIcon, title: "Model Ensemble", desc: "CNN + Transformer + CLIP" },
  { icon: SparklesIcon, title: "Face / Signature", desc: "Blends, landmarks, traces" },
  { icon: ScaleIcon, title: "Cross-Verification", desc: "Cached DB + web lookups" },
  { icon: ShieldCheckIcon, title: "Trust Verdict", desc: "Score + blockchain record" },
];

export default function PipelineViz({ steps = DEFAULT_STEPS }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((s, i) => {
        const Icon = s.icon;
        return (
          <motion.div
            key={s.title}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.08 }}
            className="flex items-center gap-2"
          >
            <div className="glass rounded-xl px-3 py-2 flex items-center gap-2 min-w-[10rem]">
              <span className="w-8 h-8 shrink-0 rounded-lg bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white">
                <Icon className="w-4 h-4" />
              </span>
              <div>
                <p className="text-xs font-bold leading-tight">{s.title}</p>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">{s.desc}</p>
              </div>
            </div>
            {i < steps.length - 1 && (
              <span className="text-slate-400 text-lg">→</span>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
