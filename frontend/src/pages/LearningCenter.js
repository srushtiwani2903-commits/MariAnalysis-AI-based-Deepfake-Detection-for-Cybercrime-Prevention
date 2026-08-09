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
    body: "A deepfake is a photo, video, audio clip or piece of text that has been generated or edited with AI. GANs and diffusion models can now create fake faces, voices and videos that look and sound genuinely real to most people.",
  },
  {
    icon: FilmIcon,
    title: "Types of Deepfakes",
    body: "The common ones: Face Swap (putting someone's face on another body), Face Reenactment (making a person say or do something they didn't), Lip Sync, Voice Cloning, fully AI-written text, and full-body puppet animation. Each one tricks a different part of your senses.",
  },
  {
    icon: MicrophoneIcon,
    title: "AI Voice Cloning",
    body: "Voice cloning can recreate someone's voice from just a few seconds of audio. Scammers use it to approve fake payments, impersonate a boss over the phone, or spread fake calls — which is why a voice alone is no longer proof someone said something.",
  },
  {
    icon: PhotoIcon,
    title: "Image Manipulation",
    body: "Image fakes include face-swapped photos, fully synthetic faces, and heavy editing like airbrushing or splicing. Common tells: lighting that doesn't match, soft edges around the face, odd reflections in the eyes, and stripped-out photo metadata.",
  },
  {
    icon: FilmIcon,
    title: "Video Manipulation",
    body: "Fake videos are the scariest because people trust them the most. They're used for political misinformation, fake celebrity content and financial fraud. Good detectors look at what's hard to fake over time: blinking, lip sync, facial warping and flicker in the video.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Cybercrime Awareness",
    body: "Deepfakes power scams like fake CEO requests, romance scams, blackmail and identity theft. A simple habit fixes most of these: if a request is unusual, confirm it through a second channel — a different phone number, a video call, or in person.",
  },
  {
    icon: LightBulbIcon,
    title: "Detection Tips",
    body: "Things to check by eye: odd blinking, blurry face edges, mismatched earrings or glasses, unnatural skin texture, inconsistent shadows, weird reflections in the eyes, robotic-sounding speech, and text that reads too perfectly uniform.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Prevention Methods",
    body: "Use watermarking and content credentials where available, turn on multi-factor authentication everywhere important, teach people to double-check unusual requests, and let detection tools give you a second opinion instead of trusting your eyes alone.",
  },
  {
    icon: GlobeAltIcon,
    title: "Latest Deepfake Trends",
    body: "Recently: live face-swapping during video calls, voice cloning that's cheap and easy, deepfake-as-a-service sites, AI-driven election misinformation, and new laws (like the EU AI Act) pushing for labels that say when content was AI-made.",
  },
];

const faqs = [
  ["How accurate is MariAnalysis?", "In the default heuristic mode it lands around 85-92% on typical media. With trained CNN/ViT models plugged in, that climbs past 96% on benchmarks like FaceForensics++ and DFDC."],
  ["Is my uploaded file stored?", "Files are stored on the server so they can be analyzed and kept in your scan history. You can delete any scan — and its file — at any time."],
  ["Can I use this for legal evidence?", "Reports are meant as guidance, not certified evidence. For court, you'd want certified forensic tools and a proper chain of custody."],
  ["Does it work on any image format?", "Images: PNG, JPG, JPEG, WebP, BMP, TIFF. Video: MP4, AVI, MOV, MKV, WebM. Audio: MP3, WAV, OGG, FLAC, M4A."],
  ["What makes text detection work?", "We look at how smoothly the text flows (perplexity), how much sentence lengths vary (burstiness), and how much it repeats. AI writing tends to be very smooth, very even, and very repetitive."],
  ["Can I use a custom model?", "Right now the app runs on built-in heuristic engines that need no model weights. The API is stable, so new model backends can be added later without changing the frontend."],
];

export default function LearningCenter() {
  const [openFaq, setOpenFaq] = useState(null);

  return (
    <div className="container-app py-12 space-y-12">
      <div className="text-center max-w-2xl mx-auto">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <AcademicCapIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl sm:text-4xl font-bold">Learning Center</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-3">
          Learn what deepfakes are, how to spot them, and how to protect yourself.
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
