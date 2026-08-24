import "./ChatbotAvatar.css";

const MOOD_CLASS = {
  idle: "cb-idle",
  happy: "cb-happy",
  thinking: "cb-thinking",
  alert: "cb-alert",
  surprised: "cb-surprised",
};

export default function ChatbotAvatar({ mood = "idle", size = 44 }) {
  const cls = MOOD_CLASS[mood] || MOOD_CLASS.idle;
  const eyeY = mood === "thinking" ? 20 : 23;
  return (
    <svg className={`cb-avatar ${cls}`} width={size} height={size} viewBox="0 0 64 66" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="cbBodyG" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
        <linearGradient id="cbLimbG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#60a5fa" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>

      <line x1="32" y1="9" x2="32" y2="13" stroke="#8b5cf6" strokeWidth="2.5" strokeLinecap="round" />
      <circle className="cb-antenna-tip" cx="32" cy="6" r="3.5" fill="#a855f7" />

      <rect x="17" y="11" width="30" height="22" rx="9" fill="url(#cbBodyG)" />
      <rect x="21.5" y="15" width="21" height="14" rx="6" fill="#0f172a" opacity="0.92" />

      {mood === "happy" ? (
        <g stroke="#7dd3fc" strokeWidth="2.5" strokeLinecap="round" fill="none">
          <path d="M24.5 23 q2.8 -3.6 5.6 0" />
          <path d="M33.9 23 q2.8 -3.6 5.6 0" />
        </g>
      ) : mood === "alert" ? (
        <g>
          <circle cx="27" cy="23" r="3" fill="#fca5a5" />
          <circle cx="37" cy="23" r="3" fill="#fca5a5" />
        </g>
      ) : mood === "surprised" ? (
        <g>
          <circle cx="27" cy="22.5" r="3.6" fill="#e0f2fe" />
          <circle cx="37" cy="22.5" r="3.6" fill="#e0f2fe" />
          <circle cx="28.3" cy="21.2" r="1.2" fill="#0f172a" />
          <circle cx="38.3" cy="21.2" r="1.2" fill="#0f172a" />
        </g>
      ) : (
        <g fill="#e0f2fe" className={mood === "idle" ? "cb-blink" : ""}>
          <ellipse cx="27" cy={eyeY} rx="2.4" ry="2.8" />
          <ellipse cx="37" cy={eyeY} rx="2.4" ry="2.8" />
        </g>
      )}

      {mood === "happy" && (
        <path d="M27 26.5 q5 4.5 10 0" stroke="#7dd3fc" strokeWidth="2" strokeLinecap="round" fill="none" />
      )}
      {mood === "thinking" && (
        <path d="M28.5 27 h7" stroke="#7dd3fc" strokeWidth="2" strokeLinecap="round" />
      )}
      {mood === "alert" && (
        <path d="M27 28.5 q2.5 -2.5 5 0 q2.5 2.5 5 0" stroke="#fca5a5" strokeWidth="2" strokeLinecap="round" fill="none" />
      )}
      {mood === "surprised" && <circle cx="32" cy="27" r="2.8" fill="#7dd3fc" />}

      {mood === "thinking" && (
        <g className="cb-dots" fill="#a855f7">
          <circle cx="46" cy="12" r="1.8" />
          <circle cx="52" cy="8" r="2.2" />
          <circle cx="58" cy="4" r="2.6" />
        </g>
      )}

      <path d="M29 33 h6 v4 h-6 z" fill="#312e81" />

      <g className="cb-arm cb-arm-l">
        <rect x="12" y="38" width="5" height="11" rx="2.5" fill="url(#cbLimbG)" />
        <circle cx="14.5" cy="50.5" r="3" fill="#c4b5fd" />
      </g>
      <g className="cb-arm cb-arm-r">
        <rect x="47" y="38" width="5" height="11" rx="2.5" fill="url(#cbLimbG)" />
        <circle cx="49.5" cy="50.5" r="3" fill="#c4b5fd" />
      </g>

      <rect x="19" y="36" width="26" height="15" rx="7" fill="url(#cbBodyG)" />
      <circle className="cb-chest" cx="32" cy="43.5" r="2.6" fill="#67e8f9" />

      <rect x="24.5" y="51" width="5.5" height="8" rx="2.75" fill="url(#cbLimbG)" />
      <rect x="34" y="51" width="5.5" height="8" rx="2.75" fill="url(#cbLimbG)" />
      <ellipse cx="26.5" cy="61" rx="4.5" ry="2.2" fill="#312e81" />
      <ellipse cx="37.5" cy="61" rx="4.5" ry="2.2" fill="#312e81" />
    </svg>
  );
}
