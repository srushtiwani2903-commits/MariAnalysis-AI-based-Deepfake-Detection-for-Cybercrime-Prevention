// Shared display formatters

export function humanSize(bytes) {
  if (bytes == null) return "—";
  const size = Number(bytes);
  if (isNaN(size) || size === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = size;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function timeAgo(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function riskColor(risk) {
  return {
    low: "text-emerald-400",
    medium: "text-amber-400",
    high: "text-orange-400",
    critical: "text-rose-400",
  }[risk] || "text-slate-400";
}
