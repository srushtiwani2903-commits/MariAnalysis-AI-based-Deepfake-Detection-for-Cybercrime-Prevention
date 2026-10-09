import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ShareIcon, PhotoIcon, LinkIcon, ExclamationTriangleIcon, SparklesIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import api from "../api/api";

// Brand colours for the platform badge shown on the link preview.
const PLATFORM_COLORS = {
  youtube: "bg-red-600",
  instagram: "bg-gradient-to-br from-pink-500 to-amber-400",
  x: "bg-slate-900",
  facebook: "bg-blue-600",
  tiktok: "bg-slate-900",
  linkedin: "bg-sky-700",
  reddit: "bg-orange-600",
  pinterest: "bg-red-700",
  threads: "bg-slate-900",
  snapchat: "bg-yellow-500",
  telegram: "bg-sky-500",
  whatsapp: "bg-green-500",
  web: "bg-slate-500",
};

const URL_RE = /^https?:\/\/\S+\.\S+/i;

// Accept "instagram.com/p/..." and turn it into a full https URL.
const normalizeUrl = (u) => {
  const t = (u || "").trim();
  if (!t || /^https?:\/\//i.test(t)) return t;
  if (/^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(t)) return "https://" + t;
  return t;
};

// Social post detection: image (profile photo / media) + caption text, or a post URL.
export default function SocialPostDetection() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [caption, setCaption] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [link, setLink] = useState(null);
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkError, setLinkError] = useState("");
  const inputRef = useRef(null);
  const lastFetchedUrl = useRef("");

  const pick = (f) => {
    setError("");
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  // Debounced link preview: after the URL is pasted, fetch the post's
  // thumbnail + caption + platform name and show a card.
  useEffect(() => {
    const u = normalizeUrl(url);
    if (!URL_RE.test(u)) {
      setLink(null);
      setLinkError("");
      lastFetchedUrl.current = "";
      return;
    }
    if (u === lastFetchedUrl.current) return;
    const t = setTimeout(async () => {
      setLinkBusy(true);
      setLinkError("");
      try {
        const { data } = await api.post("/detect/post/preview", { url: u });
        setLink(data.preview || null);
        lastFetchedUrl.current = u;
        // Auto-fill the caption from the post when the field is still empty.
        setCaption((c) => (c.trim() ? c : (data.preview?.caption || "")));
      } catch (e) {
        setLink(null);
        setLinkError(e.response?.data?.message || e.message);
      } finally {
        setLinkBusy(false);
      }
    }, 700);
    return () => clearTimeout(t);
  }, [url]);

  const analyze = async () => {
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      if (url.trim()) form.append("source_url", normalizeUrl(url));
      if (link?.thumbnail) form.append("image_url", link.thumbnail);
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
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-cyan to-neon-blue text-white mb-4">
          <ShareIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Post / URL Scan</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-2xl mx-auto">
          Paste any website or social post link and scan it for a <b>Real</b> or <b>Fake</b>
          {" "}verdict. Adding the image or caption is optional — it just makes the result stronger.
        </p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="glass-strong rounded-3xl p-6 sm:p-8 space-y-6">
        <div>
          <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
            Website / Post URL
          </label>
          <div className="flex items-center gap-2 rounded-2xl border border-slate-300 dark:border-white/15 bg-slate-50 dark:bg-slate-900/50 px-3 focus-within:border-neon-blue/60">
            <LinkIcon className="w-4 h-4 text-slate-400" />
            <input
              value={url}
              onChange={(e) => { setError(""); setUrl(e.target.value); }}
              type="url"
              placeholder="https://x.com/user/status/… or a direct image link"
              className="input !border-none !bg-transparent flex-1"
            />
            {linkBusy && <ArrowPathIcon className="w-4 h-4 text-slate-400 animate-spin shrink-0" />}
          </div>
        </div>

        {/* Link preview: platform + thumbnail + caption scraped from the post */}
        {(linkBusy || link || linkError) && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/40 p-3">
            {linkError && !linkBusy && (
              <p className="text-xs text-rose-400 flex items-center gap-2">
                <ExclamationTriangleIcon className="w-4 h-4" /> {linkError}
              </p>
            )}
            {linkBusy && !link && (
              <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
                <ArrowPathIcon className="w-4 h-4 animate-spin" /> Fetching post preview…
              </p>
            )}
            {link && (
              <div className="flex gap-3">
                <div className="w-24 h-24 shrink-0 rounded-xl overflow-hidden bg-slate-200 dark:bg-slate-800 flex items-center justify-center">
                  {link.thumbnail ? (
                    <img src={link.thumbnail} alt="post thumbnail" className="w-full h-full object-cover"
                      onError={(e) => { e.currentTarget.style.display = "none"; }} />
                  ) : (
                    <PhotoIcon className="w-8 h-8 text-slate-400" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`inline-flex items-center text-[11px] font-bold px-2.5 py-0.5 rounded-full text-white ${PLATFORM_COLORS[link.platform_slug] || PLATFORM_COLORS.web}`}>
                      {link.platform}
                    </span>
                    {link.author && <span className="text-[11px] text-slate-500 dark:text-slate-400 truncate">by {link.author}</span>}
                  </div>
                  {link.title && <p className="text-sm font-semibold truncate">{link.title}</p>}
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-3">
                    {link.caption || (link.thumbnail
                      ? "No caption text found in this post."
                      : "Preview not available — this site blocks automated access. You can still upload a screenshot or paste the caption.")}
                  </p>
                </div>
              </div>
            )}
          </motion.div>
        )}

        <div className="grid sm:grid-cols-2 gap-5">
          {/* Image */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
              Post image <span className="font-normal text-slate-400">(optional)</span>
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
            <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,.tiff,.tif,.gif,.avif,.heic,.heif,.ico,.svg,.tga,.jfif,.raw,.cr2,.nef,.arw,.dng,.psd,.eps"
              className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          </div>

          {/* Caption */}
          <div className="flex flex-col">
            <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
              Post caption / text <span className="font-normal text-slate-400">(optional)</span>
            </label>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={8}
              placeholder="Paste the caption, bio text or message that accompanies the image…"
              className="input !rounded-2xl resize-y font-mono text-sm flex-1"
            />
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1.5">
              Optional — auto-filled from the post when a link is pasted.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {url.trim() ? `URL: ${url.trim()}` : file ? `Image: ${file.name}` : "Paste a link, or add an image / caption"} · {caption.trim().split(/\s+/).filter(Boolean).length} caption words
          </p>
          <button onClick={analyze} disabled={busy || (!file && !url.trim() && caption.trim().length < 20)} className="btn-primary">
            <SparklesIcon className="w-5 h-5" /> {busy ? "Scanning…" : "Scan for Real / Fake"}
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
