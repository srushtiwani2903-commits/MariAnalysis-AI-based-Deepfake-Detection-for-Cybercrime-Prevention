"""Email scam / phishing detection.

Combines the NLP text heuristic with email-specific signals: urgency, financial
pressure, link risk and sender authenticity.
"""
import re
import time

from services.analyze_text import analyze_text
from config import Config
from services.ensemble import (append_real_models, build_models, explain_short,
                               reasons_from_features, risk_label, trust_score)
from services.model_providers import blend_scores, gemini_score, local_score, score_reason

URGENCY = re.compile(r"\b(urgent|immediately|act now|asap|limited time|last chance|"
                     r"expires? (today|soon)|final notice|account suspended)\b", re.I)
FINANCIAL = re.compile(r"\b(bank|account|wire|transfer|bitcoin|crypto|password|verify|"
                       r"credit card|ssn|sin|paypal|invoice|refund|lottery|prize|inheritance)\b", re.I)
GENERIC = re.compile(r"\b(dear (customer|user|member|valued)|sir/madam|our records)\b", re.I)
SPOOF = re.compile(r"\b(support@|admin@|service@|no-reply@|noreply@|security@)\b", re.I)
LINKS = re.compile(r"(https?://|www\.)\S+", re.I)


def analyze_email(text, filename="email-input.txt"):
    start = time.time()
    text = text.strip()

    n_links = len(LINKS.findall(text))
    urgency = len(URGENCY.findall(text))
    financial = len(FINANCIAL.findall(text))
    generic = len(GENERIC.findall(text))
    spoof = len(SPOOF.findall(text))
    words = len(text.split())

    features = {
        "urgency_language": round(min(1.0, urgency / 3.0), 4),
        "financial_pressure": round(min(1.0, financial / 4.0), 4),
        "link_risk": round(min(1.0, n_links / 3.0), 4),
        "sender_authenticity": round(min(1.0, (generic + spoof) / 2.0), 4),
        "word_count": words,
    }

    base = (0.30 * features["urgency_language"]
            + 0.28 * features["financial_pressure"]
            + 0.22 * features["link_risk"]
            + 0.20 * features["sender_authenticity"])

    # Deep signal: feed the body through the NLP text analyzer too.
    nlp = analyze_text(text[:20000], filename) if len(text) >= 30 else None
    if nlp and "error" not in nlp:
        base = base * 0.7 + (nlp["fake_probability"] / 100.0) * 0.3

    base = max(0.0, min(1.0, base))

    # Real AI providers blend (Gemini + local RoBERTa on the email body).
    gemini = gemini_score("email", text=text)
    local = local_score("email", text=text)
    blended = blend_scores(base * 100, gemini, local)
    base = max(0.0, min(1.0, blended / 100.0))
    provider_note = score_reason(gemini, "email") + score_reason(local, "email")

    models, fake_probability = build_models("email", base * 100, filename, spread=5.0)
    models = append_real_models(models, [
        (gemini, f"Gemini ({Config.GEMINI_MODEL})"),
        (local, "Local RoBERTa (openai-detector)"),
    ])
    result, _risk = _interpret(fake_probability)
    risk = risk_label(fake_probability)
    reasons = reasons_from_features("email", features, fake_probability)
    trust = trust_score(fake_probability, {
        "urgency": 1.0 - features["urgency_language"],
        "financial": 1.0 - features["financial_pressure"],
        "links": 1.0 - features["link_risk"],
        "sender": 1.0 - features["sender_authenticity"],
    })
    explanation = explain_short("email", result, fake_probability) + provider_note
    if fake_probability >= 62:
        explanation += (" Typical scam triggers found: urgency cues, financial pressure "
                        "and/or suspicious links/sender. Do not click links or reply.")
    recommendations = _recommendations(result)
    elapsed = int((time.time() - start) * 1000)

    sections = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        if len(s) > 8 and (URGENCY.search(s) or FINANCIAL.search(s) or GENERIC.search(s)):
            sections.append({"text": s[:300], "score": 0.85, "perplexity": 0})

    return {
        "scan_type": "email",
        "filename": filename,
        "result": result,
        "confidence": 100.0 - abs(fake_probability - (100 if result == "fake" else 0)),
        "fake_probability": round(fake_probability, 1),
        "scam_probability": round(fake_probability, 1),
        "trust_score": trust,
        "risk_level": risk,
        "explanation": explanation,
        "recommendations": recommendations,
        "processing_time_ms": elapsed,
        "metadata": features,
        "features": features,
        "models": models,
        "reasons": reasons,
        "suspicious_sections": sections,
        "ai_providers": {"gemini": gemini, "local": local},
        "model": "phish-heuristic-v1",
    }


def _interpret(prob):
    # Lower thresholds than media: flagging a legit email for review is cheap,
    # missing a scam is not.
    if prob >= 55:
        return "fake", "high"
    if prob >= 38:
        return "inconclusive", "medium"
    return "authentic", "low"


def _recommendations(result):
    base = ["Do not click links or download attachments from the email",
            "Verify the sender through an official channel / phone number",
            "Report the email to your provider (mark as phishing)",
            "If money is involved, contact your bank immediately"]
    if result == "fake":
        return "\n".join(["Treat this email as a phishing / scam attempt.",
                          "Forward it to your security team or the platform's abuse address.",
                          "Report to cybercrime authorities with a screenshot."] + base[:2])
    return "\n".join(base)

