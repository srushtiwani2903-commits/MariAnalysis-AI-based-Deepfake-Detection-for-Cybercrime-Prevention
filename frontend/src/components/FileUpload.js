import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CloudArrowUpIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";

// Drag & drop uploader with live progress + validation
export default function FileUpload({
  accept,
  onFile,
  maxMB = 50,
  label = "Drop your file here",
  hint,
}) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!file || uploading) return;
    // Simulated upload progress
    setUploading(true);
    setProgress(0);
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          clearInterval(interval);
          setUploading(false);
          onFile?.(file);
          return 100;
        }
        return p + Math.random() * 14 + 6;
      });
    }, 180);
    return () => clearInterval(interval);
  }, [file, uploading]);

  const validate = (f) => {
    if (!f) return false;
    const accepted = accept.split(",").map((a) => a.trim().toLowerCase());
    const ext = "." + f.name.split(".").pop().toLowerCase();
    const typeOk = accepted.includes(ext) || (f.type && accepted.includes(f.type));
    if (!typeOk) {
      setError(`File type not supported. Allowed: ${accept}`);
      return false;
    }
    if (f.size > maxMB * 1024 * 1024) {
      setError(`File exceeds the ${maxMB} MB limit.`);
      return false;
    }
    setError("");
    return true;
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f && validate(f)) setFile(f);
  };

  const onSelect = (e) => {
    const f = e.target.files?.[0];
    if (f && validate(f)) setFile(f);
  };

  return (
    <div className="space-y-4">
      <motion.div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        whileHover={{ scale: 1.005 }}
        animate={drag ? { scale: 1.02, borderColor: "#22d3ee" } : { borderColor: "rgba(34,211,238,0.4)" }}
        className={`relative cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center
          transition-colors duration-300 bg-white/40 dark:bg-white/[0.03] ${
            drag ? "border-neon-blue bg-neon-blue/5" : ""
          }`}
      >
        <div className="scan-overlay" />
        <CloudArrowUpIcon className="w-14 h-14 mx-auto text-neon-blue mb-3" />
        <p className="font-semibold text-lg">{drag ? "Release to upload" : label}</p>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {hint || `Click or drag & drop · Max ${maxMB} MB · ${accept}`}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={onSelect}
          className="hidden"
        />
      </motion.div>

      {error && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3"
        >
          <ExclamationTriangleIcon className="w-5 h-5" /> {error}
        </motion.div>
      )}

      <AnimatePresence>
        {file && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass rounded-xl p-4 flex items-center gap-3"
          >
            <span className="p-2 rounded-lg bg-neon-blue/10 text-neon-blue">
              <DocumentTextIcon className="w-6 h-6" />
            </span>
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{file.name}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {(file.size / (1024 * 1024)).toFixed(2)} MB
              </p>
            </div>

            {uploading ? (
              <div className="w-32">
                <div className="h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-neon-blue to-neon-purple glow-progress"
                       style={{ width: `${progress}%` }} />
                </div>
                <p className="text-xs text-center mt-1 font-mono">{Math.round(progress)}%</p>
              </div>
            ) : file ? (
              <span className="text-emerald-400"><CheckCircleIcon className="w-6 h-6" /></span>
            ) : null}

            <button
              onClick={() => setFile(null)}
              className="p-1.5 rounded-lg hover:bg-rose-500/10 text-rose-400 transition-colors"
              aria-label="Remove file"
            >
              <XCircleIcon className="w-5 h-5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
