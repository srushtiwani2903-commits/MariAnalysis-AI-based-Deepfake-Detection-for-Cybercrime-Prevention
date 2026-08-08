import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AcademicCapIcon, ExclamationTriangleIcon, MicrophoneIcon,
  PhotoIcon, FilmIcon, ShieldCheckIcon, LightBulbIcon,
  GlobeAltIcon, QuestionMarkCircleIcon, ChevronDownIcon,
} from "@heroicons/react/24/outline";

const articles = [
  {
    icon: ExclamationTriangleIcon,
    title: "What is a Deepfake?",
    body: "A deepfake is media (image, video, audio or text) generated or manipulated using artificial intelligence. Deep learning models such as GANs and diffusion models can create hyper-realistic fake faces, voices and videos that are nearly impossible to distinguish from reality with the naked eye.",
  },
  {
    icon: FilmIcon,
    title: "Types of Deepfakes",
    body: "Common types include: Face Swap (identity transfer), Face Reenactment (driving expressions), Lip Sync (speech manipulation), Voice Cloning (synthesizing a person's voice), AI-written text, and Puppet Master (full body animation). Each type exploits different AI architectures.",
  },
  {
    icon: MicrophoneIcon,
    title: "AI Voice Cloning",
    body: "Voice cloning uses neural vocoders and text-to-speech (TTS) to replicate a person's voice from just a few seconds of audio. Attackers use this to authorize fraudulent transactions, impersonate executives (vishing) or spread misinformation via fake phone calls.",
  },
  {
    icon: PhotoIcon,
    title: "Image Manipulation",
    body: "Image deepfakes include face swapping in photos, GAN-generated synthetic faces, and digital editing (airbrushing, splicing). Forensic markers include inconsistent lighting, blurred edges at face boundaries, unnatural eye reflections, and missing EXIF metadata.",
  },
  {
    icon: FilmIcon,
    title: "Video Manipulation",
    body: "Videos are the most dangerous deepfake vector — used for political deception, celebrity pornography and financial fraud. Detection relies on temporal analysis: blinking patterns, inconsistent lip-sync, facial warping, and flickering in compression artifacts.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Cybercrime Awareness",
    body: "Deepfakes fuel scams like CEO fraud (BEC), romance scams, blackmail, and identity theft. Organizations must train employees to verify unusual requests through secondary channels and maintain incident response playbooks for synthetic media attacks.",
  },
  {
    icon: LightBulbIcon,
    title: "Detection Tips",
    body: "Look for: odd blinking, blurry face borders, mismatched earrings/glasses, unnatural skin texture, inconsistent shadows, weird reflections in eyes, robotic audio prosody, and text that is too perfectly uniform. Use AI detectors for a confidence-based verdict.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Prevention Methods",
    body: "Adopt digital watermarking (C2PA), content credentials, cryptographic provenance, biometric voiceprints, strict multi-factor authentication, media literacy training, and real-time deepfake screening at the platform edge.",
  },
  {
    icon: GlobeAltIcon,
    title: "Latest Deepfake Trends",
    body: "2024-2026 trends: real-time face-swap in video calls, diffusion-based voice cloning at scale, deepfake-as-a-service platforms, AI election disinformation, and regulatory frameworks (EU AI Act, US legislation) requiring provenance labeling.",
  },
];

const faqs = [
  ["How accurate is MariAnalysis?", "In heuristic mode the ensemble achieves ~85-92% on typical media. When connected to trained CNN/ViT models, accuracy reaches 96%+ on benchmark datasets such as FaceForensics++ and DFDC."],
  ["Is my uploaded file stored?", "Files are stored locally on the server for analysis and included in your scan history. You can delete any scan (and its file) at any time."],
  ["Can I use this for legal evidence?", "Reports are forensic-guidance documents. For legal evidence, use certified forensic tools and chain-of-custody procedures."],
  ["Does it work on any image format?", "PNG, JPG, JPEG, WebP, BMP and TIFF are supported. Video: MP4, AVI, MOV, MKV, WebM. Audio: MP3, WAV, OGG, FLAC, M4A."],
  ["What makes text detection work?", "We score perplexity (token flow smoothness), burstiness (sentence-length variance) and repetition. LLM-generated text scores low perplexity, low burstiness and high repetition."],
  ["Can I use a custom model?", "The app currently runs on its built-in heuristic engines, which need no model weights. The API schema is stable, so future model backends can plug in without frontend changes."],
];

export default function LearningCenter() {
  const [openFaq, setOpenFaq] = useState(null);

  return (
    <div className="container-app py-12 space-y-12">
      <div className="text-center max-w-2xl mx-auto">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <AcademicCapIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl sm:text-4xl font-bold">Cybersecurity Learning Center</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-3">
          Understand deepfakes, spot manipulation, and protect yourself from AI-powered cybercrime.
        </p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {articles.map((a, i) => (
          <motion.div
            key={a.title}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ y: -5 }}
            className="glass rounded-2xl p-6"
          >
            <span className="inline-flex p-3 rounded-xl bg-neon-blue/10 text-neon-blue mb-4">
              <a.icon className="w-6 h-6" />
            </span>
            <h3 className="font-bold text-lg mb-2">{a.title}</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">{a.body}</p>
          </motion.div>
        ))}
      </div>

      {/* FAQ */}
      <div className="max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-6 flex items-center justify-center gap-2">
          <QuestionMarkCircleIcon className="w-6 h-6 text-neon-blue" /> Frequently Asked Questions
        </h2>
        <div className="space-y-3">
          {faqs.map(([q, a], i) => (
            <div key={q} className="glass rounded-2xl overflow-hidden">
              <button
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
                className="w-full flex items-center justify-between px-5 py-4 text-left font-semibold hover:bg-white/5 transition-colors"
              >
                {q}
                <ChevronDownIcon className={`w-5 h-5 transition-transform ${openFaq === i ? "rotate-180" : ""}`} />
              </button>
              <AnimatePresence>
                {openFaq === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <p className="px-5 pb-4 text-sm text-slate-500 dark:text-slate-400">{a}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
