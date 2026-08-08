import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  KeyIcon, LockClosedIcon, ExclamationTriangleIcon, CheckCircleIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";
import api from "../api/api";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";
  const email = params.get("email") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess(false);
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { email, token, new_password: password });
      setSuccess(true);
      setTimeout(() => navigate("/login"), 2200);
    } catch (err) {
      setError(err.response?.data?.message || err.message);
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
          <h1 className="text-2xl font-bold">Choose a New Password</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 break-all">
            Reset for <span className="text-neon-blue">{email}</span>
          </p>
        </div>

        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3 mb-5">
            <ExclamationTriangleIcon className="w-5 h-5 shrink-0" /> {error}
          </motion.div>
        )}
        {success && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-emerald-400 text-sm bg-emerald-400/10 border border-emerald-400/30 rounded-xl px-4 py-3 mb-5">
            <CheckCircleIcon className="w-5 h-5 shrink-0" /> Password updated. Redirecting to login…
          </motion.div>
        )}

        {!token || !email ? (
          <div className="text-center">
            <p className="text-slate-400 text-sm mb-6">This reset link is invalid. Please request a new one.</p>
            <Link to="/forgot-password" className="btn-primary w-full justify-center">Request New Link</Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium mb-1.5">New Password</label>
              <div className="relative">
                <LockClosedIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="password" required value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input !pl-11" placeholder="8+ chars, A-Z, a-z, 0-9, special"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Confirm Password</label>
              <div className="relative">
                <ShieldCheckIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="password" required value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="input !pl-11" placeholder="Re-enter the new password"
                />
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center !py-3">
              {loading ? "Saving…" : "Update Password"}
            </button>
          </form>
        )}

        <p className="text-center text-sm mt-6">
          <Link to="/login" className="text-neon-blue font-semibold hover:underline">← Back to login</Link>
        </p>
      </motion.div>
    </div>
  );
}
