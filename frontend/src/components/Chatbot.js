import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { XMarkIcon, PaperAirplaneIcon } from "@heroicons/react/24/outline";
import api from "../api/api";
import ChatbotAvatar from "./ChatbotAvatar";

const QUICK = ["What is a deepfake?", "How does the detection work?", "Can it scan videos?", "How to report fraud?"];

const ALERT_WORDS = ["scam", "fraud", "hack", "stolen", "danger", "risk", "phish", "blackmail", "crime", "complaint", "report", "fake", "threat", "unsafe", "virus"];
const HAPPY_WORDS = ["thanks", "thank", "great", "awesome", "nice", "hi", "hello", "hey", "good", "cool"];
const SURPRISED_WORDS = ["really", "wow", "seriously", "amazing", "unbelievable"];

function moodFromQuestion(q) {
  const t = q.toLowerCase();
  if (ALERT_WORDS.some((w) => t.includes(w))) return "alert";
  if (SURPRISED_WORDS.some((w) => t.includes(w))) return "surprised";
  if (HAPPY_WORDS.some((w) => t.includes(w))) return "happy";
  return null;
}

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [mood, setMood] = useState("idle");
  const [messages, setMessages] = useState([
    { role: "ai", text: "Hi! I can help you understand deepfakes, how detection works, or how to report fraud. What do you want to know?" },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const listRef = useRef(null);
  const moodTimer = useRef(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  useEffect(() => () => clearTimeout(moodTimer.current), []);

  const setMoodTemporarily = (m, ms = 4000) => {
    setMood(m);
    clearTimeout(moodTimer.current);
    moodTimer.current = setTimeout(() => setMood("idle"), ms);
  };

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || typing) return;
    const detected = moodFromQuestion(q);
    if (detected) setMood(detected);
    const history = messages.slice(-10).map((m) => ({ role: m.role, text: m.text }));
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setTyping(true);
    try {
      const { data } = await api.post("/chat", { message: q, history });
      setMessages((m) => [...m, { role: "ai", text: data.reply || "Sorry, I couldn't parse that." }]);
      setMoodTemporarily(detected || (data.intent === "gemini" ? "happy" : "thinking"));
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "I'm having trouble connecting. Please try again." }]);
      setMoodTemporarily("alert");
    } finally {
      setTyping(false);
    }
  };

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className="fixed bottom-24 right-5 z-50 w-[22rem] max-w-[calc(100vw-2.5rem)] rounded-2xl glass-strong shadow-2xl overflow-hidden"
          >
            <div className="accent-g-moss bg-gradient-to-r from-neon-blue to-neon-purple px-4 py-3 flex items-center justify-between text-white">
              <div className="flex items-center gap-2">
                <ChatbotAvatar mood={typing ? "thinking" : mood} size={26} />
                <span className="font-bold text-sm">DeepGuard Assistant</span>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Close chat">
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>
            <div ref={listRef} className="h-80 overflow-y-auto p-3 space-y-3 bg-slate-50 dark:bg-slate-900/80">
              {messages.map((m, i) => {
                const isAI = m.role === "ai";
                const showAvatar = isAI && messages[i - 1]?.role !== "ai";
                return (
                  <div key={i} className={`flex ${isAI ? "justify-start" : "justify-end"}`}>
                    {isAI && (
                      <div className="w-7 shrink-0 self-start pt-0.5 flex justify-center">
                        {showAvatar && (
                          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-neon-blue/30 to-neon-purple/30 ring-1 ring-neon-purple/40 overflow-hidden flex items-end justify-center">
                            <ChatbotAvatar size={26} />
                          </div>
                        )}
                      </div>
                    )}
                    <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                      !isAI
                        ? "accent-g-moss bg-gradient-to-br from-neon-blue to-neon-purple text-white rounded-br-sm"
                        : "glass rounded-bl-sm"
                    }`}>
                      {m.text}
                    </div>
                  </div>
                );
              })}
              {typing && (
                <div className="flex justify-start">
                  <div className="w-7 shrink-0 self-start pt-0.5 flex justify-center">
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-neon-blue/30 to-neon-purple/30 ring-1 ring-neon-purple/40 overflow-hidden flex items-end justify-center">
                      <ChatbotAvatar mood="thinking" size={26} />
                    </div>
                  </div>
                  <div className="glass rounded-2xl px-3 py-2 text-sm text-slate-400 animate-pulse">Thinking…</div>
                </div>
              )}
            </div>
            <div className="p-2 border-t border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900">
              <div className="flex gap-2 mb-2 flex-wrap">
                {QUICK.map((q) => (
                  <button key={q} onClick={() => send(q)}
                    className="text-[11px] px-2 py-1 rounded-full border border-neon-blue/40 text-neon-blue hover:bg-neon-blue/10">
                    {q}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder="Ask anything…"
                  className="input flex-1"
                />
                <button onClick={() => send()} disabled={typing || !input.trim()}
                  className="btn-primary !px-3 !py-2" aria-label="Send">
                  <PaperAirplaneIcon className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.94 }}
        onClick={() => setOpen((o) => !o)}
        aria-label="Toggle assistant"
        className="accent-g-moss fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-neon-blue to-neon-purple text-white shadow-xl shadow-neon-purple/30 flex items-center justify-center"
      >
        {open ? <XMarkIcon className="w-6 h-6" /> : <ChatbotAvatar mood={mood} size={46} />}
      </motion.button>
    </>
  );
}
