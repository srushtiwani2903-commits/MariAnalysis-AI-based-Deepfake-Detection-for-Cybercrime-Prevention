import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Doughnut, Line } from "react-chartjs-2";
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
  EnvelopeIcon,
  ShareIcon,
  FingerPrintIcon,
  BuildingOffice2Icon,
  ExclamationTriangleIcon,
  ComputerDesktopIcon,
} from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import StatCard from "../components/StatCard";
import ResultBadge from "../components/ResultBadge";
import api from "../api/api";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { humanSize, timeAgo, formatDate } from "../utils/format";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Legend, Filler);

const detectors = [
  { to: "/detect/image", icon: PhotoIcon, title: "Image Detection", desc: "PNG, JPG, GIF, WebP, AVIF, HEIC, RAW, PSD + more", color: "accent-imgscan-dark from-neon-blue to-neon-cyan" },
  { to: "/detect/video", icon: FilmIcon, title: "Video Detection", desc: "MP4, AVI, MOV, MKV, WebM, 3GP, MPEG, FLV, WMV", color: "from-neon-purple to-fuchsia-500" },
  { to: "/detect/audio", icon: MusicalNoteIcon, title: "Audio Detection", desc: "MP3, WAV, OGG, FLAC, M4A, AAC, OPUS, WMA, AIFF", color: "from-pink-500 to-rose-400" },
  { to: "/detect/text", icon: DocumentTextIcon, title: "Text Detection", desc: "TXT, MD, CSV, JSON, XML, HTML, PY, JS, SQL + more", color: "from-amber-400 to-orange-500" },
];

const tools = [
  { to: "/detect/live-call", icon: ComputerDesktopIcon, title: "Live Call Check", desc: "Zoom / Meet / WhatsApp call guard", color: "from-teal-400 to-cyan-500" },
  { to: "/detect/email", icon: EnvelopeIcon, title: "Email Scanner", desc: "Phishing & AI-written mail", color: "from-pink-500 to-rose-400" },
  { to: "/detect/social", icon: ShareIcon, title: "Post / URL Scan", desc: "Paste a link — Real vs Fake", color: "from-violet-500 to-neon-purple" },
  { to: "/evidence", icon: FingerPrintIcon, title: "Report Fraud", desc: "Evidence + case ID", color: "from-amber-400 to-orange-500" },
  { to: "/org-dashboard", icon: BuildingOffice2Icon, title: "Org Dashboard", desc: "Team threat overview", color: "from-emerald-400 to-teal-500" },
];

export default function Dashboard() {
  const { user } = useAuth();
  const { dark } = useTheme();
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [byType, setByType] = useState({ image: 0, video: 0, audio: 0, text: 0 });
  const [fakeReal, setFakeReal] = useState({ fake: 0, authentic: 0, inconclusive: 0 });

  useEffect(() => {
    Promise.all([
      api.get("/history/stats"),
      api.get("/history?limit=5"),
      api.get("/analytics/by-type"),
      api.get("/analytics/fake-vs-real"),
    ])
      .then(([s, h, bt, fr]) => {
        setStats(s.data);
        setRecent(h.data.items);
        setByType(bt.data);
        setFakeReal(fr.data);
        setLoadError("");
      })
      .catch((err) => {
        if (err.response?.status === 401) {
          setLoadError("Session expired. Please log in again.");
        } else {
          setLoadError("Could not load dashboard data. Please try again.");
        }
      });
  }, []);

  return (
    <div className="container-app py-10 space-y-8">
      {/* Welcome banner */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-strong p-8 relative overflow-hidden"
      >

        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-sm text-neon-blue font-medium">My Dashboard</p>
            <h1 className="text-2xl sm:text-3xl font-bold mt-1">
              Welcome back, <span className="neon-text">{user?.username}</span>
            </h1>
            <p className="text-slate-500 dark:text-slate-400 mt-2">
              See your recent scans, check how often fakes show up, and start a new one.
            </p>
          </div>
          <div className="flex gap-3">
            <Link to="/detect" className="btn-primary accent-g-emerald">
              <DocumentMagnifyingGlassIcon className="w-5 h-5" /> New Scan
            </Link>
          </div>
        </div>
      </motion.div>

      {loadError && (
        <div className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
          <ExclamationTriangleIcon className="w-5 h-5 shrink-0" /> {loadError}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard icon={DocumentMagnifyingGlassIcon} label="Total Scans" value={stats?.total_scans ?? "—"} color="accent-g-lime accent-total-red" />
        <StatCard icon={ShieldExclamationIcon} label="Fake Detected" value={stats?.fake_detected ?? "—"} color="from-rose-500 to-red-500" delay={0.1} />
        <StatCard icon={ShieldCheckIcon} label="Real Detected" value={stats?.real_detected ?? "—"} color="from-emerald-500 to-green-500" delay={0.2} />
        <StatCard icon={ChartBarIcon} label="Detection Accuracy" value={stats?.accuracy ?? "—"} suffix="%" color="from-neon-purple to-fuchsia-500" delay={0.3} />
      </div>

      {/* Scans by Type - Visual Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <GlassCard className="h-full">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <ChartBarIcon className="w-5 h-5 text-neon-blue" /> Total Scans by Type
            </h2>
          </div>
          <div className="h-72">
            <Bar
              data={{
                labels: ["Image", "Video", "Audio", "Text"],
                datasets: [
                  {
                    label: "Scans",
                    data: [byType.image, byType.video, byType.audio, byType.text],
                    backgroundColor: [
                      "rgba(239, 68, 68, 0.95)",
                      "rgba(59, 130, 246, 0.95)",
                      "rgba(168, 85, 247, 0.95)",
                      "rgba(249, 115, 22, 0.95)",
                    ],
                    borderColor: [
                      "#ff1e1e",
                      "#1e90ff",
                      "#9d4edd",
                      "#ff5c1d",
                    ],
                    borderWidth: 3,
                  },
                ],
              }}
              options={{
                onClick: (e, elements) => {
                  if (elements.length > 0) {
                    const index = elements[0].index;
                    const types = ["image", "video", "audio", "text"];
                    window.location.href = `/history?type=${types[index]}`;
                  }
                },
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: dark ? "#0a0e27" : "#fff",
                    titleColor: dark ? "#e2e8f0" : "#0f172a",
                    bodyColor: dark ? "#94a3b8" : "#475569",
                    borderColor: dark ? "#22d3ee" : "#15803d",
                    borderWidth: 1,
                  },
                },
                scales: {
                  x: {
                    ticks: { color: dark ? "#94a3b8" : "#64748b" },
                    grid: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)" },
                  },
                  y: {
                    ticks: { color: dark ? "#94a3b8" : "#64748b", beginAtZero: true, precision: 0 },
                    grid: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)" },
                  },
                },
              }}
            />
          </div>
        </GlassCard>

        <GlassCard className="h-full">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <ChartBarIcon className="w-5 h-5 text-neon-blue" /> Fake vs Real Trend
            </h2>
          </div>
          <div className="h-72">
            <Bar
              data={{
                labels: ["Fake", "Real", "Inconclusive"],
                datasets: [
                  {
                    label: "Count",
                    data: [fakeReal.fake, fakeReal.authentic, fakeReal.inconclusive],
                    backgroundColor: [
                      "rgba(239, 68, 68, 0.98)",
                      "rgba(16, 185, 129, 0.98)",
                      "rgba(249, 115, 22, 0.98)",
                    ],
                    borderColor: ["#ff1744", "#1de9b6", "#ff6d00"],
                    borderWidth: 3,
                  },
                ],
              }}
              options={{
                onClick: (e, elements) => {
                  if (elements.length > 0) {
                    window.location.href = `/history`;
                  }
                },
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: dark ? "#0a0e27" : "#fff",
                    titleColor: dark ? "#e2e8f0" : "#0f172a",
                    bodyColor: dark ? "#94a3b8" : "#475569",
                    borderColor: dark ? "#22d3ee" : "#15803d",
                    borderWidth: 1,
                  },
                },
                scales: {
                  x: {
                    ticks: { color: dark ? "#94a3b8" : "#64748b" },
                    grid: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)" },
                  },
                  y: {
                    ticks: { color: dark ? "#94a3b8" : "#64748b", beginAtZero: true, precision: 0 },
                    grid: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)" },
                  },
                },
              }}
            />
          </div>
        </GlassCard>

        <GlassCard className="h-full">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <ChartBarIcon className="w-5 h-5 text-neon-blue" /> Detection Accuracy %
            </h2>
          </div>
          <div className="h-72">
            <Line
              data={{
                labels: ["Total", "Fake", "Real"],
                datasets: [
                  {
                    label: "Accuracy",
                    data: [
                      stats?.accuracy || 0,
                      fakeReal.fake > 0 ? ((fakeReal.fake / (stats?.total_scans || 1)) * 100).toFixed(1) : 0,
                      fakeReal.authentic > 0 ? ((fakeReal.authentic / (stats?.total_scans || 1)) * 100).toFixed(1) : 0,
                    ],
                    borderColor: "#9d4edd",
                    backgroundColor: "rgba(157, 78, 221, 0.4)",
                    fill: true,
                    tension: 0.5,
                    pointBackgroundColor: "#ff5c1d",
                    pointBorderColor: "#0f172a",
                    pointBorderWidth: 3,
                    pointRadius: 6,
                    borderWidth: 3,
                  },
                ],
              }}
              options={{
                onClick: () => {
                  window.location.href = `/analytics`;
                },
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: dark ? "#0a0e27" : "#fff",
                    titleColor: dark ? "#e2e8f0" : "#0f172a",
                    bodyColor: dark ? "#94a3b8" : "#475569",
                    borderColor: dark ? "#22d3ee" : "#15803d",
                    borderWidth: 1,
                  },
                },
                scales: {
                  x: {
                    ticks: { color: dark ? "#94a3b8" : "#64748b" },
                    grid: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)" },
                  },
                  y: {
                    ticks: { color: dark ? "#94a3b8" : "#64748b", beginAtZero: true, max: 100 },
                    grid: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)" },
                  },
                },
              }}
            />
          </div>
        </GlassCard>
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

      {/* Advanced tools */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {tools.map((d, i) => (
          <motion.div
            key={d.to}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.06 }}
          >
            <Link to={d.to}>
              <GlassCard hover className="h-full !p-4">
                <span className={`inline-flex p-2.5 rounded-xl bg-gradient-to-br ${d.color} text-white mb-3`}>
                  <d.icon className="w-5 h-5" />
                </span>
                <h3 className="font-bold text-sm">{d.title}</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{d.desc}</p>
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
            <Link to="/detect" className="btn-primary">Start First Scan</Link>
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
                      {s.scan_type} · {humanSize(s.file_size)} · {formatDate(s.created_at)} ({timeAgo(s.created_at)})
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
