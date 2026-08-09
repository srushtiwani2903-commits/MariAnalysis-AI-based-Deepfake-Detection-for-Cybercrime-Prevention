import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import {
  ShieldCheckIcon,
  PhotoIcon,
  FilmIcon,
  MusicalNoteIcon,
  DocumentTextIcon,
  ChartBarIcon,
  LockClosedIcon,
  SparklesIcon,
  ArrowRightIcon,
  FingerPrintIcon,
  BeakerIcon,
  CloudArrowUpIcon,
  Cog6ToothIcon,
} from "@heroicons/react/24/outline";
import ParticleBackground from "../components/ParticleBackground";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";

const stats = [
  { value: "98.7%", label: "Detection Accuracy" },
  { value: "2.4M+", label: "Media Files Analyzed" },
  { value: "150K+", label: "Fake Contents Flagged" },
  { value: "24/7", label: "Real-time Protection" },
];

const features = [
  {
    icon: PhotoIcon,
    title: "Image Deepfake Detection",
    desc: "CNN + Vision Transformer analysis with Error Level Analysis, metadata forensics and heatmap visualization to spot manipulated faces and edited pixels.",
    color: "from-neon-blue to-cyan-400",
  },
  {
    icon: FilmIcon,
    title: "Video Manipulation Detection",
    desc: "Frame-by-frame face extraction with MediaPipe, temporal consistency checks and lip-sync analysis to expose AI-generated video.",
    color: "from-neon-purple to-fuchsia-500",
  },
  {
    icon: MusicalNoteIcon,
    title: "AI Voice Clone Detection",
    desc: "Librosa spectrogram analysis of spectral flatness, MFCC variance and prosody to catch cloned or synthetic voices in audio files.",
    color: "from-pink-500 to-rose-400",
  },
  {
    icon: DocumentTextIcon,
    title: "AI Text Detection",
    desc: "Perplexity and burstiness scoring with sentence-level highlighting to identify LLM-generated text, phishing and AI-written reports.",
    color: "from-amber-400 to-orange-500",
  },
];

const workflow = [
  { icon: CloudArrowUpIcon, title: "Upload", desc: "Drop an image, video, audio or text file into the secure portal." },
  { icon: BeakerIcon, title: "Preprocessing", desc: "Frames are extracted, faces detected, audio and text normalized." },
  { icon: Cog6ToothIcon, title: "Feature Extraction", desc: "ELA, spectral, temporal and linguistic features are computed." },
  { icon: FingerPrintIcon, title: "AI Inference", desc: "CNN / ViT / Transformer ensemble produces a prediction." },
  { icon: ChartBarIcon, title: "Confidence Score", desc: "Fake probability and risk level with explainable AI factors." },
  { icon: ShieldCheckIcon, title: "Report", desc: "Downloadable PDF/CSV report with QR verification, stored in history." },
];

export default function Home() {
  const { isAuthenticated } = useAuth();
  const { dark } = useTheme();

  return (
    <div className="relative overflow-hidden">
      <ParticleBackground className={dark ? "" : "opacity-60"} density={80} />
      <div className="cyber-grid absolute inset-0" />

      {/* ---------- HERO ---------- */}
      <section className="relative min-h-[88vh] flex items-center">
        <div className="container-app grid lg:grid-cols-2 gap-12 items-center py-16">
          <div>
            <motion.span
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass text-xs font-medium mb-6"
            >
              <SparklesIcon className="w-4 h-4 text-neon-blue" />
              Deepfake Detection You Can Actually Use
            </motion.span>

            <motion.h1
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-tight"
            >
              Detect <span className="neon-text">Deepfakes</span> Before They
              Strike
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="mt-6 text-lg text-slate-600 dark:text-slate-300"
            >
              MariAnalysis checks images, videos, audio and text for signs of
              AI-generated or manipulated content — so you can tell what's real
              from what isn't, before it causes problems.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mt-8 flex flex-wrap gap-4"
            >
              <Link to={isAuthenticated ? "/detect/image" : "/register"} className="btn-primary !px-8 !py-3.5 !text-base">
                {isAuthenticated ? "Scan Content" : "Get Started Free"}
                <ArrowRightIcon className="w-5 h-5" />
              </Link>
              <a href="#features" className="btn-secondary !px-8 !py-3.5 !text-base">
                Explore Features
              </a>
            </motion.div>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="mt-6 font-mono text-xs text-slate-400 dark:text-slate-500 terminal-cursor"
            >
              $ marianalysis scan --media image --model ensemble --explain yes
            </motion.p>
          </div>

          {/* Hero visual */}
          <motion.div
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.25 }}
            className="relative"
          >
            <div className="glass-strong rounded-3xl p-6 relative">
              <div className="scan-overlay" />
              <div className="flex items-center gap-2 mb-5">
                <span className="w-3 h-3 rounded-full bg-rose-400" />
                <span className="w-3 h-3 rounded-full bg-amber-400" />
                <span className="w-3 h-3 rounded-full bg-emerald-400" />
                <span className="ml-3 font-mono text-xs text-slate-400">marianalysis-console</span>
              </div>

              <div className="space-y-4 font-mono text-xs">
                <div className="flex items-center gap-3">
                  <span className="text-neon-blue">$</span>
                  <span className="text-slate-600 dark:text-slate-300">loading sample_video.mp4</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-neon-blue">$</span>
                  <span className="text-slate-600 dark:text-slate-300">extracting 48 frames…</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-neon-blue">$</span>
                  <span className="text-slate-600 dark:text-slate-300">faces detected: 2</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-neon-blue">$</span>
                  <span className="text-slate-600 dark:text-slate-300">temporal inconsistency: 0.83</span>
                </div>

                <div className="rounded-xl border border-rose-400/40 bg-rose-400/10 p-3">
                  <p className="text-rose-400 font-bold text-sm mb-1 flex items-center gap-2">
                    <LockClosedIcon className="w-4 h-4" /> VERDICT: FAKE
                  </p>
                  <div className="h-2 rounded-full bg-rose-400/20 overflow-hidden">
                    <div className="h-full w-[87%] bg-gradient-to-r from-rose-500 to-red-400 glow-progress" />
                  </div>
                  <p className="mt-1 text-slate-500 dark:text-slate-400">AI probability 87.4% · risk HIGH</p>
                </div>

                <div className="rounded-xl border border-emerald-400/40 bg-emerald-400/10 p-3">
                  <p className="text-emerald-400 font-bold text-sm mb-1">VERDICT: AUTHENTIC</p>
                  <div className="h-2 rounded-full bg-emerald-400/20 overflow-hidden">
                    <div className="h-full w-[96%] bg-gradient-to-r from-emerald-500 to-green-400 glow-progress" />
                  </div>
                  <p className="mt-1 text-slate-500 dark:text-slate-400">Confidence 96.2% · risk LOW</p>
                </div>

                <div className="flex items-center gap-3 pt-1">
                  <span className="text-neon-blue">$</span>
                  <span className="text-slate-600 dark:text-slate-300">report.pdf generated ✓</span>
                </div>
              </div>
            </div>

          </motion.div>
        </div>
      </section>

      {/* ---------- STATS ---------- */}
      <section className="relative py-12 border-y border-slate-200 dark:border-white/10">
        <div className="container-app grid grid-cols-2 lg:grid-cols-4 gap-6">
          {stats.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="text-center"
            >
              <p className="text-3xl sm:text-4xl font-extrabold neon-text">{s.value}</p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{s.label}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ---------- FEATURES ---------- */}
      <section id="features" className="relative py-24">
        <div className="container-app">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Everything You Need to <span className="neon-text">Verify Truth</span>
            </h2>
            <p className="text-slate-600 dark:text-slate-300">
              One place to check media across every format — using computer vision,
              signal processing and text analysis together.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                whileHover={{ y: -6 }}
                className="glass rounded-2xl p-6 group relative overflow-hidden"
              >
                <div className="scan-overlay opacity-0 group-hover:opacity-100" />
                <span className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${f.color} text-white mb-4`}>
                  <f.icon className="w-7 h-7" />
                </span>
                <h3 className="font-bold text-lg mb-2">{f.title}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- AI WORKFLOW ---------- */}
      <section className="relative py-24 bg-gradient-to-b from-transparent via-neon-purple/5 to-transparent">
        <div className="container-app">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              The <span className="neon-text">AI Workflow</span>
            </h2>
            <p className="text-slate-600 dark:text-slate-300">
              From upload to report — six steps, no black boxes.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {workflow.map((w, i) => (
              <motion.div
                key={w.title}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="relative glass rounded-2xl p-6"
              >
                <span className="absolute top-4 right-5 font-mono text-3xl font-black text-slate-200 dark:text-white/5">
                  0{i + 1}
                </span>
                <span className="inline-flex p-3 rounded-xl bg-neon-blue/10 text-neon-blue mb-4">
                  <w.icon className="w-6 h-6" />
                </span>
                <h3 className="font-bold mb-1.5">{w.title}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400">{w.desc}</p>
              </motion.div>
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mt-12 text-center"
          >
            <Link to={isAuthenticated ? "/dashboard" : "/register"} className="btn-primary !px-10 !py-4 !text-lg">
              <ShieldCheckIcon className="w-6 h-6" />
              Get Started
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ---------- SECURITY BAND ---------- */}
      <section className="relative py-16 border-t border-slate-200 dark:border-white/10">
        <div className="container-app flex flex-wrap items-center justify-center gap-x-12 gap-y-6 text-center">
          {[
            ["JWT Authentication", LockClosedIcon],
            ["Rate Limiting", ShieldCheckIcon],
            ["XSS & SQLi Protected", LockClosedIcon],
            ["Explainable AI", SparklesIcon],
            ["Forensic Reports", DocumentTextIcon],
          ].map(([label, Icon]) => (
            <div key={label} className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Icon className="w-5 h-5 text-neon-blue" /> {label}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
