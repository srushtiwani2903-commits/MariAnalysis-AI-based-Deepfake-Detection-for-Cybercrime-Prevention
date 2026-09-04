import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { MusicalNoteIcon, ExclamationTriangleIcon, SparklesIcon } from "@heroicons/react/24/outline";
import FileUpload from "../components/FileUpload";
import ScanLoader from "../components/ScanLoader";
import api from "../api/api";

export default function AudioDetection() {
  const navigate = useNavigate();
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [audio, setAudio] = useState(null);

  const analyze = async (f) => {
    setError("");
    setAnalyzing(true);
    setAudio(URL.createObjectURL(f));
    try {
      const form = new FormData();
      form.append("file", f);
      const { data } = await api.post("/detect/audio", form, {
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
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-pink-500 to-rose-400 text-white mb-4">
          <MusicalNoteIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl font-bold">Audio & Voice Clone Detection</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-xl mx-auto">
          Detect synthetic and cloned voices using spectral analysis, MFCC variance and prosody checks.
          Supports MP3, WAV, OGG, FLAC, M4A, AAC, OPUS, WMA, AIFF, ALAC, AMR.
        </p>
      </motion.div>

      {analyzing ? (
        <ScanLoader text="Computing spectrogram, spectral flatness and MFCC features…" />
      ) : (
        <>
          {audio && (
            <div className="mb-6 rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 max-w-md mx-auto p-4 bg-black">
              <audio src={audio} controls className="w-full" />
            </div>
          )}
          <FileUpload accept=".mp3,.wav,.ogg,.flac,.m4a,.aac,.opus,.wma,.aiff,.alac,.amr,.mid,.midi,.pcm,.ape" maxMB={10240} onFile={analyze}
            label="Drop an audio file to analyze" />
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="mt-4 flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
              <ExclamationTriangleIcon className="w-5 h-5" /> {error}
            </motion.div>
          )}
          <div className="mt-8 grid sm:grid-cols-3 gap-4">
            {[
              ["Spectrogram Analysis", "Librosa spectral flatness fingerprint"],
              ["Voice Clone Detection", "MFCC variance exposes synthetic prosody"],
              ["Emotion Consistency", "Robotic pauses & unnatural pitch shifts"],
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
