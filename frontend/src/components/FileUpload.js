import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CloudArrowUpIcon,
  DocumentTextIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PhotoIcon,
  FilmIcon,
  MusicalNoteIcon,
} from "@heroicons/react/24/outline";

const formatSize = (maxMB) =>
  maxMB >= 1024 ? `${maxMB / 1024} GB` : `${maxMB} MB`;

const IMAGE_EXT = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif", "gif",
  "avif", "heic", "heif", "ico", "svg", "tga", "jfif", "raw", "cr2", "nef",
  "arw", "dng", "psd", "eps"];
const VIDEO_EXT = ["mp4", "avi", "mov", "mkv", "webm", "3gp", "3g2", "mpeg",
  "mpg", "m4v", "ogv", "flv", "wmv", "asf", "ts", "vob", "mts", "m2ts"];
const AUDIO_EXT = ["mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma",
  "aiff", "alac", "amr", "mid", "midi", "pcm", "ape"];

// Classify a file so the upload card can show a real thumbnail (image/video)
// or the right icon (audio/text). Falls back to the extension when the
// browser does not provide a MIME type.
const detectKind = (f) => {
  if (!f) return "file";
  const type = (f.type || "").toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  const ext = (f.name.split(".").pop() || "").toLowerCase();
  if (IMAGE_EXT.includes(ext)) return "image";
  if (VIDEO_EXT.includes(ext)) return "video";
  if (AUDIO_EXT.includes(ext)) return "audio";
  return "text";
};

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
  const [previewUrl, setPreviewUrl] = useState("");
  const [thumbOk, setThumbOk] = useState(true);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);
  const onFileRef = useRef(onFile);
  onFileRef.current = onFile;

  // Build an in-browser preview URL for images/videos so the user can see
  // exactly which media they queued up before scanning. Revoked on unmount
  // or when a different file is chosen.
  useEffect(() => {
    setThumbOk(true);
    if (!file) {
      setPreviewUrl("");
      return;
    }
    const kind = detectKind(file);
    if (kind !== "image" && kind !== "video") {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          clearInterval(interval);
          setUploading(false);
          return 100;
        }
        return p + Math.random() * 14 + 6;
      });
    }, 180);
    return () => clearInterval(interval);
  }, [file]);

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
      setError(`File exceeds the ${formatSize(maxMB)} limit. Not more than ${formatSize(maxMB)} will accept.`);
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

  const kind = file ? detectKind(file) : "file";
  const sizeMB = file ? (file.size / (1024 * 1024)).toFixed(2) : "0";
  const kindLabel = kind === "image" ? "Image"
    : kind === "video" ? "Video"
    : kind === "audio" ? "Audio"
    : "Document";

  return (
    <div className="space-y-4">
      <motion.div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => !uploading && !file && inputRef.current?.click()}
        whileHover={{ scale: 1.005 }}
        animate={drag ? { scale: 1.02 } : { scale: 1 }}
        className={`relative ${file ? "" : "cursor-pointer"} rounded-2xl border-2 border-dashed p-10 text-center
          transition-colors duration-300 bg-white/40 dark:bg-white/[0.03] ${
            drag ? "border-neon-blue bg-neon-blue/5" : "border-neon-blue/40"
          }`}
      >
        <div className="scan-overlay" />
        {file ? (
          <div className="flex flex-col items-center gap-3" title={file.name}>
            <div className="w-32 h-32 rounded-xl overflow-hidden flex-shrink-0 bg-gradient-to-br from-neon-blue/15 to-neon-purple/15 flex items-center justify-center">
              {previewUrl && thumbOk && (kind === "image" || kind === "video") ? (
                kind === "image" ? (
                  <img
                    src={previewUrl}
                    alt={file.name}
                    onError={() => setThumbOk(false)}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <video
                    src={`${previewUrl}#t=0.1`}
                    className="w-full h-full object-cover"
                    muted
                    playsInline
                    preload="metadata"
                  />
                )
              ) : (
                <span className="text-neon-blue">
                  {kind === "image" ? (
                    <PhotoIcon className="w-12 h-12" />
                  ) : kind === "video" ? (
                    <FilmIcon className="w-12 h-12" />
                  ) : kind === "audio" ? (
                    <MusicalNoteIcon className="w-12 h-12" />
                  ) : (
                    <DocumentTextIcon className="w-12 h-12" />
                  )}
                </span>
              )}
            </div>
            <div className="max-w-full px-4">
              <p className="font-semibold text-lg truncate" title={file.name}>{file.name}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {kindLabel} · {sizeMB} MB · selected for scanning
              </p>
            </div>
          </div>
        ) : (
          <>
            <CloudArrowUpIcon className="w-14 h-14 mx-auto text-neon-blue mb-3" />
            <p className="font-semibold text-lg">{drag ? "Release to upload" : label}</p>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              {hint || `Click or drag & drop · Max ${formatSize(maxMB)} · ${accept}`}
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              One file at a time — it will be ready to scan after upload
            </p>
          </>
        )}
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
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-600 dark:text-slate-300 truncate">
                {uploading ? "Uploading…" : "Ready to scan"}
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
            ) : !uploading && progress >= 100 ? (
              <button
                onClick={() => onFileRef.current?.(file)}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm
                  bg-gradient-to-r from-neon-blue to-neon-purple text-white
                  hover:shadow-lg hover:shadow-neon-blue/25 transition-all duration-200
                  active:scale-95"
              >
                <MagnifyingGlassIcon className="w-5 h-5" />
                Scan
              </button>
            ) : null}

            <button
              onClick={() => { setFile(null); setProgress(0); }}
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
