import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CodeBracketIcon } from "@heroicons/react/24/outline";
import GlassCard from "../components/GlassCard";
import api from "../api/api";

export default function ApiDocs() {
  const [endpoints, setEndpoints] = useState(null);

  useEffect(() => {
    api.get("/docs").then((res) => setEndpoints(res.data.endpoints)).catch(() => {});
  }, []);

  const base = process.env.REACT_APP_API_URL || "http://localhost:5000/api";

  return (
    <div className="container-app py-12 max-w-5xl">
      <div className="text-center mb-10">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <CodeBracketIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">API Documentation</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 font-mono text-sm">{base}</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {endpoints &&
          Object.entries(endpoints).map(([group, epList], gi) => (
            <motion.div key={group} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: gi * 0.05 }}>
              <GlassCard hover={false}>
                <h2 className="font-bold mb-4 uppercase tracking-wider text-sm text-neon-blue">{group}</h2>
                <div className="space-y-2">
                  {epList.map((ep) => {
                    const method = ep.split(" ")[0];
                    const path = ep.split(" ").slice(1).join(" ");
                    const color =
                      method === "POST" ? "text-emerald-400 bg-emerald-400/10"
                      : method === "GET" ? "text-neon-blue bg-neon-blue/10"
                      : method === "PUT" ? "text-amber-400 bg-amber-400/10"
                      : method === "DELETE" ? "text-rose-400 bg-rose-400/10" : "text-slate-400 bg-slate-400/10";
                    return (
                      <div key={ep} className="flex items-center gap-3 rounded-xl bg-white/40 dark:bg-white/5 px-4 py-2.5">
                        <span className={`w-14 text-center text-xs font-bold rounded-md px-2 py-1 ${color}`}>{method}</span>
                        <code className="text-xs text-slate-600 dark:text-slate-300 break-all">{path}</code>
                      </div>
                    );
                  })}
                </div>
              </GlassCard>
            </motion.div>
          ))}
      </div>

      <GlassCard hover={false} className="mt-8">
        <h2 className="font-bold mb-3">Authentication</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
          All endpoints except register/login require a JWT Bearer token:
        </p>
        <pre className="mt-3 rounded-xl bg-navy-950 p-4 text-xs text-neon-blue overflow-x-auto font-mono">
{`# 1. Get a token
POST ${base}/auth/login
{ "identifier": "user@example.com", "password": "YourPass1!" }

# 2. Use it
GET ${base}/history
Authorization: Bearer <token>`}
        </pre>
      </GlassCard>
    </div>
  );
}
