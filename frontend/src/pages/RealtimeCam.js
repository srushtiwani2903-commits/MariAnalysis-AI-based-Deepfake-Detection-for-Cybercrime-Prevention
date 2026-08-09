import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  VideoCameraIcon, StopIcon, ShieldExclamationIcon, SparklesIcon,
} from "@heroicons/react/24/outline";
import ConfidenceGauge from "../components/ConfidenceGauge";
import api from "../api/api";

// Real-time webcam deepfake check. Streams frames to the realtime endpoint
// at ~1 frame/sec and shows a live fake-confidence gauge + bounding overlay.
export default function RealtimeCam() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [active, setActive] = useState(false);
  const [result, setResult] = useState(null);
  const [hint, setHint] = useState("Connect your camera and press Start. You should be in a well-lit room.");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActive(false);
    setResult(null);
  };

  const start = async () => {
    setErr("");
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = s;
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play();
      }
      setActive(true);
      setHint("Camera live. Sending a frame to the detector every ~1s.");
    } catch (e) {
      setErr("Camera unavailable. Allow webcam permission and retry, or use the Camera tab on a phone.");
    }
  };

  useEffect(() => {
    if (!active) return;
    let alive = true;
    const tick = async () => {
      if (!alive || busy) return;
      const v = videoRef.current, c = canvasRef.current;
      if (!v || v.readyState < 2) return;
      c.width = v.videoWidth || 640;
      c.height = v.videoHeight || 480;
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
      const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.7));
      if (!alive) return;
      setBusy(true);
      try {
        const form = new FormData();
        form.append("frame", blob, "frame.jpg");
        const { data } = await api.post("/detect/realtime", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        if (alive) setResult(data.result || data);
      } catch {
        if (alive) setErr("Could not reach the detector. Is the backend running?");
      } finally {
        setBusy(false);
      }
    };
    tick();
    const iv = setInterval(tick, 1100);
    return () => { alive = false; clearInterval(iv); };
  }, [active, busy]);

  useEffect(() => () => stop(), []);

  const fake = result?.fake_probability;
  const verdict = fake >= 65 ? "FAKE SUSPECTED" : fake >= 42 ? "AMBIGUOUS" : "LIKELY REAL";

  return (
    <div className="container-app py-10 max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <VideoCameraIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Live Webcam Check</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Point your camera at a screen or video call to see if the feed shows signs of
          deepfake manipulation in real time.
        </p>
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="glass-strong rounded-3xl overflow-hidden">
            <div className="relative bg-black aspect-video">
              <video ref={videoRef} muted playsInline className="w-full h-full object-cover" />
              {/* Live verdict overlay */}
              {active && result && (
                <>
                  <div className="absolute inset-x-0 top-0 p-3 flex justify-between items-start">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold tracking-wider text-white ${
                      verdict === "FAKE SUSPECTED" ? "bg-rose-500" : verdict === "AMBIGUOUS" ? "bg-amber-500" : "bg-emerald-500"
                    }`}>
                      {verdict}
                    </span>
                    <span className="px-3 py-1 rounded-full text-xs font-mono bg-black/50 text-white">
                      {(result?.fake_probability ?? 0).toFixed(0)}% fake
                    </span>
                  </div>
                  {/* Prevent: when the live feed looks fake, warn + block action */}
                  {verdict === "FAKE SUSPECTED" && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-rose-950/70 backdrop-blur-sm text-white p-6 text-center">
                      <ShieldExclamationIcon className="w-12 h-12 text-rose-300" />
                      <p className="font-bold text-lg">Deepfake feed detected — do not trust it</p>
                      <p className="text-sm text-rose-100 max-w-md">
                        Stop the call, hang up, and verify the person through a known trusted channel
                        before sharing any sensitive information.
                      </p>
                    </div>
                  )}
                </>
              )}
              {!active && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-2">
                  <VideoCameraIcon className="w-14 h-14 opacity-40" />
                  <p className="text-sm">Camera off</p>
                </div>
              )}
            </div>
            <div className="p-4 flex items-center justify-between flex-wrap gap-3">
              {!active ? (
                <button onClick={start} className="btn-primary">
                  <SparklesIcon className="w-5 h-5" /> Start Live Detection
                </button>
              ) : (
                <button onClick={stop} className="btn-danger">
                  <StopIcon className="w-5 h-5" /> Stop
                </button>
              )}
              <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                <ShieldExclamationIcon className="w-4 h-4 text-neon-blue" />
                {hint}
              </p>
            </div>
          </div>
          <canvas ref={canvasRef} className="hidden" />
          {err && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="mt-4 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
              {err}
            </motion.div>
          )}
        </div>

        <div className="glass-strong rounded-3xl p-6 flex flex-col items-center gap-6">
          <h2 className="text-lg font-bold self-start">Live Signal</h2>
          <ConfidenceGauge value={result?.fake_probability ?? 0}
            label={result ? "Manipulation likelihood" : "Awaiting first frame"} />
          <div className="w-full space-y-2 text-xs">
            <div className="flex justify-between"><span className="text-slate-500">Detected faces</span>
              <span className="font-mono">{result?.faces_detected ?? result?.face_count ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Signal confidence</span>
              <span className="font-mono">{result?.confidence ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Status</span>
              <span className="font-semibold">{busy ? "analyzing…" : active ? "live" : "idle"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Kaggle reference</span>
              <span className="font-mono">{result?.kaggle_reference_status ?? "ready"}</span></div>
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 text-center">
            Frames are processed in-memory and never stored. Replays or screen-capture feeds
            can trigger elevated fake scores.
          </p>
        </div>
      </div>
    </div>
  );
}
