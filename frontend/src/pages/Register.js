import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  UserIcon, EnvelopeIcon, LockClosedIcon, ExclamationTriangleIcon,
  ShieldCheckIcon, CheckCircleIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../context/AuthContext";

const passwordRules = [
  { label: "8+ characters", test: (p) => p.length >= 8 },
  { label: "Upper & lower case", test: (p) => /[A-Z]/.test(p) && /[a-z]/.test(p) },
  { label: "At least one number", test: (p) => /\d/.test(p) },
  { label: "One special character", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", full_name: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.password !== form.confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await register({ username: form.username, full_name: form.full_name, email: form.email, password: form.password });
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container-app max-w-md py-16">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-8 relative overflow-hidden"
      >
        <div className="scan-overlay opacity-40" />
        <div className="text-center mb-8">
          <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
            <ShieldCheckIcon className="w-8 h-8" />
          </span>
          <h1 className="text-2xl font-bold">Create Account</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Join DeepGuard AI security platform</p>
        </div>

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3 mb-5"
          >
            <ExclamationTriangleIcon className="w-5 h-5 shrink-0" /> {error}
          </motion.div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Username</label>
              <div className="relative">
                <UserIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text" required value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  className="input !pl-11" placeholder="agent007"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Full Name</label>
              <div className="relative">
                <UserIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text" value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="input !pl-11" placeholder="Jane Doe"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Email</label>
            <div className="relative">
              <EnvelopeIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="email" required value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="input !pl-11" placeholder="you@example.com"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Password</label>
            <div className="relative">
              <LockClosedIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="password" required value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="input !pl-11" placeholder="••••••••"
              />
            </div>
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {passwordRules.map((r) => (
                <span key={r.label} className={`flex items-center gap-1 text-[11px] ${r.test(form.password) ? "text-emerald-400" : "text-slate-400"}`}>
                  {r.test(form.password) ? <CheckCircleIcon className="w-3.5 h-3.5" /> : <span className="w-3.5 h-3.5" />}
                  {r.label}
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Confirm Password</label>
            <div className="relative">
              <LockClosedIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="password" required value={form.confirm}
                onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                className="input !pl-11" placeholder="••••••••"
              />
            </div>
          </div>

          <button type="submit" disabled={loading} className="btn-primary w-full justify-center !py-3">
            {loading ? "Creating account…" : "Create Account"}
          </button>
        </form>

        <p className="text-center text-sm mt-6 text-slate-500 dark:text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="text-neon-blue font-semibold hover:underline">Sign in</Link>
        </p>
      </motion.div>
    </div>
  );
}
