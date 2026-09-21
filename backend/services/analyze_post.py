"""Fake-news + deepfake analysis for a social-media post.

Fuses the image and caption verdicts into one misinformation score. Also
handles caption-only posts and posts fetched from a URL.
"""
import time

from services.analyze_image import analyze_image
from services.analyze_text import analyze_text
from config import Config
from services.ensemble import (append_real_models, build_models, explain_short,
                               risk_label, trust_score)
from services.model_providers import (blend_scores, gemini_score, local_score,
                                      score_reason)


def analyze_post(image_path, image_filename, image_size, caption, source_url=None):
    start = time.time()
    text_caption = (caption or "").strip()

    image_result = None
    img_prob = 0.0
    heatmap_file = ""
    file_hash = ""

    if image_path:
        image_result = analyze_image(image_path, image_filename, image_size)
        if "error" in image_result:
            return image_result
        img_prob = image_result["fake_probability"]
        heatmap_file = image_result.get("heatmap_file", "")
        file_hash = image_result.get("file_hash", "")

    caption_result = None
    if len(text_caption) >= 20:
        caption_result = analyze_text(text_caption, image_filename or "caption.txt")

    text_prob = caption_result["fake_probability"] if caption_result else 0.0

    # Combined: image weighs more, caption adds context.
    if image_path and caption_result:
        base = 0.8 * img_prob + 0.2 * text_prob
    elif image_path:
        base = img_prob
    elif caption_result:
        base = text_prob
    else:
        return {"error": "No image or caption text to analyse."}

    base = max(0.0, min(100.0, base))

    # Cross-modal Gemini + local verdicts on image + caption together.
    gemini = local = None
    if image_path:
        gemini = gemini_score("post", file_path=image_path, text=text_caption or None)
        local = local_score("post", file_path=image_path, text=text_caption or None)
        # A social post is an ensemble verdict, so the real AI models carry
        # more weight than the (weak on faces) heuristics.
        blended = blend_scores(base, gemini, local,
                               weights={"heuristic": 0.2, "gemini": 0.5, "local": 0.3})
        base = max(0.0, min(100.0, blended))
        # Confidence guard: never call an image authentic when Gemini is
        # strongly convinced it is AI-generated (and vice-versa).
        if gemini and gemini.get("available"):
            gp = float(gemini.get("fake_probability", 50.0))
            if gp >= 72 and base < 42:
                base = 0.4 * base + 0.6 * gp
            elif gp <= 20 and base > 62:
                base = 0.4 * base + 0.6 * gp
    base = max(0.0, min(100.0, base))
    provider_note = score_reason(gemini, "post") + score_reason(local, "post")

    model_label = f"{image_filename or 'caption'}|{text_caption[:40]}"
    models, _final = build_models("post", base, model_label, spread=4.5)
    models = append_real_models(models, [
        (gemini, f"Gemini ({Config.GEMINI_MODEL})"),
        (local, "Local ViT (deepfake-vs-real)"),
    ])
    result, _risk = _interpret(base)
    risk = risk_label(base)
    trust = trust_score(base, {
        "visual": max(0.0, (100.0 - img_prob) / 100.0),
        "textual": max(0.0, (100.0 - text_prob) / 100.0),
    })

    explanation = explain_short("post", result, base) + provider_note
    recommendations = _recommendations(result)
    elapsed = int((time.time() - start) * 1000)

    metadata = {
        "image_fake_probability": round(img_prob, 1) if image_path else None,
        "caption_fake_probability": round(text_prob, 1) if caption_result else None,
        "caption_length": len(text_caption),
        "file_hash_sha256": file_hash,
    }
    if source_url:
        metadata["source_url"] = source_url

    return {
        "scan_type": "post",
        "filename": image_filename or (image_result or {}).get("filename", "post-caption.txt"),
        "result": result,
        "confidence": 100.0 - abs(base - (100 if result == "fake" else 0)),
        "fake_probability": round(base, 1),
        "misinformation_probability": round(base, 1),
        "trust_score": trust,
        "risk_level": risk,
        "explanation": explanation,
        "recommendations": recommendations,
        "processing_time_ms": elapsed,
        "metadata": metadata,
        "features": {
            "image_ai_probability": round(img_prob / 100.0, 4) if image_path else 0,
            "caption_ai_probability": round(text_prob / 100.0, 4) if caption_result else 0,
            "misinformation_score": round(base / 100.0, 4),
        },
        "models": models,
        "reasons": ((image_result or {}).get("reasons") or []) + ((caption_result or {}).get("reasons") or []),
        "file_hash": file_hash,
        "suspicious_sections": ((caption_result or {}).get("suspicious_sections") or [])[:10],
        "heatmap_file": heatmap_file,
        "ai_providers": {"gemini": gemini, "local": local},
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

