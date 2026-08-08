import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  DocumentMagnifyingGlassIcon,
  ShieldExclamationIcon,
  ShieldCheckIcon,
  ChartBarIcon,
  PhotoIcon,
  FilmIcon,
  MusicalNoteIcon,
  DocumentTextIcon,
  ArrowRightIcon,
  ClockIcon,
} from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import StatCard from "../components/StatCard";
import ResultBadge from "../components/ResultBadge";
import api from "../api/api";
import { useAuth } from "../context/AuthContext";
import { humanSize, timeAgo } from "../utils/format";

const detectors = [
  { to: "/detect/image", icon: PhotoIcon, title: "Image Detection", desc: "Photos, faces, screenshots", color: "from-neon-blue to-cyan-400" },
  { to: "/detect/video", icon: FilmIcon, title: "Video Detection", desc: "MP4, AVI, MOV, WebM", color: "from-neon-purple to-fuchsia-500" },
  { to: "/detect/audio", icon: MusicalNoteIcon, title: "Audio Detection", desc: "MP3, WAV, OGG, FLAC", color: "from-pink-500 to-rose-400" },
  { to: "/detect/text", icon: DocumentTextIcon, title: "Text Detection", desc: "AI-written content, phishing", color: "from-amber-400 to-orange-500" },
];

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    Promise.all([api.get("/history/stats"), api.get("/history?limit=5")])
      .then(([s, h]) => {
        setStats(s.data);
        setRecent(h.data.items);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="container-app py-10 space-y-8">
      {/* Welcome banner */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-8 relative overflow-hidden"
      >
        <div className="scan-overlay opacity-30" />
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-sm text-neon-blue font-medium">Security Dashboard</p>
            <h1 className="text-2xl sm:text-3xl font-bold mt-1">
              Welcome back, <span className="neon-text">{user?.username}</span>
            </h1>
            <p className="text-slate-500 dark:text-slate-400 mt-2">
              Monitor your scans, verify media integrity and stay protected against deepfakes.
            </p>
          </div>
          <div className="flex gap-3">
            <Link to="/analytics" className="btn-secondary">Analytics</Link>
            <Link to="/detect/image" className="btn-primary">
              <DocumentMagnifyingGlassIcon className="w-5 h-5" /> New Scan
            </Link>
          </div>
        </div>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard icon={DocumentMagnifyingGlassIcon} label="Total Scans" value={stats?.total_scans ?? "—"} />
        <StatCard icon={ShieldExclamationIcon} label="Fake Detected" value={stats?.fake_detected ?? "—"} color="from-rose-500 to-red-500" delay={0.1} />
        <StatCard icon={ShieldCheckIcon} label="Real Detected" value={stats?.real_detected ?? "—"} color="from-emerald-500 to-green-500" delay={0.2} />
        <StatCard icon={ChartBarIcon} label="Detection Accuracy" value={stats?.accuracy ?? "—"} suffix="%" color="from-neon-purple to-fuchsia-500" delay={0.3} />
      </div>

      {/* Detector quick access */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {detectors.map((d, i) => (
          <motion.div
            key={d.to}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
          >
            <Link to={d.to}>
              <GlassCard className="h-full">
                <span className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${d.color} text-white mb-3`}>
                  <d.icon className="w-6 h-6" />
                </span>
                <h3 className="font-bold">{d.title}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{d.desc}</p>
                <span className="inline-flex items-center gap-1 text-xs text-neon-blue mt-3 font-medium">
                  Start scan <ArrowRightIcon className="w-3.5 h-3.5" />
                </span>
              </GlassCard>
            </Link>
          </motion.div>
        ))}
      </div>

      {/* Recent scans */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <ClockIcon className="w-5 h-5 text-neon-blue" /> Recent Uploads
          </h2>
          <Link to="/history" className="text-sm text-neon-blue hover:underline flex items-center gap-1">
            View all <ArrowRightIcon className="w-4 h-4" />
          </Link>
        </div>

        {recent.length === 0 ? (
          <GlassCard hover={false} className="text-center py-12">
            <p className="text-slate-400 mb-3">No scans yet. Run your first deepfake analysis.</p>
            <Link to="/detect/image" className="btn-primary">Start First Scan</Link>
          </GlassCard>
        ) : (
          <div className="space-y-3">
            {recent.map((s) => (
              <GlassCard key={s.id} hover={false} className="!p-4">
                <div className="flex flex-wrap items-center gap-4">
                  <ResultBadge result={s.result} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{s.filename}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {s.scan_type} · {humanSize(s.file_size)} · {timeAgo(s.created_at)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm font-bold">{Math.round(s.fake_probability)}%</p>
                    <p className="text-xs text-slate-400">AI probability</p>
                  </div>
                  <Link to={`/results/${s.id}`} className="btn-secondary !px-4 !py-1.5 !text-sm">Details</Link>
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
