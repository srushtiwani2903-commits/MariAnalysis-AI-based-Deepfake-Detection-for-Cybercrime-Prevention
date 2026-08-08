import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  UserIcon, EnvelopeIcon, LockClosedIcon, ExclamationTriangleIcon,
  CheckCircleIcon, KeyIcon,
} from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import api from "../api/api";
import { useAuth } from "../context/AuthContext";
import { formatDate } from "../utils/format";

export default function Profile() {
  const { user, refreshUser } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [saved, setSaved] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "" });
  const [pwMsg, setPwMsg] = useState("");
  const [pwErr, setPwErr] = useState("");
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/history/stats").then((res) => setStats(res.data)).catch(() => {});
  }, []);

  const saveProfile = async (e) => {
    e.preventDefault();
    setSaved(false);
    await api.put("/auth/profile", { full_name: fullName });
    await refreshUser();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const changePassword = async (e) => {
    e.preventDefault();
    setPwMsg(""); setPwErr("");
    try {
      await api.post("/auth/change-password", { current_password: pw.current, new_password: pw.next });
      setPwMsg("Password updated successfully.");
      setPw({ current: "", next: "" });
    } catch (err) {
      setPwErr(err.message);
    }
  };

  return (
    <div className="container-app py-10 max-w-4xl space-y-8">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="glass-strong rounded-3xl p-8 flex flex-wrap items-center gap-6">
        <span className="w-20 h-20 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white text-3xl font-bold uppercase">
          {user?.username?.[0]}
        </span>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{user?.full_name || user?.username}</h1>
          <p className="text-slate-500 dark:text-slate-400">@{user?.username} · {user?.email}</p>
          <div className="flex flex-wrap gap-2 mt-2">
            {user?.is_admin && <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-neon-purple/15 text-neon-purple">ADMIN</span>}
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-400">VERIFIED</span>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full glass">Joined {formatDate(user?.created_at)}</span>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4 text-center">
          {[
            [stats?.total_scans ?? "—", "Scans"],
            [stats?.fake_detected ?? "—", "Fake"],
            [stats?.real_detected ?? "—", "Real"],
          ].map(([v, l]) => (
            <div key={l}>
              <p className="text-2xl font-bold neon-text">{v}</p>
              <p className="text-xs text-slate-400">{l}</p>
            </div>
          ))}
        </div>
      </motion.div>

      <div className="grid md:grid-cols-2 gap-6">
        <GlassCard>
          <h2 className="font-bold mb-4 flex items-center gap-2"><UserIcon className="w-5 h-5 text-neon-blue" /> Account Details</h2>
          <form onSubmit={saveProfile} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Full Name</label>
              <div className="relative">
                <UserIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input value={fullName} onChange={(e) => setFullName(e.target.value)} className="input !pl-11" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Email (read-only)</label>
              <div className="relative">
                <EnvelopeIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input value={user?.email || ""} disabled className="input !pl-11 opacity-60" />
              </div>
            </div>
            {saved && (
              <p className="flex items-center gap-2 text-emerald-400 text-sm"><CheckCircleIcon className="w-4 h-4" /> Profile updated.</p>
            )}
            <button type="submit" className="btn-primary w-full justify-center">Save Changes</button>
          </form>
        </GlassCard>

        <GlassCard>
          <h2 className="font-bold mb-4 flex items-center gap-2"><LockClosedIcon className="w-5 h-5 text-neon-purple" /> Change Password</h2>
          <form onSubmit={changePassword} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Current Password</label>
              <div className="relative">
                <KeyIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input type="password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} className="input !pl-11" required />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">New Password</label>
              <div className="relative">
                <LockClosedIcon className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input type="password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} className="input !pl-11" required />
              </div>
            </div>
            {pwMsg && <p className="flex items-center gap-2 text-emerald-400 text-sm"><CheckCircleIcon className="w-4 h-4" /> {pwMsg}</p>}
            {pwErr && <p className="flex items-center gap-2 text-rose-400 text-sm"><ExclamationTriangleIcon className="w-4 h-4" /> {pwErr}</p>}
            <button type="submit" className="btn-primary w-full justify-center">Update Password</button>
          </form>
        </GlassCard>
      </div>
    </div>
  );
}
