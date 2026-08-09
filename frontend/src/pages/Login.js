import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { EnvelopeIcon, LockClosedIcon, ExclamationTriangleIcon, ShieldExclamationIcon } from "@heroicons/react/24/outline";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ identifier: "", password: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(() => sessionStorage.getItem("deepguard-401-message") || "");
  const [loading, setLoading] = useState(false);

  if (notice) {
    sessionStorage.removeItem("deepguard-401-message");
  }

  const doLogin = async () => {
    setError("");
    setLoading(true);
    try {
      const data = await login(form.identifier, form.password);
      navigate(data.user?.is_admin ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err.response?.data?.message || err.message);
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    doLogin();
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
            <ShieldExclamationIcon className="w-8 h-8" />
          </span>
          <h1 className="text-2xl font-bold">Welcome Back</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Sign in to continue scanning</p>
        </div>

        {notice && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 text-amber-300 text-sm bg-amber-400/10 border border-amber-400/40 rounded-xl px-4 py-3 mb-5"
          >
            <ShieldExclamationIcon className="w-5 h-5 shrink-0" /> {notice}
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3 mb-5"
          >
            <ExclamationTriangleIcon className="w-5 h-5 shrink-0" /> {error}
          </motion.div>
        )}

        <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium mb-1.5">Email, Username or Phone</label>
            <div className="relative">
              <EnvelopeIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                required
                value={form.identifier}
                onChange={(e) => setForm({ ...form, identifier: e.target.value })}
                className="input !pl-11"
                placeholder="you@example.com / username / +91 98765 43210"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-sm font-medium">Password</label>
              <Link to="/forgot-password" className="text-xs text-neon-blue hover:underline">Forgot password?</Link>
            </div>
            <div className="relative">
              <LockClosedIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="password"
                required
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="input !pl-11"
                placeholder="••••••••"
              />
            </div>
          </div>

          <button type="submit" disabled={loading} className="btn-primary w-full justify-center !py-3">
            {loading ? "Authenticating…" : "Sign In"}
          </button>
        </form>

        <p className="text-center text-sm mt-6 text-slate-500 dark:text-slate-400">
          Don't have an account?{" "}
          <Link to="/register" className="text-neon-blue font-semibold hover:underline">Create one</Link>
        </p>
      </motion.div>
    </div>
  );
}
