import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  BuildingOffice2Icon, ArrowUpTrayIcon, ExclamationTriangleIcon,
  CheckCircleIcon, ClockIcon, ChartBarIcon, FunnelIcon, ArrowDownTrayIcon,
} from "@heroicons/react/24/outline";
import StatCard from "../components/StatCard";
import api from "../api/api";

// Organisation dashboard: threat overview for teams/enterprises.
export default function OrgDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const { data: d } = await api.get("/analytics/org-dashboard");
        setData(d);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, []);

  const exportCsv = async () => {
    try {
      const { data: blob } = await api.get("/org/export", { params: { format: "csv" }, responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "org-threat-report.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    }
  };

  const riskColor = { low: "bg-emerald-400", medium: "bg-amber-400", high: "bg-orange-500", critical: "bg-rose-500" };
  const risks = data?.risk_levels ?? {};
  const maxRisk = Math.max(...Object.values(risks), 1);

  return (
    <div className="container-app py-10 max-w-6xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        className="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-purple to-fuchsia-500 text-white mb-3 inline-flex">
            <BuildingOffice2Icon className="w-7 h-7" />
          </span>
          <h1 className="text-3xl font-bold">Organisation Threat Dashboard</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            {data ? (data.scope === "global" ? "Global overview (admin)" : "Your organisation's activity") : "Loading…"}
          </p>
        </div>
        <button onClick={exportCsv} className="btn-secondary">
          <ArrowDownTrayIcon className="w-5 h-5" /> Export CSV
        </button>
      </motion.div>

      {error && (
        <div className="mb-6 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
          <ExclamationTriangleIcon className="w-5 h-5" /> {error}
        </div>
      )}

      {!data && !error && <div className="text-center py-16 text-slate-400 animate-pulse">Gathering threat intelligence…</div>}

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard icon={ArrowUpTrayIcon} label="Scans Today" value={data.today_uploads} color="from-neon-blue to-cyan-400" delay={0} />
            <StatCard icon={ExclamationTriangleIcon} label="Deepfakes Detected" value={data.fake_detected} color="from-rose-500 to-pink-500" delay={0.05} />
            <StatCard icon={CheckCircleIcon} label="Authentic" value={data.real_detected} color="from-emerald-400 to-teal-500" delay={0.1} />
            <StatCard icon={ClockIcon} label="Pending Review" value={data.pending_review} color="from-amber-400 to-orange-500" delay={0.15} />
          </div>

          <div className="grid lg:grid-cols-3 gap-6">
            {/* Risk distribution */}
            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              className="glass-strong rounded-3xl p-6">
              <h3 className="font-bold mb-1 flex items-center gap-2"><ChartBarIcon className="w-5 h-5 text-neon-blue" /> Risk Distribution</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">Total scans: {data.total_scans}</p>
              <div className="space-y-3">
                {Object.entries(risks).map(([k, v]) => (
                  <div key={k}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="capitalize">{k}</span>
                      <span className="font-mono">{v}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                      <motion.div initial={{ width: 0 }} animate={{ width: `${(v / maxRisk) * 100}%` }}
                        transition={{ duration: 0.7 }} className={`h-full rounded-full ${riskColor[k] || "bg-slate-400"}`} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-200 dark:border-white/10 grid grid-cols-2 gap-3 text-center">
                <div>
                  <p className="text-2xl font-bold font-mono">{data.avg_trust_score ?? 0}</p>
                  <p className="text-[11px] text-slate-400">Avg trust score</p>
                </div>
                <div>
                  <p className="text-2xl font-bold font-mono">{data.flagged_rate ?? 0}%</p>
                  <p className="text-[11px] text-slate-400">Flagged rate</p>
                </div>
              </div>
            </motion.div>

            {/* Top threat sources */}
            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              transition={{ delay: 0.08 }} className="glass-strong rounded-3xl p-6 lg:col-span-2">
              <h3 className="font-bold mb-4 flex items-center gap-2"><FunnelIcon className="w-5 h-5 text-neon-purple" /> Top Threat Sources</h3>
              {data.top_threat_sources.length === 0 ? (
                <p className="text-sm text-slate-400">No scan data yet.</p>
              ) : (
                <div className="space-y-3">
                  {data.top_threat_sources.map((s, i) => (
                    <div key={s.source} className="flex items-center gap-3">
                      <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-neon-blue to-neon-purple text-white text-xs flex items-center justify-center">
                        {i + 1}
                      </span>
                      <div className="flex-1">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="font-medium">{s.source}</span>
                          <span className="font-mono text-slate-500 dark:text-slate-400">{s.count}</span>
                        </div>
                        <div className="h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                          <motion.div initial={{ width: 0 }} whileInView={{ width: `${(s.count / (data.top_threat_sources[0]?.count || 1)) * 100}%` }}
                            viewport={{ once: true }} transition={{ duration: 0.7, delay: i * 0.06 }}
                            className="h-full rounded-full bg-gradient-to-r from-neon-blue to-neon-purple" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-5 text-[11px] text-slate-500 dark:text-slate-400">
                Threat sources are inferred from media type and detection patterns. Use the
                evidence registry to escalate confirmed cases to authorities.
              </p>
            </motion.div>
          </div>
        </>
      )}
    </div>
  );
}
