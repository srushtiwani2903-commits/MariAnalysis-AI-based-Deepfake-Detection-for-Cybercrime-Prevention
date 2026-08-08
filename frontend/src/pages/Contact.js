import { useState } from "react";
import { motion } from "framer-motion";
import {
  EnvelopeIcon, MapPinIcon, PaperAirplaneIcon,
  ExclamationTriangleIcon, CheckCircleIcon,
} from "@heroicons/react/24/outline";
import { GitHubIcon, LinkedInIcon, TwitterIcon, WhatsAppIcon } from "../components/SocialIcons";

export default function Contact() {
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.message) {
      setError("Please fill in all required fields.");
      return;
    }
    setError("");
    setSent(true);
    setForm({ name: "", email: "", subject: "", message: "" });
    setTimeout(() => setSent(false), 5000);
  };

  return (
    <div className="container-app py-12 space-y-12">
      <div className="text-center max-w-2xl mx-auto">
        <span className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple text-white mb-4">
          <EnvelopeIcon className="w-8 h-8" />
        </span>
        <h1 className="text-3xl sm:text-4xl font-bold">Contact Us</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-3">
          Questions, partnerships or deepfake incidents? Our team responds within 24 hours.
        </p>
      </div>

      <div className="grid lg:grid-cols-5 gap-8">
        {/* Form */}
        <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="lg:col-span-3">
          <form onSubmit={onSubmit} className="glass-strong rounded-3xl p-8 space-y-5">
            {sent && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex items-center gap-2 text-emerald-400 text-sm bg-emerald-400/10 border border-emerald-400/30 rounded-xl px-4 py-3">
                <CheckCircleIcon className="w-5 h-5" /> Message sent successfully. We'll be in touch!
              </motion.div>
            )}
            {error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex items-center gap-2 text-rose-400 text-sm bg-rose-400/10 border border-rose-400/30 rounded-xl px-4 py-3">
                <ExclamationTriangleIcon className="w-5 h-5" /> {error}
              </motion.div>
            )}

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">Name *</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input" placeholder="Your name" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">Email *</label>
                <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="input" placeholder="you@example.com" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Subject</label>
              <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} className="input" placeholder="Deepfake report, partnership, support…" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Message *</label>
              <textarea rows={5} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} className="input resize-y" placeholder="Describe your concern…" />
            </div>
            <button type="submit" className="btn-primary w-full justify-center !py-3">
              <PaperAirplaneIcon className="w-5 h-5" /> Send Message
            </button>
          </form>
        </motion.div>

        {/* Contact info + map */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass rounded-2xl p-6 space-y-4">
            <h3 className="font-bold">Reach us directly</h3>
            <div className="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
              <EnvelopeIcon className="w-5 h-5 text-neon-blue" /> support@deepguard.ai
            </div>
            <div className="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
              <MapPinIcon className="w-5 h-5 text-neon-blue" /> Global · Remote · 24/7 monitoring
            </div>
            <div className="flex gap-3 pt-2">
              {[
                [GitHubIcon, "github.com/deepguard"],
                [LinkedInIcon, "linkedin.com/company/deepguard"],
                [TwitterIcon, "@deepguard_ai"],
                [WhatsAppIcon, "+1 (555) 010-2299"],
              ].map(([Icon, label], i) => (
                <a key={i} href="#" title={label} className="p-2.5 rounded-xl glass hover:text-neon-blue hover:border-neon-blue/50 transition-all">
                  <Icon className="w-5 h-5" />
                </a>
              ))}
            </div>
          </div>

          <div className="glass rounded-2xl overflow-hidden h-64 relative">
            <iframe
              title="Office location"
              className="w-full h-full grayscale-[0.2] dark:grayscale"
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d4484.7!2d-0.1278!3d51.5074!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2zNTHCsDMwJzI2LjYiTiAwwrAwNyczOC4wIlc!5e0!3m2!1sen!2suk!4v1700000000000"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
