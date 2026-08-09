import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ShareIcon, PhotoIcon, ExclamationTriangleIcon, SparklesIcon } from "@heroicons/react/24/outline";
import api from "../api/api";

// Social post detection: image (profile photo / media) + caption text.
export default function SocialPostDetection() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  const pick = (f) => {
    setError("");
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const analyze = async () => {
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("caption", caption.trim());
      const { data } = await api.post("/detect/post", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.response?.data?.message || err.message);
      setBusy(false);
    }
  };

  return (
    <div className="container-app py-10 max-w-4xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-cyan-400 to-neon-blue text-white mb-4">
          <ShareIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Social Post Detection</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Verify a social media post — combine the attached image with its caption text.
          Fake-news and romance-scam posts often pair AI images with AI-written captions.
        </p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-6 sm:p-8 space-y-6">
        <div className="grid sm:grid-cols-2 gap-5">
          {/* Image */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
              Post image
            </label>
            <div
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]); }}
              className="rounded-2xl border-2 border-dashed border-slate-300 dark:border-white/15 hover:border-neon-blue/60 transition-colors cursor-pointer aspect-square flex flex-col items-center justify-center overflow-hidden bg-slate-50 dark:bg-slate-900/50"
            >
              {preview ? (
                <img src={preview} alt="preview" className="w-full h-full object-cover" />
              ) : (
                <>
                  <PhotoIcon className="w-10 h-10 text-slate-300 dark:text-slate-600" />
                  <p className="text-sm text-slate-500 mt-2">Drop an image or tap to browse</p>
                </>
              )}
            </div>
            <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,.tiff"
              className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          </div>

          {/* Caption */}
          <div className="flex flex-col">
            <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
              Post caption / text
            </label>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={8}
              placeholder="Paste the caption, bio text or message that accompanies the image…"
              className="input !rounded-2xl resize-y font-mono text-sm flex-1"
            />
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1.5">
              Optional — but analyzing both improves accuracy.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {file ? `Image: ${file.name}` : "No image selected"} · {caption.trim().split(/\s+/).filter(Boolean).length} caption words
          </p>
          <button onClick={analyze} disabled={busy || (!file && caption.trim().length < 30)} className="btn-primary">
            <SparklesIcon className="w-5 h-5" /> {busy ? "Analyzing…" : "Analyze Post"}
          </button>
        </div>

        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
            <ExclamationTriangleIcon className="w-5 h-5" /> {error}
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
