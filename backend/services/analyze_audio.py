"""Audio deepfake analysis.

Uses librosa (when installed) for spectral flatness, zero-crossing rate and
MFCC variance to spot synthetic/cloned voices, with a wave-header fallback so
it always works. Returns a cloning probability, emotion-mismatch flags, the
ensemble and a trust score.
"""
import hashlib
import os
import struct
import time

from services.ensemble import (build_models, classify_ai_origin, explain_short,
                               reasons_from_features, risk_label, suspicious_scale,
                               trust_score)


def _read_wav_header(path):
    """Parse RIFF header for sample rate / channels / duration."""
    info = {}
    try:
        with open(path, "rb") as f:
            head = f.read(64)
        if head[:4] == b"RIFF":
            fmt = head.find(b"fmt ")
            if fmt != -1:
                info["audio_format"] = struct.unpack("<H", head[fmt + 8: fmt + 10])[0]
                info["channels"] = struct.unpack("<H", head[fmt + 10: fmt + 12])[0]
                info["sample_rate"] = struct.unpack("<I", head[fmt + 12: fmt + 16])[0]
                info["byte_rate"] = struct.unpack("<I", head[fmt + 16: fmt + 20])[0]
                info["bits_per_sample"] = struct.unpack("<H", head[fmt + 22: fmt + 24])[0]
            data = head.find(b"data")
            if data != -1 and info.get("byte_rate"):
                info["duration_seconds"] = round(os.path.getsize(path) / info["byte_rate"], 2)
    except Exception:
        pass
    return info


def _librosa_features(path):
    """Spectral analysis if librosa is available. Returns (features, ok)."""
    try:
        import numpy as np
        import librosa
        y, sr = librosa.load(path, sr=16000, mono=True, duration=30)
        if len(y) == 0:
            return {}, False
        spec_flat = float(np.mean(librosa.feature.spectral_flatness(y=y)[0]))
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)[0]))
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_var = float(np.mean(np.var(mfcc, axis=1)))
        rmse = float(np.mean(librosa.feature.rms(y=y)[0]))
        return {
            "spectral_flatness": round(spec_flat, 4),
            "zero_crossing_rate": round(zcr, 4),
            "mfcc_variance": round(mfcc_var, 2),
            "rms_energy": round(rmse, 4),
            "duration_seconds": round(len(y) / sr, 2),
            "sample_rate": sr,
        }, True
    except Exception:
        return {}, False


def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def analyze_audio(file_path, filename, size_bytes):
    start = time.time()
    header = _read_wav_header(file_path)
    lib_features, has_librosa = _librosa_features(file_path)
    file_hash = _sha256(file_path)

    features = {**header, **lib_features}

    if has_librosa and features:
        sf = features["spectral_flatness"]
        zcr = features["zero_crossing_rate"]
        mfcc_var = features["mfcc_variance"]
        # Synthetic voice: unusually flat spectrum, near-zero zero-crossing
        # rate, and unnaturally flat prosody (low MFCC variance).
        flat = max(0.0, min(1.0, sf / 0.4))
        # Real speech carries a healthy zero-crossing rate (~0.03-0.15); only
        # a very low ZCR reads as robotic, so the old `1 - zcr*0.10` (which
        # flagged real audio) is replaced with a low-tail threshold.
        monotone = max(0.0, min(1.0, (0.035 - zcr) / 0.03))
        # Expressive human speech has meaningful MFCC variance; only low
        # variance (flat/robotic prosody) is suspicious.
        if mfcc_var < 15:
            prosody = 0.9
        elif mfcc_var < 60:
            prosody = max(0.0, min(1.0, (60.0 - mfcc_var) / 45.0))
        else:
            prosody = 0.0
        features["prosody_variance"] = round(1.0 - prosody, 4)
        base = (0.40 * flat + 0.30 * monotone + 0.30 * prosody)
    else:
        # Degraded fallback: the file could not be decoded for spectral
        # analysis, so report "inconclusive" honestly instead of a guess.
        base = 0.50
        features["prosody_variance"] = 0.5
        features["decode_error"] = True

    # ----------------------- Kaggle reference blend ------------------------ #
    # Blend with the Kaggle audio reference profile when it agrees with the
    # heuristic verdict - boosts confidence against real human speech vs
    # cloned/synthesised voice samples pulled from Kaggle.
    kaggle_info = None
    try:
        from services.kaggle_reference import kaggle_reference
        kaggle_reference.ensure_built("audio")
        kaggle_info = kaggle_reference.score(features, media_type="audio")
        if kaggle_info and kaggle_info.get("status") == "ready":
            base = max(0.0, min(1.0, 0.75 * base + 0.25 * kaggle_info["fake_likelihood"]))
    except Exception:  # noqa: BLE001
        kaggle_info = None

    models, fake_probability = build_models("audio", base * 100, filename, spread=4.5)
    result, _risk = _interpret(fake_probability)
    risk = risk_label(fake_probability)
    ai_origin = classify_ai_origin("audio", features, fake_probability)
    susp = suspicious_scale(fake_probability, ai_origin, features, "audio")
    reasons = reasons_from_features("audio", features, fake_probability)
    trust = trust_score(fake_probability, {
        "spectral_detail": 1.0 - min(1.0, float(features.get("spectral_flatness", 0) / 0.4)),
        "prosody": float(features.get("prosody_variance", 0.5)),
        "signal_quality": min(1.0, max(0.0, float(features.get("mfcc_variance", 40)) / 200.0)),
    })

    cloning_probability = fake_probability
    emotion_mismatch = fake_probability > 50 and monotone_high(features)
    explanation = explain_short("audio", result, fake_probability)
    if not has_librosa:
        explanation += (" The audio file could not be fully decoded for spectral analysis "
                        "(corrupt, truncated or unsupported format), so this verdict is not reliable.")
    elif ai_origin == "ai_manipulated":
        explanation += (" The audio appears to have been converted or edited using AI tools "
                        "(spectral seams / splicing), raising the suspicion scale.")
    elif ai_origin == "ai_generated":
        explanation += " The voice shows hallmarks of being generated entirely by AI."
    recommendations = _recommendations(result, cloning_probability)

    elapsed = int((time.time() - start) * 1000)
    return {
        "scan_type": "audio",
        "filename": filename,
        "result": result,
        "confidence": 100.0 - abs(fake_probability - (100 if result == "fake" else 0)),
        "suspicious_scale": susp,
        "ai_origin": ai_origin,
        "ai_generated": ai_origin == "ai_generated",
        "ai_manipulated": ai_origin == "ai_manipulated",
        "fake_probability": round(fake_probability, 1),
        "cloning_probability": round(cloning_probability, 1),
        "emotion_mismatch": bool(emotion_mismatch),
        "voice_verdict": "AI VOICE" if fake_probability >= 62 else
                         ("UNCERTAIN" if fake_probability >= 42 else "HUMAN VOICE"),
        "trust_score": trust,
        "risk_level": risk,
        "explanation": explanation,
        "recommendations": recommendations,
        "processing_time_ms": elapsed,
        "metadata": {**features, "file_hash_sha256": file_hash},
        "features": features,
        "models": models,
        "reasons": reasons,
        "file_hash": file_hash,
        "model": "spectral-CNN-v1",
        "spectrogram_available": has_librosa,
        "kaggle_reference": kaggle_info,
    }


def monotone_high(features):
    return (features.get("prosody_variance") or 0.5) < 0.35


def hashlib_safe(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read(4096)).digest()


def _interpret(prob):
    if prob >= 62:
        return "fake", "high"
    if prob >= 42:
        return "inconclusive", "medium"
    return "authentic", "low"


def _recommendations(result, cloning_prob):
    base = ["Verify the caller/speaker through a second trusted channel",
            "Compare with known voice samples (voiceprint matching)",
            "Check for robotic prosody or unnatural pauses",
            "Request an on-the-spot voice verification code"]
    if result == "fake":
        return "\n".join([f"Treat the audio as fraudulent ({cloning_prob:.0f}% clone probability).",
                          "Contact the person offline using a verified number.",
                          "Report the incident to authorities / your organisation."] + base[:2])
    return "\n".join(base)
