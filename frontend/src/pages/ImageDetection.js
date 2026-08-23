import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { PhotoIcon, ExclamationTriangleIcon, SparklesIcon, LinkIcon } from "@heroicons/react/24/outline";
import FileUpload from "../components/FileUpload";
import ScanLoader from "../components/ScanLoader";
import api from "../api/api";

export default function ImageDetection() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [url, setUrl] = useState("");
  const [scanningUrl, setScanningUrl] = useState(false);

  const analyze = async (f) => {
    setFile(f);
    setError("");
    setAnalyzing(true);
    if (f.type.startsWith("image/")) {
      setPreview(URL.createObjectURL(f));
    }
    try {
      const form = new FormData();
      form.append("file", f);
      const { data } = await api.post("/detect/image", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const analyzeUrl = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setError("");
    setScanningUrl(true);
    try {
      const { data } = await api.post("/detect/url", { url: url.trim(), media_type: "image" });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.message);
    } finally {
      setScanningUrl(false);
    }
  };

  return (
    <div className="container-app py-10 max-w-4xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="accent-imgscan-dark inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-cyan text-white mb-4">
          <PhotoIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Image Deepfake Detection</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-xl mx-auto">
          Upload an image to detect AI-generated faces, manipulated pixels and metadata anomalies.
          Supports PNG, JPG, JPEG, WebP, BMP, TIFF.
        </p>
      </motion.div>

      {analyzing ? (
        <ScanLoader text="Running error-level analysis, texture stats and metadata forensics…" />
      ) : (
        <>
          {preview && (
            <div className="mb-6 rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 max-w-md mx-auto">
              <img src={preview} alt="preview" className="w-full h-56 object-cover" />
            </div>
          )}
          <FileUpload accept=".png,.jpg,.jpeg,.webp,.bmp,.tiff" maxMB={50} onFile={analyze}
            label="Drop an image to analyze" />
          <div className="mt-6 glass rounded-xl p-4">
            <form onSubmit={analyzeUrl} className="flex flex-col sm:flex-row gap-3 items-end">
              <div className="flex-1 w-full">
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 flex items-center gap-1">
                  <LinkIcon className="w-3.5 h-3.5" /> Or scan an image from a URL
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/image.jpg"
                  className="w-full bg-white/70 dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-neon-blue/50"
                />
              </div>
              <button type="submit" disabled={scanningUrl} className="btn-secondary !py-2.5">
                {scanningUrl ? "Scanning…" : "Scan URL"}
              </button>
            </form>
          </div>
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="mt-4 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
              <ExclamationTriangleIcon className="w-5 h-5" /> {error}
            </motion.div>
          )}
          <div className="mt-8 grid sm:grid-cols-3 gap-4">
            {[
              ["Error Level Analysis", "Recompression artifacts reveal edits"],
              ["CNN + ViT Ensemble", "Vision transformers spot uncanny faces"],
              ["Metadata Forensics", "EXIF anomalies & stripped headers"],
            ].map(([t, d]) => (
              <div key={t} className="glass rounded-xl p-4">
                <p className="font-semibold text-sm flex items-center gap-2"><SparklesIcon className="w-4 h-4 text-neon-blue" />{t}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{d}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
