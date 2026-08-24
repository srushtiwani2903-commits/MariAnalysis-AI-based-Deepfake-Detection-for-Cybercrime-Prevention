"""Deepfake awareness chatbot with a real LLM backend.

When GEMINI_API_KEY is set, /api/chat answers ANY question via Google Gemini
(like ChatGPT / Gemini) with conversation context. Without a key, or if the
LLM call fails, it falls back to the built-in rule-based keyword matcher so
the assistant always answers.
"""
import json
import logging
import re
import time
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from config import Config
from utils.security import limiter, sanitize_string

chat_bp = Blueprint("chat", __name__)

_log = logging.getLogger("chat.gemini")

# Skip Gemini for a while after a quota/auth error so the assistant answers
# fast (via the fallback) instead of waiting on the API every time.
_gemini_blocked_until = 0.0

# (keywords, intent, reply)
_KB = [
    (["report", "file complaint", "cybercrime", "police", "1930", "helpline", "law enforcement"],
     "reporting",
     "If you found a deepfake, collect evidence first: keep the original file, take screenshots, "
     "and download the MariAnalysis forensic PDF. Report it on the platform where you saw it, and "
     "file a cybercrime complaint - in India you can call the national helpline 1930 or visit "
     "cybercrime.gov.in. Keep your case ID (like DF-2026-0001) for tracking."),
    (["is this image safe", "is this image fake", "is this photo", "check this image", "image fake"],
     "image_safe",
     "Upload the image to the Image Detection page. MariAnalysis runs error-level analysis, "
     "face/eye checks, metadata forensics and a multi-model ensemble, then gives a verdict, "
     "confidence, trust score and a manipulation heatmap. Treat any result as forensic guidance, "
     "not legal proof."),
    (["voice clone", "voice cloning", "ai voice", "cloned voice", "deepfake voice"],
     "voice_clone",
     "Voice cloning uses AI to copy someone's voice from a short sample. Detect it by listening for "
     "robotic prosody, unnatural pauses and inconsistent emotion. You can upload the audio on the "
     "Audio Detection page - it returns an AI/clone probability plus emotion-mismatch flag. If a "
     "'relative' calls asking for money, hang up and call them back on a verified number."),
    (["avoid", "protect", "prevent", "how do i", "how can i", "safety", "safe from"],
     "avoid",
     "Stay safe from deepfakes: (1) Verify unusual requests over a second trusted channel. "
     "(2) Enable two-factor authentication on accounts. (3) Check media before believing it - "
     "use MariAnalysis or a reverse image search. (4) Never share OTPs or ID documents with "
     "callers. (5) Report scams to your platform and local cybercrime helpline."),
    (["video call", "video meeting", "webcam", "realtime", "live", "zoom", "camera"],
     "video_call",
     "For live calls, enable the Realtime Detection page - it analyses webcam frames and shows a "
     "live confidence verdict. Watch for weird face boundaries, delayed lip-sync, flickering edges "
     "and unnatural eye blinking. When money is involved, confirm identity with a question only the "
     "real person would know."),
    (["deepfake", "what is", "definition", "explain", "how does it work", "ai generated", "synthetic"],
     "what_is",
     "A deepfake is media (image, video, audio or text) created or altered with AI so it looks real. "
     "Common types: face swap, lip-sync, voice clone and image manipulation. Detection works by "
     "analysing recompression artifacts (ELA), texture uniformity, face/eye consistency, lighting, "
     "spectral voice patterns and text perplexity."),
    (["law", "legal", "illegal", "crime", "it act", "section", "punishment", "court"],
     "laws",
     "Deepfake cybercrime is covered by India's IT Act 2000 (Sec. 66C/66D: identity theft, Sec. 66E: "
     "privacy) and IPC Sec. 419/420 (cheating). The Digital Personal Data Protection Act and the 2023 "
     "IT Rules also require platforms to remove deepfakes. Penalties range from fines to imprisonment. "
     "Always preserve evidence and file a formal complaint."),
    (["email", "phish", "scam email", "spam", "bank", "password email", "otp"],
     "email",
     "Suspicious emails often create urgency ('account suspended'), demand money, or send links to "
     "fake login pages. Never click links or enter OTPs from such emails. Paste the email into the "
     "Email Scam Detection page for an instant phishing score, then report it to your provider."),
    (["fake news", "misinformation", "news", "caption", "claim", "fact"],
     "fake_news",
     "Fake news uses manipulated images plus misleading captions. Use the Social Post detection to "
     "scan both the image and the caption together, cross-check claims with fact-checkers "
     "(Poynter network), reverse-search the image, and check the account's age and history."),
    (["trust score", "confidence", "trust", "score"],
     "trust",
     "The trust score (0-100) shows how trustworthy the evidence looks based on metadata, AI "
     "artifacts, compression, face consistency and noise. Higher trust = stronger authentic signals. "
     "It is shown on every result and inside the forensic PDF."),
    (["blockchain", "evidence", "tamper", "hash", "case id", "proof", "immutable"],
     "blockchain",
     "When you report a deepfake, MariAnalysis registers an evidence case (ID like DF-2026-0001) and "
     "locks the file hash, report hash and timestamp into a blockchain-style SHA-256 ledger. You can "
     "verify the chain any time on the Evidence page - if a block was altered, verification fails."),
    (["extension", "browser", "chrome", "social media", "facebook", "instagram", "twitter"],
     "extension",
     "The MariAnalysis browser-extension prototype warns you about possible AI-generated images while "
     "browsing. Install it from the /extension folder, add an API key from your profile, and hover "
     "over images on social sites to see a 'Possible AI-generated' badge."),
    (["chatbot", "who are you", "help", "hi", "hello", "hey"],
     "greeting",
     "Hi! I am the MariAnalysis assistant. Ask me about deepfakes, spotting scams, voice cloning, "
     "reporting cybercrime, cyber laws, or how to use the detectors - I can guide you."),
]

_SYSTEM_PROMPT = (
    "You are DeepGuard, the friendly AI assistant for MariAnalysis - an AI-based deepfake "
    "detection platform for cybercrime prevention. You help users understand deepfakes, detect "
    "AI-generated or manipulated media, avoid scams, recognise voice cloning and phishing, report "
    "cybercrime, and understand relevant cyber laws (India's IT Act 2000, IPC 419/420, DPDP Act). "
    "You can also answer general questions like any helpful assistant. Be clear, warm, concise "
    "(aim for 3-8 sentences unless asked for detail), and stay factual. If a user seems to be "
    "asking about a real emergency or crime in progress, encourage them to contact local "
    "authorities or India's cybercrime helpline 1930. Treat detection results as forensic "
    "guidance, not legal proof."
)

_ROLE_MAP = {"ai": "model", "assistant": "model", "model": "model", "user": "user"}


def _ask_gemini(contents):
    """Call the Gemini generateContent REST API. Returns reply text or None."""
    global _gemini_blocked_until
    if not Config.GEMINI_API_KEY:
        return None
    now = time.time()
    if now < _gemini_blocked_until:
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": Config.GEMINI_MAX_OUTPUT_TOKENS,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=Config.GEMINI_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (429, 403):
            _gemini_blocked_until = now + 600
            _log.warning("Gemini %s (quota/auth) - cooldown 10min", e.code)
        else:
            _log.warning("Gemini HTTP %s: %s", e.code, e.read(300).decode("utf-8", "replace"))
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
        _log.warning("Gemini request failed: %s", e)
        return None
    candidates = body.get("candidates") or []
    if not candidates:
        _log.warning("Gemini returned no candidates")
        return None
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or None


def _match(text):
    for keywords, intent, reply in _KB:
        if any(k in text for k in keywords):
            return intent, reply
    return "unknown", None


def _fallback_reply(intent):
    for _, i, reply in _KB:
        if i == intent:
            return reply
    return ("I can help with deepfake detection, scam prevention, voice cloning, reporting "
            "cybercrime, cyber laws and the MariAnalysis tools. Try asking e.g. "
            "'How do I avoid deepfake scams?' or 'What is a voice clone?'")


@chat_bp.route("", methods=["POST"])
@jwt_required()
def chat():
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(f"chat:{request.remote_addr}")[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429
    data = request.get_json(silent=True) or {}
    message = sanitize_string(data.get("message", ""), 500).strip()
    if not message:
        return jsonify({"message": "Please type a question."}), 400

    # Build the conversation for the LLM from the last few turns (if supplied).
    history = data.get("history") or []
    contents = []
    if isinstance(history, list):
        for turn in history[-12:]:
            role = str(turn.get("role", "")).lower()
            text = sanitize_string(turn.get("text", ""), 500).strip()
            if role in _ROLE_MAP and text:
                contents.append({"role": _ROLE_MAP[role], "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    reply = _ask_gemini(contents)
    if reply:
        return jsonify({"reply": reply, "intent": "gemini", "source": "gemini"})

    text = message.lower()
    intent, rule_reply = _match(text)
    if not rule_reply:
        rule_reply = _fallback_reply(intent)
    return jsonify({"reply": rule_reply, "intent": intent, "source": "rules"})


@chat_bp.route("/suggestions", methods=["GET"])
def suggestions():
    return jsonify({"suggestions": [
        "How do I avoid deepfake scams?",
        "Is this image safe?",
        "What is voice cloning?",
        "How do I report a deepfake?",
        "What are the cyber laws against deepfakes?",
    ]})
