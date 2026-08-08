import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  UsersIcon, DocumentMagnifyingGlassIcon, ShieldCheckIcon,
  ShieldExclamationIcon, ClipboardDocumentListIcon, ServerIcon,
  Cog6ToothIcon, TrashIcon, UserMinusIcon, ArrowPathIcon,
} from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import api from "../api/api";
import { timeAgo } from "../utils/format";

const tabs = [
  { id: "stats", label: "System Stats", icon: ServerIcon },
  { id: "users", label: "User Management", icon: UsersIcon },
  { id: "logs", label: "Detection Logs", icon: ClipboardDocumentListIcon },
  { id: "model", label: "Model Performance", icon: Cog6ToothIcon },
];

export default function Admin() {
  const [tab, setTab] = useState("stats");
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [model, setModel] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get("/admin/stats"),
      api.get("/admin/users"),
      api.get("/admin/logs?limit=15"),
      api.get("/admin/model-performance"),
      api.get("/admin/health"),
    ])
      .then(([s, u, l, m, h]) => {
        setStats(s.data); setUsers(u.data.items); setLogs(l.data.items);
        setModel(m.data); setHealth(h.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const deleteUser = async (id) => {
    if (!window.confirm("Delete this user and all their scans?")) return;
    await api.delete(`/admin/users/${id}`);
    load();
  };

  const toggleAdmin = async (id) => {
    await api.post(`/admin/users/${id}/toggle-admin`);
    load();
  };

  const statCards = [
    ["Total Users", stats?.total_users, "from-neon-blue to-cyan-400", UsersIcon],
    ["Total Scans", stats?.total_scans, "from-neon-purple to-fuchsia-500", DocumentMagnifyingGlassIcon],
    ["Fake Detected", stats?.fake_detected, "from-rose-500 to-red-500", ShieldExclamationIcon],
    ["Real Detected", stats?.real_detected, "from-emerald-500 to-green-500", ShieldCheckIcon],
    ["Scans Today", stats?.scans_today, "from-amber-400 to-orange-500", ServerIcon],
    ["Reports", stats?.total_reports, "from-pink-500 to-rose-400", ClipboardDocumentListIcon],
    ["Accuracy", `${stats?.accuracy ?? "—"}%`, "from-sky-400 to-indigo-500", Cog6ToothIcon],
  ];

  return (
    <div className="container-app py-10 space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Cog6ToothIcon className="w-7 h-7 text-neon-blue" /> Admin Panel
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">System-wide monitoring & management</p>
        </div>
        <button onClick={load} className="btn-secondary"><ArrowPathIcon className="w-4 h-4" /> Refresh</button>
      </div>

      {/* Health banner */}
      {health && (
        <div className={`rounded-2xl px-5 py-3 border text-sm flex flex-wrap gap-4 ${
          health.status === "healthy"
            ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
            : "border-amber-400/30 bg-amber-400/10 text-amber-300"}`}>
          <span className="font-bold">SYSTEM {health.status.toUpperCase()}</span>
          <span>DB: {health.database}</span>
          <span>Engine: heuristic-ensemble-v1</span>
          <span>Storage free: {(health.storage_free_bytes / 1e9).toFixed(1)} GB</span>
          <span>Uptime: {Math.floor(health.uptime_seconds / 60)} min</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
              tab === t.id ? "bg-gradient-to-r from-neon-blue to-neon-purple text-white shadow-glow" : "glass hover:border-neon-blue/40"}`}
          >
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {/* STATS */}
      {tab === "stats" && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {statCards.map(([label, value, color, Icon], i) => (
            <motion.div key={label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass rounded-2xl p-5">
              <span className={`inline-flex p-2.5 rounded-xl bg-gradient-to-br ${color} text-white mb-3`}><Icon className="w-5 h-5" /></span>
              <p className="text-2xl font-bold">{value ?? "—"}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
            </motion.div>
          ))}
        </div>
      )}

      {/* USERS */}
      {tab === "users" && (
        <GlassCard hover={false}>
          <div className="space-y-3">
            {users.map((u) => (
              <div key={u.id} className="flex flex-wrap items-center gap-4 rounded-xl bg-white/40 dark:bg-white/5 p-4">
                <span className="w-10 h-10 rounded-full bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white font-bold uppercase">
                  {u.username?.[0]}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">
                    {u.username} {u.is_admin && <span className="text-xs text-neon-purple font-bold ml-1">ADMIN</span>}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{u.email} · {u.scan_count} scans · joined {timeAgo(u.created_at)}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => toggleAdmin(u.id)} className="btn-secondary !px-3 !py-1.5 !text-xs">
                    {u.is_admin ? <UserMinusIcon className="w-4 h-4" /> : <ShieldCheckIcon className="w-4 h-4" />}
                    {u.is_admin ? "Revoke admin" : "Make admin"}
                  </button>
                  <button onClick={() => deleteUser(u.id)} className="btn-danger !px-3 !py-1.5 !text-xs">
                    <TrashIcon className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* LOGS */}
      {tab === "logs" && (
        <GlassCard hover={false}>
          <div className="space-y-2 font-mono text-xs">
            {logs.map((l) => (
              <div key={l.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-white/40 dark:bg-white/5 px-4 py-2.5">
                <span className="text-neon-blue">{timeAgo(l.created_at)}</span>
                <span className="font-bold text-neon-purple">{l.action}</span>
                <span className="text-slate-500 dark:text-slate-400 flex-1 truncate">{l.details}</span>
                <span className="text-slate-400">user#{l.user_id || "system"}</span>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* MODEL */}
      {tab === "model" && model && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            ["Engine Mode", model.engine_mode],
            ["Total Predictions", model.total_predictions],
            ["Avg Confidence", `${model.avg_confidence}%`],
          ].map(([l, v]) => (
            <div key={l} className="glass rounded-2xl p-5">
              <p className="text-xs text-slate-500 dark:text-slate-400">{l}</p>
              <p className="text-xl font-bold mt-1 break-all">{v}</p>
            </div>
          ))}
          <div className="glass rounded-2xl p-5 sm:col-span-2 lg:col-span-3">
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">Predictions per model</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(model.models_used).map(([name, count]) => (
                <span key={name} className="glass rounded-full px-4 py-1.5 text-sm">{name} · {count}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      {loading && <p className="text-center text-sm text-slate-400 terminal-cursor">Loading…</p>}
    </div>
  );
}
