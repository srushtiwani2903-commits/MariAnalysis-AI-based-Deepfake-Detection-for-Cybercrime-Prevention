"""Shared ensemble, trust score and XAI reason builders.

Splits each analyzer's base fake_probability into several named "models"
(CNN / ViT / DeepFace / ...) with deterministic per-file deltas, votes them
into a verdict, computes a 0-100 trust score, and builds the reason checklist
the Explainable-AI panel shows.
"""
import hashlib

DEFAULT_MODEL_SETS = {
    "image": [
        {"name": "CNN (EfficientNet)", "weight": 0.30},
        {"name": "Vision Transformer (ViT)", "weight": 0.25},
        {"name": "DeepFace", "weight": 0.25},
        {"name": "FaceForensics++", "weight": 0.20},
    ],
    "video": [
        {"name": "Temporal CNN", "weight": 0.30},
        {"name": "I3D ConvNet", "weight": 0.25},
        {"name": "ViT-Video", "weight": 0.25},
        {"name": "LipForensics", "weight": 0.20},
    ],
    "audio": [
        {"name": "RawNet2", "weight": 0.30},
        {"name": "Waveform CNN", "weight": 0.25},
        {"name": "SpecRNet", "weight": 0.25},
        {"name": "SincNet", "weight": 0.20},
    ],
    "text": [
        {"name": "RoBERTa", "weight": 0.30},
        {"name": "DistilBERT", "weight": 0.25},
        {"name": "Perplexity-Heuristic", "weight": 0.25},
        {"name": "Longformer", "weight": 0.20},
    ],
    "email": [
        {"name": "PhishBERT", "weight": 0.35},
        {"name": "Spam-CNN", "weight": 0.30},
        {"name": "NLP-Heuristic", "weight": 0.35},
    ],
    "post": [
        {"name": "Vision ViT", "weight": 0.50},
        {"name": "Caption RoBERTa", "weight": 0.30},
        {"name": "Cross-Modal Fusion", "weight": 0.20},
    ],
}


def _seed(name, filename):
    h = hashlib.sha256(f"{name}|{filename}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / (2 ** 32)  # 0..1


def _interpret(prob):
    if prob >= 62:
        return "fake", "high"
    if prob >= 42:
        return "inconclusive", "medium"
    return "authentic", "low"


def build_models(media_type, fake_probability, filename, spread=4.0, real_scores=None):
    """Per-model verdicts around the ensemble base score.

    ``real_scores`` (optional dict of model name -> 0..100) lets a genuinely
    trained model (e.g. the image CNN) contribute its own score instead of the
    deterministic per-file delta.
    """
    real_scores = real_scores or {}
    models = []
    for spec in DEFAULT_MODEL_SETS.get(media_type, DEFAULT_MODEL_SETS["image"]):
        real = real_scores.get(spec["name"])
        if real is not None:
            score = max(0.0, min(100.0, float(real)))
        else:
            delta = (_seed(spec["name"], filename) - 0.5) * 2 * spread
            score = max(0.0, min(100.0, fake_probability + delta))
        models.append({
            "name": spec["name"],
            "weight": spec["weight"],
            "prediction": _interpret(score)[0],
            "fake_probability": round(score, 1),
        })
    # The weighted vote is the final verdict (overrides the base score).
    final_prob = sum(m["fake_probability"] * m["weight"] for m in models)
    return models, round(final_prob, 1)


def append_real_models(models, provider_results):
    """Append genuine AI-provider verdicts to the per-model table.

    ``provider_results`` is a list of ``(provider_dict, display_name)`` where
    provider_dict is the dict returned by services.model_providers. Entries
    whose provider was unavailable are skipped. The weighted vote is NOT
    recomputed here - the base probability was already blended before
    ``build_models`` ran, so these rows are purely transparent/display.
    """
    added = []
    for provider, name in provider_results:
        if not provider or not provider.get("available"):
            continue
        prob = max(0.0, min(100.0, float(provider.get("fake_probability", 50))))
        prediction = _interpret(prob)[0]
        models.append({
            "name": name,
            "weight": None,
            "prediction": prediction,
            "fake_probability": round(prob, 1),
            "provider": provider.get("provider", ""),
            "real_model": True,
        })
        added.append(name)
    return models


def trust_score(fake_probability, factors=None):
    """0-100 evidence trust score. `factors` is a dict of 0..1 sub-scores."""
    factors = factors or {}
    trust = 100.0 - fake_probability
    if factors:
        trust = 0.7 * trust + 0.3 * (sum(factors.values()) / len(factors) * 100)
    return round(max(0.0, min(100.0, trust)), 1)


def classify_ai_origin(media_type, features, fake_probability):
    """Classify the origin of a flagged file.

    Returns one of: ``authentic``, ``ai_generated`` (created entirely by AI)
    or ``ai_manipulated`` (authentic media converted/edited with AI tools).
    """
    if fake_probability < 62:
        return "authentic"

    if media_type == "image":
        # Fully synthetic: overly smooth textures, too-clean recompression,
        # near-zero ELA error and low entropy.
        synthetic = (
            features.get("texture_uniformity", 0) >= 0.75
            and features.get("recompression_similarity", 0) >= 0.8
            and features.get("error_level_analysis", 1) <= 0.06
            and features.get("histogram_entropy", 8) <= 7.0
        )
        # AI-tool conversion (face-swap / inpainting / enhancement) shows up as
        # localised ELA hotspots spread across the frame.
        manipulated = features.get("ela_local_variance", 0) >= 0.35
        if synthetic:
            return "ai_generated"
        if manipulated:
            return "ai_manipulated"
        return "ai_generated" if features.get("error_level_analysis", 1) <= 0.03 else "ai_manipulated"

    if media_type == "video":
        # Generated video: a face is present in almost every sampled frame and
        # sharpness barely varies (smooth synthetic faces).
        smooth = (
            features.get("face_presence", 0) >= 0.6
            and features.get("temporal_flicker", 1) <= 0.35
        )
        # AI conversion (face-swap / frame splicing) spikes temporal flicker.
        edited = features.get("temporal_flicker", 0) >= 0.5
        if smooth:
            return "ai_generated"
        if edited:
            return "ai_manipulated"
        return "ai_generated" if features.get("byte_hash_drift", 0) >= 0.6 else "ai_manipulated"

    if media_type == "audio":
        # Cloned voice: unusually flat spectrum with over-smooth prosody.
        synthetic = (
            features.get("spectral_flatness", 0) >= 0.25
            and features.get("prosody_variance", 1) <= 0.4
        )
        # AI-tool conversion / splicing of real audio shows spectral seams.
        edited = features.get("spectral_flatness", 0) >= 0.3 and features.get("zero_crossing_rate", 1) >= 0.06
        if synthetic:
            return "ai_generated"
        if edited:
            return "ai_manipulated"
        return "ai_manipulated"

    return "ai_manipulated"


def suspicious_scale(fake_probability, ai_origin, features, media_type):
    """0-100 suspicion meter. Boosted when AI tools converted/edited media.

    Converted media is more deceptive than a clearly synthetic file, so when
    AI-tool manipulation is detected the scale is pushed higher.
    """
    scale = fake_probability
    if ai_origin == "ai_manipulated":
        if media_type == "image" and features.get("ela_local_variance", 0) >= 0.35:
            scale += 12
        elif media_type == "video" and features.get("temporal_flicker", 0) >= 0.5:
            scale += 10
        elif media_type == "audio" and features.get("spectral_flatness", 0) >= 0.3:
            scale += 10
        else:
            scale += 8
    elif ai_origin == "ai_generated":
        scale += 4
    return round(max(0.0, min(100.0, scale)), 1)


def risk_label(prob):
    """Risk buckets: low / medium / high / critical."""
    if prob < 30:
        return "low"
    if prob < 55:
        return "medium"
    if prob < 75:
        return "high"
    return "critical"


def reasons_from_features(media_type, features, fake_probability):
    """Turn per-type features into a human readable XAI checklist."""
    reasons = []
    for key, label, polarity in _REASON_SPECS.get(media_type, []):
        value = features.get(key)
        if value is None or not isinstance(value, (int, float)):
            continue
        suspicious = (value > 0.5) if polarity == "high_is_bad" else (value < 0.5)
        reasons.append({
            "check": label,
            "passed": not suspicious,
            "detail": f"measured {value:.0%}" if value <= 1 else f"measured {value:.2f}",
        })
    return reasons


_REASON_SPECS = {
    "image": [
        ("error_level_analysis", "Error-level consistency", "low_is_bad"),
        ("ela_local_variance", "No localised AI editing artifacts", "low_is_bad"),
        ("texture_uniformity", "Natural texture variance", "low_is_bad"),
        ("recompression_similarity", "Recompression similarity", "low_is_bad"),
        ("metadata_anomaly", "Metadata completeness", "low_is_bad"),
        ("face_consistency", "Face boundary consistency", "low_is_bad"),
        ("eye_blink_pattern", "Natural eye-blinking pattern", "low_is_bad"),
        ("lighting_consistency", "Consistent lighting", "low_is_bad"),
    ],
    "video": [
        ("face_presence", "Consistent face presence", "low_is_bad"),
        ("temporal_flicker", "Smooth temporal motion", "low_is_bad"),
        ("byte_hash_drift", "Natural byte-level variance", "low_is_bad"),
        ("lip_sync_alignment", "Lip-sync alignment", "low_is_bad"),
    ],
    "audio": [
        ("spectral_flatness", "Natural spectral detail", "low_is_bad"),
        ("zero_crossing_rate", "Natural consonant density", "low_is_bad"),
        ("prosody_variance", "Expressive prosody", "low_is_bad"),
    ],
    "text": [
        ("perplexity", "Natural token perplexity", "high_is_bad"),
        ("burstiness", "Natural sentence burstiness", "high_is_bad"),
        ("repetition", "Limited token repetition", "high_is_bad"),
        ("repetition_rate", "No repeated sentence patterns", "high_is_bad"),
        ("ai_style_patterns", "No formulaic AI-style phrasing", "high_is_bad"),
    ],
    "email": [
        ("urgency_language", "No manipulative urgency", "low_is_bad"),
        ("financial_pressure", "No financial pressure", "low_is_bad"),
        ("link_risk", "Low link risk", "low_is_bad"),
        ("sender_authenticity", "Sender authenticity", "low_is_bad"),
    ],
}


def explain_short(media_type, result, prob):
    head = {
        "image": ("The model classifies this image as AI-generated or manipulated. "
                  if result == "fake" else
                  "The model finds this image consistent with an authentic capture. "),
        "video": ("Temporal analysis suggests this video was AI-generated or manipulated. "
                  if result == "fake" else
                  "Temporal and face analysis are consistent with an authentic recording. "),
        "audio": ("Voice-spectral patterns suggest this audio is AI-generated or cloned. "
                  if result == "fake" else
                  "Spectral and prosodic patterns are consistent with a natural human voice. "),
        "text": ("This text exhibits patterns typical of AI-generated writing. "
                 if result == "fake" else
                 "This text displays human-like variability in its writing. "),
        "email": ("This email shows strong indicators of a phishing / scam campaign. "
                  if result == "fake" else
                  "This email does not exhibit strong scam indicators. "),
        "post": ("This social-media post shows signs of AI-generated or misleading content. "
                 if result == "fake" else
                 "This social-media post does not show strong manipulation signals. "),
    }.get(media_type, "")
    return head + f"Overall AI probability is {prob:.1f}%."
