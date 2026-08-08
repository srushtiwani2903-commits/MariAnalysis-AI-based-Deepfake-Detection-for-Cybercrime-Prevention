import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { EnvelopeIcon, ExclamationTriangleIcon, PaperAirplaneIcon, KeyIcon } from "@heroicons/react/24/outline";
import api from "../api/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/forgot-password", { email });
      setMessage(data.message || "If that email exists, a reset link was sent.");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container-app max-w-md py-20">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-8 relative overflow-hidden"
      >
        <div className="scan-overlay opacity-40" />
        <div className="text-center mb-8">
          <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
            <KeyIcon className="w-8 h-8" />
          </span>
          <h1 className="text-2xl font-bold">Reset Password</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Enter your email and we'll send a reset link
          </p>
        </div>

        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3 mb-5">
            <ExclamationTriangleIcon className="w-5 h-5 shrink-0" /> {error}
          </motion.div>
        )}
        {message && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-emerald-400 text-sm bg-emerald-400/10 border border-emerald-400/30 rounded-xl px-4 py-3 mb-5">
            <PaperAirplaneIcon className="w-5 h-5 shrink-0" /> {message}
          </motion.div>
        )}

        <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium mb-1.5">Email Address</label>
            <div className="relative">
              <EnvelopeIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="email" required value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input !pl-11" placeholder="you@example.com"
              />
            </div>
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full justify-center !py-3">
            {loading ? "Sending…" : "Send Reset Link"}
          </button>
        </form>

        <p className="text-center text-sm mt-6">
          <Link to="/login" className="text-neon-blue font-semibold hover:underline">← Back to login</Link>
        </p>
      </motion.div>
    </div>
  );
}
