import "./ChatbotAvatar.css";

const MOOD_CLASS = {
  idle: "cb-idle",
  happy: "cb-happy",
  thinking: "cb-thinking",
  alert: "cb-alert",
  surprised: "cb-surprised",
};

export default function ChatbotAvatar({ mood = "idle", size = 40 }) {
  const cls = MOOD_CLASS[mood] || MOOD_CLASS.idle;
  return (
    <svg className={`cb-avatar ${cls}`} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="cbBody" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
      </defs>

      <line x1="32" y1="11" x2="32" y2="16" stroke="url(#cbBody)" strokeWidth="3" strokeLinecap="round" />
      <circle className="cb-antenna-tip" cx="32" cy="8" r="4" fill="#a855f7" />

      <rect x="12" y="14" width="40" height="36" rx="12" fill="url(#cbBody)" />
      <rect x="17" y="19" width="30" height="26" rx="9" fill="#0f172a" opacity="0.92" />

      {mood === "happy" ? (
        <g stroke="#7dd3fc" strokeWidth="3" strokeLinecap="round" fill="none">
          <path d="M23 31 q3.5 -4.5 7 0" />
          <path d="M34 31 q3.5 -4.5 7 0" />
        </g>
      ) : mood === "alert" ? (
        <g>
          <circle cx="27" cy="30" r="4" fill="#fca5a5" />
          <circle cx="37" cy="30" r="4" fill="#fca5a5" />
        </g>
      ) : mood === "surprised" ? (
        <g>
          <circle cx="27" cy="29" r="4.5" fill="#e0f2fe" />
          <circle cx="37" cy="29" r="4.5" fill="#e0f2fe" />
          <circle cx="28.5" cy="27.5" r="1.6" fill="#0f172a" />
          <circle cx="38.5" cy="27.5" r="1.6" fill="#0f172a" />
        </g>
      ) : (
        <g fill="#e0f2fe" className={mood === "idle" ? "cb-blink" : ""}>
          <ellipse cx="27" cy={mood === "thinking" ? 26 : 29} rx="3" ry="3.5" />
          <ellipse cx="37" cy={mood === "thinking" ? 26 : 29} rx="3" ry="3.5" />
        </g>
      )}

      {mood === "happy" && (
        <path d="M26 36 q6 5.5 12 0" stroke="#7dd3fc" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      )}
      {mood === "thinking" && (
        <path d="M28 38 h9" stroke="#7dd3fc" strokeWidth="2.5" strokeLinecap="round" />
      )}
      {mood === "alert" && (
        <path d="M26 39 q3 -3 6 0 q3 3 6 0" stroke="#fca5a5" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      )}
      {mood === "surprised" && <circle cx="32" cy="38" r="3.5" fill="#7dd3fc" />}

      {mood === "thinking" && (
        <g className="cb-dots" fill="#a855f7">
          <circle cx="46" cy="13" r="2" />
          <circle cx="52" cy="9" r="2.5" />
          <circle cx="58" cy="5" r="3" />
        </g>
      )}
    </svg>
  );
}
