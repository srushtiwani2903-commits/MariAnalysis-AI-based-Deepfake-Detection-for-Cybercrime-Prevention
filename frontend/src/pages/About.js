import { motion } from "framer-motion";
import {
  RocketLaunchIcon, ExclamationTriangleIcon, BeakerIcon,
  CpuChipIcon, UsersIcon, LightBulbIcon,
} from "@heroicons/react/24/outline";

const objectives = [
  "Detect AI-generated and manipulated media across image, video, audio and text.",
  "Provide confidence scores and explainable (XAI) reasoning behind every verdict.",
  "Educate users about deepfake threats and how to protect themselves.",
  "Offer forensic-grade downloadable reports for cybercrime reporting.",
];

const methodology = [
  ["Problem Statement", "Deepfake technology is weaponized for fraud, defamation, misinformation and identity theft. Traditional verification fails because synthetic media is visually indistinguishable from reality."],
  ["Objective", "Build an enterprise-grade platform that uses deep learning to flag synthetic content with high confidence and clear explanations."],
  ["Approach", "Multi-modal detection: CNN + Vision Transformers for images/video, spectral analysis for audio, and NLP perplexity/burstiness for text — unified behind a single REST API."],
  ["Verification", "Heuristic ensemble provides immediate predictions; a pluggable interface allows swapping in trained models (FaceForensics++, DFDC, ASVspoof) without changing the product."],
];

const workflow = [
  ["Upload", "Image, video, audio or text submitted securely via REST API"],
  ["Preprocessing", "Frames extracted, faces localized, signals normalized"],
  ["Feature Extraction", "ELA, spectral, MFCC, temporal, linguistic features computed"],
  ["AI Inference", "Ensemble of CNN/ViT/transformer models scores the content"],
  ["Prediction", "Fake / authentic verdict with confidence and risk level"],
  ["Report", "Explainable PDF/CSV report stored and downloadable"],
];

const tech = [
  "React.js", "Tailwind CSS", "Framer Motion", "Chart.js", "React Router",
  "Python Flask", "JWT Auth", "SQLite / MySQL", "TensorFlow / PyTorch",
  "OpenCV", "MediaPipe", "DeepFace", "Librosa", "HuggingFace Transformers",
  "CNN", "Vision Transformer", "REST APIs",
];

const future = [
  "Live real-time detection during video calls (browser WebRTC integration).",
  "Distributed model serving with ONNX/TensorRT for sub-second inference.",
  "Mobile apps (iOS / Android) via React Native.",
  "Integration with social platforms & email gateways via webhooks.",
  "Deepfake news & registry for public fact-checking.",
];

export default function About() {
  return (
    <div className="container-app py-12 space-y-16">
      <div className="text-center max-w-3xl mx-auto">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <RocketLaunchIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl sm:text-4xl font-bold">About the Project</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-3">
          AI-Based Deepfake Detection for Cybercrime Prevention — a senior-project
          grade, production-ready cybersecurity platform.
        </p>
      </div>

      {/* Objectives */}
      <section>
        <h2 className="text-2xl font-bold mb-5 flex items-center gap-2"><LightBulbIcon className="w-6 h-6 text-neon-blue" /> Objectives</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          {objectives.map((o, i) => (
            <motion.div key={i} initial={{ opacity: 0, x: -16 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }}
              className="glass rounded-2xl p-5 flex gap-3">
              <span className="text-neon-blue font-bold">✓</span>
              <p className="text-sm text-slate-600 dark:text-slate-300">{o}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Problem & Methodology */}
      <section className="grid lg:grid-cols-2 gap-8">
        <div>
          <h2 className="text-2xl font-bold mb-5 flex items-center gap-2"><ExclamationTriangleIcon className="w-6 h-6 text-neon-purple" /> Problem & Approach</h2>
          <div className="space-y-4">
            {methodology.map(([t, d]) => (
              <div key={t} className="glass rounded-2xl p-5">
                <h3 className="font-bold text-neon-blue mb-1.5">{t}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">{d}</p>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-2xl font-bold mb-5 flex items-center gap-2"><BeakerIcon className="w-6 h-6 text-neon-blue" /> AI Workflow</h2>
          <div className="space-y-3">
            {workflow.map(([t, d], i) => (
              <motion.div key={t} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }}
                className="glass rounded-2xl p-4 flex items-center gap-4">
                <span className="font-mono text-neon-blue font-bold">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <p className="font-bold text-sm">{t}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{d}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Technologies */}
      <section>
        <h2 className="text-2xl font-bold mb-5 flex items-center gap-2"><CpuChipIcon className="w-6 h-6 text-neon-purple" /> Technologies Used</h2>
        <div className="flex flex-wrap gap-3">
          {tech.map((t) => (
            <span key={t} className="glass rounded-full px-4 py-2 text-sm font-medium hover:text-neon-blue hover:border-neon-blue/50 transition-colors">{t}</span>
          ))}
        </div>
      </section>

      {/* Team */}
      <section>
        <h2 className="text-2xl font-bold mb-5 flex items-center gap-2"><UsersIcon className="w-6 h-6 text-neon-blue" /> Team Members</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[["Lead Developer", "Full-stack architecture, AI pipeline"], ["AI/ML Engineer", "CNN & ViT model design"], ["UI/UX Designer", "Cybersecurity UI & animations"]].map(([role, duty]) => (
            <div key={role} className="glass rounded-2xl p-6 text-center">
              <div className="w-16 h-16 mx-auto mb-3 rounded-full bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white font-bold text-xl">
                {role[0]}
              </div>
              <p className="font-bold">{role}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{duty}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Future scope */}
      <section>
        <h2 className="text-2xl font-bold mb-5 flex items-center gap-2"><RocketLaunchIcon className="w-6 h-6 text-neon-blue" /> Future Scope</h2>
        <div className="space-y-3">
          {future.map((f, i) => (
            <div key={i} className="glass rounded-xl p-4 flex gap-3 text-sm text-slate-600 dark:text-slate-300">
              <span className="text-neon-blue font-bold">▸</span> {f}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
