import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChatBubbleLeftRightIcon, XMarkIcon, PaperAirplaneIcon } from "@heroicons/react/24/outline";
import api from "../api/api";

const QUICK = ["What is a deepfake?", "How does the detection work?", "Can it scan videos?", "How to report fraud?"];

// Floating assistant chat widget.
export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "ai", text: "Hi! I can help you understand deepfakes, how detection works, or how to report fraud. What do you want to know?" },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || typing) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setTyping(true);
    try {
      const { data } = await api.post("/chat", { message: q });
      setMessages((m) => [...m, { role: "ai", text: data.reply || "Sorry, I couldn't parse that." }]);
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "I'm having trouble connecting. Please try again." }]);
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
            <div className="bg-gradient-to-r from-neon-blue to-neon-purple px-4 py-3 flex items-center justify-between text-white">
              <div className="flex items-center gap-2">
                <ChatBubbleLeftRightIcon className="w-5 h-5" />
                <span className="font-bold text-sm">DeepGuard Assistant</span>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Close chat">
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>
            <div ref={listRef} className="h-80 overflow-y-auto p-3 space-y-3 bg-slate-50 dark:bg-slate-900/80">
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                    m.role === "user"
                      ? "bg-gradient-to-br from-neon-blue to-neon-purple text-white rounded-br-sm"
                      : "glass rounded-bl-sm"
                  }`}>
                    {m.text}
                  </div>
                </div>
              ))}
              {typing && (
                <div className="flex justify-start">
                  <div className="glass rounded-2xl px-3 py-2 text-sm text-slate-400 animate-pulse">Thinking…</div>
                </div>
              )}
            </div>
            <div className="p-2 border-t border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900">
              <div className="flex gap-2 mb-2 flex-wrap">
                {QUICK.map((q) => (
                  <button key={q} onClick={() => send(q)}
                    className="text-[11px] px-2 py-1 rounded-full border border-neon-blue/40 text-neon-blue dark:text-cyan-300 hover:bg-neon-blue/10">
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
        className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-neon-blue to-neon-purple text-white shadow-xl shadow-neon-purple/30 flex items-center justify-center"
      >
        {open ? <XMarkIcon className="w-6 h-6" /> : <ChatBubbleLeftRightIcon className="w-6 h-6" />}
      </motion.button>
    </>
  );
}
