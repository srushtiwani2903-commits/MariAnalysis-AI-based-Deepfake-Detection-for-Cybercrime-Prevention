import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { FilmIcon, ExclamationTriangleIcon, SparklesIcon } from "@heroicons/react/24/outline";
import FileUpload from "../components/FileUpload";
import ScanLoader from "../components/ScanLoader";
import api from "../api/api";

export default function VideoDetection() {
  const navigate = useNavigate();
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [video, setVideo] = useState(null);

  const analyze = async (f) => {
    setError("");
    setAnalyzing(true);
    setVideo(URL.createObjectURL(f));
    try {
      const form = new FormData();
      form.append("file", f);
      const { data } = await api.post("/detect/video", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate(`/results/${data.result.scan_id}`, { state: { result: data.result } });
    } catch (err) {
      setError(err.message);
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="container-app py-10 max-w-4xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-purple to-fuchsia-500 text-white mb-4">
          <FilmIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Video Deepfake Detection</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-xl mx-auto">
          Extract frames, detect faces and analyze temporal consistency to expose AI-generated video.
          Supports MP4, AVI, MOV, MKV, WebM, 3GP, MPEG, MPG, M4V, OGV, FLV, WMV, TS, VOB, MTS.
        </p>
      </motion.div>

      {analyzing ? (
        <ScanLoader text="Extracting frames, detecting faces, running temporal analysis…" />
      ) : (
        <>
          {video && (
            <div className="mb-6 rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 max-w-md mx-auto">
              <video src={video} controls className="w-full h-56 object-contain bg-black" />
            </div>
          )}
          <FileUpload accept=".mp4,.avi,.mov,.mkv,.webm,.3gp,.3g2,.mpeg,.mpg,.m4v,.ogv,.flv,.wmv,.asf,.ts,.vob,.mts,.m2ts" maxMB={20480} onFile={analyze}
            label="Drop a video to analyze" />
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="mt-4 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
              <ExclamationTriangleIcon className="w-5 h-5" /> {error}
            </motion.div>
          )}
          <div className="mt-8 grid sm:grid-cols-3 gap-4">
            {[
              ["Frame Extraction", "MediaPipe + Haar face detection per frame"],
              ["Temporal Analysis", "Lip-sync & motion consistency checks"],
              ["Manipulation Map", "Timeline of suspicious segments"],
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
