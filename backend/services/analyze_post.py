"""Fake-news + deepfake combined analysis for a social-media post.

Fuses the image verdict with the caption (text) verdict into a single
misinformation score.
"""
import time

from services.analyze_image import analyze_image
from services.analyze_text import analyze_text
from config import Config
from services.ensemble import (append_real_models, build_models, explain_short,
                               risk_label, trust_score)
from services.model_providers import blend_scores, gemini_score, score_reason


def analyze_post(image_path, image_filename, image_size, caption):
    start = time.time()

    image_result = analyze_image(image_path, image_filename, image_size)
    if "error" in image_result:
        return image_result

    caption_result = None
    if caption and len(caption.strip()) >= 20:
        caption_result = analyze_text(caption, "caption.txt")

    img_prob = image_result["fake_probability"]
    text_prob = caption_result["fake_probability"] if caption_result else 0.0

    # Combined: image weighs more, caption adds context.
    if caption_result:
        base = 0.7 * img_prob + 0.3 * text_prob
    else:
        base = img_prob

    base = max(0.0, min(100.0, base))

    # Cross-modal Gemini verdict on image + caption together.
    gemini = gemini_score("post", file_path=image_path, text=caption or "")
    blended = blend_scores(base, gemini, None)
    base = max(0.0, min(100.0, blended))
    provider_note = score_reason(gemini, "post")

    models, _final = build_models("post", base, f"{image_filename}|{caption[:40]}", spread=4.5)
    models = append_real_models(models, [(gemini, f"Gemini ({Config.GEMINI_MODEL})")])
    result, _risk = _interpret(base)
    risk = risk_label(base)
    trust = trust_score(base, {
        "visual": max(0.0, (100.0 - img_prob) / 100.0),
        "textual": max(0.0, (100.0 - text_prob) / 100.0),
    })

    explanation = explain_short("post", result, base) + provider_note
    recommendations = _recommendations(result)
    elapsed = int((time.time() - start) * 1000)

    return {
        "scan_type": "post",
        "filename": image_filename,
        "result": result,
        "confidence": 100.0 - abs(base - (100 if result == "fake" else 0)),
        "fake_probability": round(base, 1),
        "misinformation_probability": round(base, 1),
        "trust_score": trust,
        "risk_level": risk,
        "explanation": explanation,
        "recommendations": recommendations,
        "processing_time_ms": elapsed,
        "metadata": {
            "image_fake_probability": round(img_prob, 1),
            "caption_fake_probability": round(text_prob, 1) if caption_result else None,
            "caption_length": len(caption or ""),
            "file_hash_sha256": image_result.get("file_hash", ""),
        },
        "features": {
            "image_ai_probability": round(img_prob / 100.0, 4),
            "caption_ai_probability": round(text_prob / 100.0, 4) if caption_result else 0,
            "misinformation_score": round(base / 100.0, 4),
        },
        "models": models,
        "reasons": (image_result.get("reasons") or []) + (caption_result.get("reasons") or []),
        "file_hash": image_result.get("file_hash", ""),
        "suspicious_sections": (caption_result.get("suspicious_sections") or [])[:10],
        "heatmap_file": image_result.get("heatmap_file", ""),
        "ai_providers": {"gemini": gemini, "local": None},
        "model": "cross-modal-fusion-v1",
    }


def _interpret(prob):
    if prob >= 62:
        return "fake", "high"
    if prob >= 42:
        return "inconclusive", "medium"
    return "authentic", "low"


def _recommendations(result):
    base = ["Check the claim against trusted fact-checkers (e.g. Poynter network)",
            "Run a reverse image search on the attached photo",
            "Verify the account that posted it — new accounts are a red flag",
            "Read the full article/source before sharing"]
    if result == "fake":
        return "\n".join(["Do not share or upvote this post.",
                          "Report it as misinformation on the platform.",
                          "Share the verified fact-check instead."] + base[:2])
    return "\n".join(base)

