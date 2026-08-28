import { useEffect, useState } from "react";
import {
  Chart as ChartJS, ArcElement, BarElement, CategoryScale, LinearScale,
  LineElement, PointElement, Tooltip, Legend, Filler,
} from "chart.js";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import { ChartBarIcon } from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import Leaderboard from "../components/Leaderboard";
import api from "../api/api";
import { useTheme } from "../context/ThemeContext";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Legend, Filler);

const NEON = ["#22d3ee", "#7c3aed", "#e879f9", "#f59e0b", "#10b981", "#f43f5e"];
const gridColor = (dark) => (dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.08)");
const tickColor = (dark) => (dark ? "#94a3b8" : "#64748b");
// Accent follows the theme: neon blue in dark mode, cyber dark-green in light mode
const ACCENT = (dark) => (dark ? "#22d3ee" : "#15803d");

export default function Analytics() {
  const { dark } = useTheme();
  const [overview, setOverview] = useState(null);
  const [daily, setDaily] = useState([]);
  const [weekly, setWeekly] = useState([]);
  const [fakeReal, setFakeReal] = useState({ fake: 0, authentic: 0, inconclusive: 0 });
  const [byType, setByType] = useState({ image: 0, video: 0, audio: 0, text: 0 });
  const [accuracyTrend, setAccuracyTrend] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get("/analytics/overview"),
      api.get("/analytics/daily?days=7"),
      api.get("/analytics/weekly?weeks=6"),
      api.get("/analytics/fake-vs-real"),
      api.get("/analytics/by-type"),
      api.get("/analytics/accuracy-trend"),
      api.get("/analytics/deepfake-types"),
    ])
      .then(([o, d, w, fr, bt, at, df]) => {
        setOverview(o.data);
        setDaily(d.data.series);
        setWeekly(w.data.series);
        setFakeReal(fr.data);
        setByType(bt.data);
        setAccuracyTrend(at.data.series);
        setLeaderboard(df.data.leaderboard || []);
      })
      .catch(() => {});
  }, []);

  const g = (c) => (dark ? c : c);

  const chartOptions = (extra = {}) => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: tickColor(dark), font: { size: 11 } } },
      tooltip: { backgroundColor: dark ? "#0a0e27" : "#fff", titleColor: tickColor(dark), bodyColor: tickColor(dark), borderColor: ACCENT(dark), borderWidth: 1 },
    },
    scales: {
      x: { ticks: { color: tickColor(dark) }, grid: { color: gridColor(dark) } },
      y: { ticks: { color: tickColor(dark) }, grid: { color: gridColor(dark) } },
    },
    ...extra,
  });

  return (
    <div className="container-app py-10 space-y-8">
      <div className="flex items-center gap-3">
        <span className="p-2.5 rounded-xl bg-neon-blue/10 text-neon-blue"><ChartBarIcon className="w-6 h-6" /></span>
        <div>
          <h1 className="text-2xl font-bold">Analytics Dashboard</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Your detection performance at a glance</p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          ["Total Scans", overview?.total_scans ?? "—", "accent-g-teal accent-total-red"],
          ["Fake Detected", overview?.fake ?? "—", "from-rose-500 to-red-500"],
          ["Authentic", overview?.authentic ?? "—", "from-emerald-500 to-green-500"],
          ["Accuracy", `${overview?.accuracy ?? "—"}%`, "from-neon-purple to-fuchsia-500"],
        ].map(([label, value, color]) => (
          <div key={label} className="glass rounded-2xl p-5 text-center">
            <div className={`w-10 h-10 mx-auto mb-2 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center text-white text-sm font-bold`}>
              {label === "Total Scans" ? "Σ" : label === "Fake Detected" ? "✕" : label === "Authentic" ? "✓" : "A"}
            </div>
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Charts grid */}
      <div className="grid lg:grid-cols-2 gap-6">
        <GlassCard>
          <h3 className="font-bold mb-4">Daily Scans (7 days)</h3>
          <div className="h-72">
            <Bar
              data={{
                labels: daily.map((d) => d.date.slice(5)),
                datasets: [{ label: "Scans", data: daily.map((d) => d.scans), backgroundColor: ACCENT(dark), borderRadius: 0 }],
              }}
              options={chartOptions()}
            />
          </div>
        </GlassCard>

        <GlassCard>
          <h3 className="font-bold mb-4">Weekly Scans</h3>
          <div className="h-72">
            <Line
              data={{
                labels: weekly.map((d) => d.week),
                datasets: [{ label: "Scans", data: weekly.map((d) => d.scans), borderColor: g("#7c3aed"), backgroundColor: g("rgba(124,58,237,0.15)"), fill: true, tension: 0, pointBackgroundColor: ACCENT(dark) }],
              }}
              options={chartOptions()}
            />
          </div>
        </GlassCard>

        <GlassCard>
          <h3 className="font-bold mb-4">Fake vs Real</h3>
          <div className="h-72">
            <Doughnut
              data={{
                labels: ["Fake", "Authentic", "Inconclusive"],
                datasets: [{ data: [fakeReal.fake, fakeReal.authentic, fakeReal.inconclusive], backgroundColor: [ACCENT(dark), ...NEON.slice(1, 3)], borderColor: dark ? "#14181f" : "#fff", borderWidth: 3 }],
              }}
              options={chartOptions({ cutout: "65%" })}
            />
          </div>
        </GlassCard>

        <GlassCard>
          <h3 className="font-bold mb-4">Scans by Media Type</h3>
          <div className="h-72">
            <Bar
              data={{
                labels: ["Image", "Video", "Audio", "Text"],
                datasets: [{ label: "Scans", data: [byType.image, byType.video, byType.audio, byType.text], backgroundColor: [ACCENT(dark), g("#7c3aed"), g("#e879f9"), g("#f59e0b")], borderRadius: 0 }],
              }}
              options={chartOptions()}
            />
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-2">
          <h3 className="font-bold mb-4">Detection Confidence Trend</h3>
          <div className="h-72">
            <Line
              data={{
                labels: accuracyTrend.map((d) => `#${d.scan_index}`),
                datasets: [{ label: "Avg confidence", data: accuracyTrend.map((d) => d.confidence), borderColor: g("#10b981"), backgroundColor: g("rgba(16,185,129,0.12)"), fill: true, tension: 0, pointBackgroundColor: ACCENT(dark) }],
              }}
              options={chartOptions()}
            />
          </div>
        </GlassCard>

        {leaderboard.length > 0 && (
          <GlassCard className="lg:col-span-2">
            <h3 className="font-bold mb-4">Deepfake Types Leaderboard</h3>
            <Leaderboard entries={leaderboard.map((l) => ({ type: `${l.icon} ${l.type}`, count: l.percent }))} />
          </GlassCard>
        )}
      </div>
    </div>
  );
}
