import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MicrophoneIcon, SpeakerWaveIcon, XMarkIcon } from "@heroicons/react/24/outline";

// Voice assistant: uses the Web Speech API to narrate detection results.
// Click the mic to start/stop reading the page's results aloud.
export default function VoiceAssistant() {
  const [open, setOpen] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  const readResults = () => {
    if (!supported) return;
    const text = document.querySelector("[data-readable]")?.getAttribute("data-readable");
    if (!text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1;
    u.pitch = 1;
    u.onend = () => setSpeaking(false);
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
    setSpeaking(true);
  };

  const stop = () => {
    speechSynthesis?.cancel();
    setSpeaking(false);
  };

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            className="fixed bottom-24 right-5 z-50 glass-strong rounded-2xl p-4 w-72 shadow-glow"
          >
            <div className="flex items-center justify-between mb-3">
              <p className="font-bold text-sm flex items-center gap-2">
                <SpeakerWaveIcon className="w-5 h-5 text-neon-blue" /> Voice Assistant
              </p>
              <button onClick={() => { stop(); setOpen(false); }} className="p-1 hover:text-rose-400">
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
              Reads the current detection results aloud. Works best in Chrome/Edge.
            </p>
            <button
              onClick={speaking ? stop : readResults}
              className="btn-primary w-full justify-center"
            >
              <MicrophoneIcon className="w-4 h-4" />
              {speaking ? "Stop Reading" : "Read Results"}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white shadow-glow flex items-center justify-center hover:scale-110 transition-transform"
        aria-label="Voice assistant"
      >
        <MicrophoneIcon className="w-6 h-6" />
      </button>
    </>
  );
}
