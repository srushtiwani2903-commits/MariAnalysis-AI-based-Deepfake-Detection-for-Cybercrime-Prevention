import { Link } from "react-router-dom";
import {
  ShieldCheckIcon,
  EnvelopeIcon,
  MapPinIcon,
} from "@heroicons/react/24/outline";
import { GitHubIcon, LinkedInIcon, TwitterIcon } from "./SocialIcons";

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 dark:border-white/10 bg-white/40 dark:bg-white/[0.02] backdrop-blur-xl mt-auto">
      <div className="container-app py-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white">
              <ShieldCheckIcon className="w-4 h-4" />
            </span>
            <span className="font-bold">Mari<span className="neon-text">Analysis</span></span>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            AI-powered deepfake detection platform fighting cybercrime by exposing
            manipulated images, videos, audio and text.
          </p>
        </div>

        <div>
          <h4 className="font-semibold mb-3 text-sm uppercase tracking-wider text-slate-500 dark:text-slate-400">Scan & Detect</h4>
          <ul className="space-y-2 text-sm">
            <li><Link to="/detect" className="hover:text-neon-blue transition-colors">Scan Center</Link></li>
            <li><Link to="/detect/image" className="hover:text-neon-blue transition-colors">Image Detection</Link></li>
            <li><Link to="/detect/video" className="hover:text-neon-blue transition-colors">Video Detection</Link></li>
            <li><Link to="/detect/audio" className="hover:text-neon-blue transition-colors">Audio Detection</Link></li>
            <li><Link to="/detect/text" className="hover:text-neon-blue transition-colors">Text Detection</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="font-semibold mb-3 text-sm uppercase tracking-wider text-slate-500 dark:text-slate-400">Prevention</h4>
          <ul className="space-y-2 text-sm">
            <li><Link to="/detect" className="hover:text-neon-blue transition-colors">Verify Media</Link></li>
            <li><Link to="/history" className="hover:text-neon-blue transition-colors">Scan History</Link></li>
            <li><Link to="/forgot-password" className="hover:text-neon-blue transition-colors">Account Recovery</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="font-semibold mb-3 text-sm uppercase tracking-wider text-slate-500 dark:text-slate-400">Contact</h4>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center gap-2"><EnvelopeIcon className="w-4 h-4" /> support@marianalysis.ai</li>
            <li className="flex items-center gap-2"><MapPinIcon className="w-4 h-4" /> Global · 24/7</li>
          </ul>
          <div className="flex gap-3 mt-4">
            {[GitHubIcon, LinkedInIcon, TwitterIcon].map((Icon, i) => (
              <a key={i} href="#" className="p-2 rounded-lg glass hover:text-neon-blue hover:border-neon-blue/50 transition-all">
                <Icon className="w-4 h-4" />
              </a>
            ))}
          </div>
        </div>
      </div>
      <div className="border-t border-slate-200 dark:border-white/10 py-4">
        <p className="text-center text-xs text-slate-500 dark:text-slate-500">
          © {new Date().getFullYear()} MariAnalysis · AI-Based Deepfake Detection for Cybercrime Prevention · Made with security in mind
        </p>
      </div>
    </footer>
  );
}
