import { ShieldExclamationIcon } from "@heroicons/react/24/outline";

export default function FullPageLoader() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4">
      <span className="w-14 h-14 rounded-2xl bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white animate-pulse">
        <ShieldExclamationIcon className="w-7 h-7" />
      </span>
      <p className="font-mono text-sm text-neon-blue terminal-cursor">Authenticating…</p>
    </div>
  );
}
