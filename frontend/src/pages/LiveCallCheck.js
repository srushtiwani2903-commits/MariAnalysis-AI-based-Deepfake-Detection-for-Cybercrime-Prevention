import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ComputerDesktopIcon, StopIcon, ShieldExclamationIcon, SparklesIcon,
  ArrowsPointingOutIcon, ArrowPathIcon,
} from "@heroicons/react/24/outline";
import ConfidenceGauge from "../components/ConfidenceGauge";
import api from "../api/api";

// Live call guard: share a Zoom / Meet / WhatsApp call window, drag a box
// around the other person's video, and we send that region to the detector
// every ~1.6s — same engine as the realtime endpoint, fed by screen capture.
const MAX_OUT_W = 960;
const TICK_MS = 1600;
const MAX_FAILS = 3;

export default function LiveCallCheck() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const wrapRef = useRef(null);
  const dragRef = useRef(null);
  const draftRef = useRef(null);
  const regionRef = useRef(null);
  const failsRef = useRef(0);

  const [active, setActive] = useState(false);
  const [ended, setEnded] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [hint, setHint] = useState(
    "Share the call window (Zoom, Meet, WhatsApp...), then drag a box around ONLY the other person's video."
  );
  const [region, setRegion] = useState(null);
  const [draft, setDraft] = useState(null);
  const [paused, setPaused] = useState(false);
  const [hiddenPause, setHiddenPause] = useState(false);

  const setRegionSafe = (r) => { regionRef.current = r; setRegion(r); };
  const setDraftSafe = (d) => { draftRef.current = d; setDraft(d); };

  const teardown = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const stop = () => {
    teardown();
    setActive(false);
    setEnded(false);
    setPaused(false);
    failsRef.current = 0;
    setRegionSafe(null);
    setDraftSafe(null);
  };

  const endShared = () => {
    teardown();
    setActive(false);
    setEnded(true);
    setPaused(false);
    failsRef.current = 0;
    setRegionSafe(null);
    setDraftSafe(null);
    setHint("Sharing stopped. Press Start to share the call window again.");
  };

  const start = async () => {
    setErr("");
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setErr("Screen capture is not supported here. Please use Chrome, Edge or Firefox on desktop.");
      return;
    }
    try {
      const s = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 15, max: 30 } },
        audio: false,
      });
      streamRef.current = s;
      s.getVideoTracks()[0].addEventListener("ended", endShared);
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch(() => {});
      }
      setResult(null);
      setEnded(false);
      setPaused(false);
      setHiddenPause(false);
      failsRef.current = 0;
      setRegionSafe(null);
      setDraftSafe(null);
      setActive(true);
      setHint("Sharing on. Drag on the preview to select the other person's video tile.");
    } catch (e) {
      if (e?.name === "NotAllowedError" || e?.name === "AbortError") {
        setErr("Screen share was cancelled. Press Start again and pick the call window.");
      } else {
        setErr(`Could not start screen capture: ${e?.message || "unknown error"}`);
      }
    }
  };

  const retry = () => {
    failsRef.current = 0;
    setErr("");
    setPaused(false);
  };

  const clearRegion = () => {
    setRegionSafe(null);
    setDraftSafe(null);
  };

  // --- region drag (container-normalized coords) ------------------------- //
  const toNorm = (e) => {
    const el = wrapRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    const x = (e.clientX - r.left) / r.width;
    const y = (e.clientY - r.top) / r.height;
    if (x < 0 || y < 0 || x > 1 || y > 1) return null;
    return { x, y };
  };

  const onPointerDown = (e) => {
    if (!active) return;
    const p = toNorm(e);
    if (!p) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragRef.current = p;
    setDraftSafe({ x: p.x, y: p.y, w: 0, h: 0 });
  };

  const onPointerMove = (e) => {
    if (!dragRef.current) return;
    const p = toNorm(e);
    if (!p) return;
    const s = dragRef.current;
    setDraftSafe({
      x: Math.min(s.x, p.x),
      y: Math.min(s.y, p.y),
      w: Math.abs(p.x - s.x),
      h: Math.abs(p.y - s.y),
    });
  };

  const onPointerUp = () => {
    if (!dragRef.current) return;
    dragRef.current = null;
    const d = draftRef.current;
    setDraftSafe(null);
    if (d && d.w >= 0.04 && d.h >= 0.04) setRegionSafe(d);
  };

  // --- frame loop -------------------------------------------------------- //
  useEffect(() => {
    if (!active || paused) return;
    let alive = true;
    let inFlight = false;
    const tick = async () => {
      if (!alive || inFlight || document.hidden) return;
      const v = videoRef.current, c = canvasRef.current, wrap = wrapRef.current;
      if (!v || !c || v.readyState < 2 || !v.videoWidth) return;
      const rect = wrap.getBoundingClientRect();
      if (!rect.width || !rect.height) return;

      const vw = v.videoWidth, vh = v.videoHeight;
      const sc = Math.min(rect.width / vw, rect.height / vh);
      const offX = (rect.width - vw * sc) / 2;
      const offY = (rect.height - vh * sc) / 2;
      let sx = 0, sy = 0, sw = vw, sh = vh;
      const reg = regionRef.current;
      if (reg) {
        sx = Math.max(0, Math.min(vw - 1, (reg.x * rect.width - offX) / sc));
        sy = Math.max(0, Math.min(vh - 1, (reg.y * rect.height - offY) / sc));
        sw = Math.max(1, Math.min(vw - sx, (reg.w * rect.width) / sc));
        sh = Math.max(1, Math.min(vh - sy, (reg.h * rect.height) / sc));
      }
      const outW = Math.max(1, Math.min(sw, MAX_OUT_W));
      const outH = Math.max(1, Math.round(sh * (outW / sw)));
      const ctx = c.getContext("2d");
      if (!ctx) return;
      c.width = outW;
      c.height = outH;
      ctx.drawImage(v, sx, sy, sw, sh, 0, 0, outW, outH);

      const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.7));
      if (!alive || !blob) return;
      inFlight = true;
      setBusy(true);
      try {
        const form = new FormData();
        form.append("file", new File([blob], "frame.jpg", { type: "image/jpeg" }));
        form.append("source", "call");
        const { data } = await api.post("/detect/realtime", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        if (!alive) return;
        setResult(data.result || data);
        setErr("");
        failsRef.current = 0;
      } catch (e) {
        if (!alive) return;
        const status = e?.response?.status;
        if (status === 401) {
          setErr("Session expired. Please log in again, then restart the check.");
          failsRef.current = MAX_FAILS;
        } else if (status === 429) {
          setErr("Too many frames sent — waiting a moment before retrying.");
          failsRef.current += 1;
        } else {
          setErr("Could not reach the detector. Is the backend running on port 5001?");
          failsRef.current += 1;
        }
        if (failsRef.current >= MAX_FAILS) setPaused(true);
      } finally {
        if (alive) setBusy(false);
        inFlight = false;
      }
    };
    tick();
    const iv = setInterval(tick, TICK_MS);
    return () => { alive = false; clearInterval(iv); };
  }, [active, paused]);

  // Pause while the tab is hidden so frozen frames never become a verdict,
  // auto-resume when the user comes back.
  useEffect(() => {
    const onVis = () => {
      if (!streamRef.current) return;
      if (document.hidden) {
        setHiddenPause(true);
        setPaused(true);
        setErr("Detector window is hidden — frames would freeze. Keep MariAnalysis visible beside the call.");
      } else if (hiddenPause) {
        setHiddenPause(false);
        failsRef.current = 0;
        setErr("");
        setPaused(false);
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [hiddenPause]);

  useEffect(() => () => teardown(), []);

  const fake = result?.fake_probability;
  const verdict = fake >= 65 ? "FAKE SUSPECTED" : fake >= 42 ? "AMBIGUOUS" : "LIKELY REAL";
  const overlayRect = draft || region;

  return (
    <div className="container-app py-10 max-w-5xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-teal-400 to-cyan-500 text-white mb-4">
          <ComputerDesktopIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Live Call Check</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Share your Zoom, Google Meet, WhatsApp or any video-call window and we will analyse the
          other person's feed live for deepfake manipulation — on any platform.
        </p>
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="glass-strong rounded-3xl overflow-hidden">
            <div
              ref={wrapRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              className={`relative bg-black aspect-video ${active ? "cursor-crosshair" : ""}`}
            >
              <video ref={videoRef} muted playsInline className="w-full h-full object-contain" />
              {overlayRect && (
                <div
                  className="absolute border-2 border-neon-blue bg-neon-blue/10 pointer-events-none"
                  style={{
                    left: `${overlayRect.x * 100}%`,
                    top: `${overlayRect.y * 100}%`,
                    width: `${overlayRect.w * 100}%`,
                    height: `${overlayRect.h * 100}%`,
                  }}
                >
                  <span className="absolute -top-6 left-0 text-[10px] font-bold px-2 py-0.5 rounded bg-neon-blue text-white whitespace-nowrap">
                    ANALYSING THIS AREA
                  </span>
                </div>
              )}
              {active && result && (
                <div className="absolute inset-x-0 top-0 p-3 flex justify-between items-start pointer-events-none">
                  <span className={`px-3 py-1 rounded-full text-xs font-bold tracking-wider text-white ${
                    verdict === "FAKE SUSPECTED" ? "bg-rose-500" : verdict === "AMBIGUOUS" ? "bg-amber-500" : "bg-emerald-500"
                  }`}>
                    {verdict}
                  </span>
                  <span className="px-3 py-1 rounded-full text-xs font-mono bg-black/50 text-white">
                    {(result?.fake_probability ?? 0).toFixed(0)}% fake
                  </span>
                </div>
              )}
              {active && result && verdict === "FAKE SUSPECTED" && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-rose-950/70 backdrop-blur-sm text-white p-6 text-center">
                  <ShieldExclamationIcon className="w-12 h-12 text-rose-300" />
                  <p className="font-bold text-lg">Deepfake feed detected — do not trust it</p>
                  <p className="text-sm text-rose-100 max-w-md">
                    Stop the call, hang up, and verify the person through a known trusted channel
                    before sharing any sensitive information.
                  </p>
                </div>
              )}
              {!active && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-2">
                  <ComputerDesktopIcon className="w-14 h-14 opacity-40" />
                  <p className="text-sm">{ended ? "Sharing stopped" : "No call shared yet"}</p>
                </div>
              )}
            </div>
            <div className="p-4 flex items-center justify-between flex-wrap gap-3">
              {!active ? (
                <button onClick={start} className="btn-primary">
                  <SparklesIcon className="w-5 h-5" /> Start Live Call Check
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <button onClick={stop} className="btn-danger">
                    <StopIcon className="w-5 h-5" /> Stop Sharing
                  </button>
                  {region && (
                    <button onClick={clearRegion} className="btn-secondary !py-2">
                      <ArrowsPointingOutIcon className="w-4 h-4" /> Clear Region
                    </button>
                  )}
                </div>
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
              className="mt-4 flex items-center justify-between gap-3 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
              <span>{err}</span>
              {paused && !hiddenPause && (
                <button onClick={retry} className="btn-secondary !py-1.5 shrink-0">
                  <ArrowPathIcon className="w-4 h-4" /> Retry
                </button>
              )}
            </motion.div>
          )}
          <div className="mt-4 glass-strong rounded-2xl p-4 text-xs text-slate-500 dark:text-slate-400 space-y-1.5">
            <p className="font-bold text-slate-700 dark:text-slate-200 text-sm">How to use</p>
            <p>1. Press <b>Start</b> and pick the call window or the whole screen (Zoom, Meet, WhatsApp, Teams...).</p>
            <p>2. Drag a box on the preview around <b>only the other person's video</b> — not the toolbar or your own camera.</p>
            <p>3. Keep this window visible beside the call — the gauge updates every ~1.6 seconds. Red = stop the call and verify.</p>
          </div>
        </div>

        <div className="glass-strong rounded-3xl p-6 flex flex-col items-center gap-6">
          <h2 className="text-lg font-bold self-start">Live Signal</h2>
          <ConfidenceGauge value={result?.fake_probability ?? 0}
            label={result ? "Manipulation likelihood" : "Awaiting first frame"} />
          <div className={`w-full rounded-2xl px-4 py-3 text-center text-sm font-bold tracking-wider ${
            !result ? "bg-slate-500/10 text-slate-400" :
            verdict === "FAKE SUSPECTED" ? "bg-rose-500 text-white" :
            verdict === "AMBIGUOUS" ? "bg-amber-500 text-black" : "bg-emerald-500 text-white"
          }`}>
            {result ? verdict.replace("SUSPECTED", "SUSPECTED ⚠") : "START SCREEN SHARE"}
          </div>
          <div className="w-full">
            <div className="flex justify-between text-[11px] mb-1">
              <span className="font-bold text-emerald-500">REAL</span>
              <span className="font-mono text-slate-400">{Math.round(fake ?? 0)}% fake</span>
              <span className="font-bold text-rose-500">FAKE</span>
            </div>
            <div className="h-3 w-full rounded-full overflow-hidden bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500 relative">
              <div className="absolute inset-y-0 bg-white/70 border-r-2 border-black"
                style={{ left: `calc(${(fake ?? 0)}% - 1px)`, width: "2px" }} />
            </div>
          </div>
          <div className="w-full space-y-2 text-xs">
            <div className="flex justify-between"><span className="text-slate-500">Detected faces</span>
              <span className="font-mono">{result?.features?.faces_detected ?? result?.face_analysis?.faces_detected ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Feed liveness</span>
              <span className={`font-mono font-bold ${result?.liveness?.replay_suspected ? "text-amber-500" : "text-emerald-500"}`}>
                {result ? (result?.liveness?.replay_suspected ? "FROZEN" : "LIVE") : "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Signal confidence</span>
              <span className="font-mono">{result?.confidence ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Capture source</span>
              <span className="font-mono">{result?.source === "call" ? "call window" : "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Kaggle reference</span>
              <span className="font-mono">{result?.kaggle_reference_status ?? "ready"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Status</span>
              <span className="font-semibold">{busy ? "analyzing…" : active ? "live" : "idle"}</span></div>
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 text-center">
            Frames are analysed in-memory and never stored. Heavy call compression can slightly
            raise scores — treat verdicts as forensic guidance, not proof.
          </p>
        </div>
      </div>
    </div>
  );
}
