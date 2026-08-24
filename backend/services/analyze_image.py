"""Image deepfake analysis using heuristic signals.

Runs Error Level Analysis, color stats, metadata forensics, and face/eye/
lighting checks (OpenCV when available), then the ensemble + trust score +
XAI reasons + heatmap. No model weights needed.
"""
import hashlib
import io
import os
import time

from PIL import Image, ImageChops, ImageStat
from PIL.ExifTags import TAGS

from config import Config
from services.ensemble import (build_models, classify_ai_origin, explain_short,
                               reasons_from_features, risk_label, suspicious_scale,
                               trust_score)


def _average_hash(image, hash_size=16):
    """pHash-style signature used to compare compressed artifacts."""
    img = image.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return int(bits, 2)


def _error_level_analysis(image, quality=90):
    """Compare original vs re-saved JPEG to locate compression artifacts."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(image.convert("RGB"), recompressed)
    stat = ImageStat.Stat(diff)
    rms = sum(stat.mean) / 3.0
    return rms, diff


def _save_heatmap(diff, seed_hex):
    """Persist a heatmap PNG (red = manipulated regions) and return its name."""
    try:
        import numpy as np
        gray = np.asarray(diff.convert("L"), dtype=np.float32)
        spread = gray.ptp()
        norm = (gray - gray.min()) / spread if spread > 1e-6 else np.zeros_like(gray)
        heat = np.zeros((norm.shape[0], norm.shape[1], 3), dtype=np.uint8)
        heat[:, :, 0] = (norm * 255).astype(np.uint8)       # red channel
        heat[:, :, 1] = ((1 - norm) * 120).astype(np.uint8)  # muted green
        from PIL import Image as _Img
        os.makedirs(Config.HEATMAP_FOLDER, exist_ok=True)
        name = f"heat_{seed_hex[:10]}.png"
        _Img.fromarray(heat).save(os.path.join(Config.HEATMAP_FOLDER, name))
        return name
    except Exception:
        return ""


def _face_analysis(path):
    """OpenCV Haar-cascade face/eye/lighting heuristics. Best-effort."""
    out = {
        "faces_detected": 0,
        "face_consistency": 0.5,
        "eye_blink_pattern": 0.5,
        "lighting_consistency": 0.5,
        "face_areas": [],
    }
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return out
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml")
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        out["faces_detected"] = int(len(faces))
        if len(faces) == 0:
            return out

        eyes_total = 0
        lighting_diffs = []
        for (x, y, w, h) in faces[:4]:
            face_gray = gray[y:y + h, x:x + w]
            eyes = eye_cascade.detectMultiScale(face_gray, 1.1, 5, minSize=(8, 8))
            eyes_total += len(eyes)
            # Lighting consistency: compare left vs right half of the face.
            mid = w // 2
            left = float(face_gray[:, :mid].mean())
            right = float(face_gray[:, mid:].mean())
            lighting_diffs.append(abs(left - right) / 128.0)
            out["face_areas"].append({"x": int(x), "y": int(y), "w": int(w), "h": int(h),
                                      "eyes": int(len(eyes))})

        expected_eyes = min(len(faces) * 2, 8)
        eye_ratio = min(1.0, eyes_total / max(1, expected_eyes))
        out["eye_blink_pattern"] = round(min(1.0, max(0.0, eye_ratio)), 4)
        light = sum(lighting_diffs) / len(lighting_diffs)
        out["lighting_consistency"] = round(min(1.0, max(0.0, 1.0 - light)), 4)
        # A generated face often has 0 eyes detected (uncanny gaps).
        if eyes_total == 0:
            out["face_consistency"] = 0.2
        else:
            out["face_consistency"] = round(min(1.0, 0.5 + eye_ratio * 0.5), 4)
    except Exception:
        pass
    return out


def _extract_metadata(path):
    """Collect EXIF/IPTC metadata for forensic checks."""
    meta = {}
    try:
        img = Image.open(path)
        meta.update({"format": img.format, "mode": img.mode,
                     "width": img.width, "height": img.height,
                     "size_bytes": os.path.getsize(path)})
        exif = img.getexif()
        for tag_id, value in exif.items():
            name = TAGS.get(tag_id, str(tag_id))
            meta[name] = str(value)[:120]
        meta["has_exif"] = bool(exif)
    except Exception:
        meta = {"error": "unable to read metadata"}
    return meta


def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def feature_vector(image):
    """Compute the shared numeric feature dict from an RGB PIL image.

    Used both by ``analyze_image`` and by the Kaggle reference scorer, so a
    scanned frame and a Kaggle sample are measured identically. Returns the
    features that need no file metadata (face/EXIF checks are applied on top
    by the full pipeline).
    """
    # hash of a heavily re-compressed copy => similarity score
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=50)
    buf.seek(0)
    h_original = _average_hash(image)
    h_recomp = _average_hash(Image.open(buf).convert("RGB"))
    similarity = 1.0 - bin(h_original ^ h_recomp).count("1") / (16 * 16)

    stat = ImageStat.Stat(image)
    mean_rgb = stat.mean
    stddev = sum(stat.stddev) / 3.0

    ela_rms, _diff = _error_level_analysis(image)
    return {
        "error_level_analysis": round(max(0.0, min(1.0, ela_rms / 14.0)), 4),
        "texture_uniformity": round(max(0.0, min(1.0, (1.0 - stddev / 70.0))), 4),
        "recompression_similarity": round(max(0.0, min(1.0, (similarity - 0.6) / 0.4)), 4),
        "color_flatness": round(max(0.0, min(1.0, (120.0 - (sum(mean_rgb) / 3.0)) / 120.0)), 4),
        "histogram_entropy": round(_entropy(image.histogram()), 3),
    }


def analyze_image(file_path, filename, size_bytes):
    """Run the full image pipeline. Returns a prediction result dict."""
    start = time.time()

    with Image.open(file_path) as img:
        try:
            img.verify()
            img = Image.open(file_path).convert("RGB")
        except Exception:
            return _pack_failure("Unsupported or corrupted image file.")

        _ela_rms, diff = _error_level_analysis(img)
        # Spatial variance of the ELA difference map: high values mean the
        # recompression error is concentrated in patches -> localised AI edits
        # (face-swap, inpainting, enhancement) rather than a uniform synthetic source.
        try:
            import numpy as np
            diff_arr = np.asarray(diff.convert("L"), dtype=np.float32)
            ela_local_variance = float(min(1.0, diff_arr.std() / 30.0))
        except Exception:  # noqa: BLE001
            ela_local_variance = 0.0
        shared = feature_vector(img)

    meta = _extract_metadata(file_path)
    file_hash = _sha256(file_path)
    seed_hex = file_hash or hashlib.sha256(open(file_path, "rb").read()[:65536]).hexdigest()
    heatmap_name = _save_heatmap(diff, seed_hex)
    face = _face_analysis(file_path)

    # -------------------------- heuristic scoring -------------------------- #
    # High localised recompression error points to tampering.
    ela_score = shared["error_level_analysis"]
    # Generated faces tend to be overly smooth and uniform.
    texture_score = shared["texture_uniformity"]
    # Missing or stripped metadata is mildly suspicious.
    meta_score = 0.0 if meta.get("has_exif") else 0.35
    # Being too similar after lossy recompression suggests a synthetic source.
    recomp_score = shared["recompression_similarity"]
    # Low color variance reads flat / uncanny.
    flatness = shared["color_flatness"]
    # Face heuristics only apply when a face is present.
    if face["faces_detected"]:
        face_score = (1.0 - face["face_consistency"]) * 0.6 + (1.0 - face["eye_blink_pattern"]) * 0.4
        lighting_score = 1.0 - face["lighting_consistency"]
        face_weight = 0.12
    else:
        face_score = 0.0
        lighting_score = 0.0
        face_weight = 0.0

    features = {
        "error_level_analysis": round(ela_score, 4),
        "ela_local_variance": round(ela_local_variance, 4),
        "texture_uniformity": round(texture_score, 4),
        "metadata_anomaly": round(meta_score, 4),
        "recompression_similarity": round(recomp_score, 4),
        "color_flatness": round(flatness, 4),
        "histogram_entropy": round(shared["histogram_entropy"], 3),
        "face_consistency": round(face["face_consistency"], 4),
        "eye_blink_pattern": round(face["eye_blink_pattern"], 4),
        "lighting_consistency": round(face["lighting_consistency"], 4),
        "faces_detected": face["faces_detected"],
        "resolution": f"{img.width}x{img.height}",
    }

    base = (
        0.28 * ela_score
        + 0.20 * texture_score
        + 0.16 * recomp_score
        + 0.14 * meta_score
        + 0.14 * flatness
        + 0.08 * face_score
    )
    base = max(0.0, min(1.0, base + (lighting_score * 0.03 if face_weight else 0.0)))

    # ----------------------- Kaggle reference blend ------------------------ #
    # Blend with the Kaggle reference profile when it agrees with the
    # heuristic verdict - boosts confidence.
    kaggle_info = None
    try:
        from services.kaggle_reference import kaggle_reference
        kaggle_reference.ensure_built()
        kaggle_info = kaggle_reference.score(shared)
        if kaggle_info and kaggle_info.get("status") == "ready":
            ref_likelihood = kaggle_info["fake_likelihood"]
            base = max(0.0, min(1.0, 0.75 * base + 0.25 * ref_likelihood))
    except Exception:  # noqa: BLE001
        kaggle_info = None

    # ------------------------- trained CNN signal -------------------------- #
    # When a model has been trained (ml/train_cnn_kaggle.py) and deployed,
    # blend its real fake-probability into the base and let the ensemble's
    # "CNN" slot vote with the actual network output instead of a heuristic.
    cnn_info = None
    cnn_fake_pct = None
    try:
        from services.cnn_detector import cnn_detector
        if cnn_detector.available():
            cnn_info = cnn_detector.predict(file_path)
            if cnn_info and cnn_info.get("fake_probability") is not None:
                cnn_fake_pct = cnn_info["fake_probability"] * 100.0
                base = max(0.0, min(1.0,
                                    (1.0 - Config.IMAGE_CNN_WEIGHT) * base
                                    + Config.IMAGE_CNN_WEIGHT * cnn_info["fake_probability"]))
                features["cnn_ai_probability"] = round(cnn_info["fake_probability"], 4)
    except Exception:  # noqa: BLE001
        cnn_info = None

    real_scores = {"CNN (EfficientNet)": cnn_fake_pct} if cnn_fake_pct is not None else None
    models, fake_probability = build_models("image", base * 100, filename, spread=4.0,
                                            real_scores=real_scores)
    result, _risk = _interpret(fake_probability)
    risk = risk_label(fake_probability)
    ai_origin = classify_ai_origin("image", features, fake_probability)
    susp = suspicious_scale(fake_probability, ai_origin, features, "image")
    reasons = reasons_from_features("image", features, fake_probability)
    if cnn_fake_pct is not None:
        reasons.insert(0, {
            "check": "Trained CNN (EfficientNet) forensic signal",
            "passed": cnn_fake_pct < 50.0,
            "detail": f"CNN fake probability {cnn_fake_pct:.1f}%",
        })
    factors = {
        "metadata": 1.0 - meta_score,
        "ai_artifacts": 1.0 - ela_score,
        "compression": 1.0 - recomp_score,
        "face_consistency": face["face_consistency"],
        "noise": 1.0 - texture_score,
    }
    trust = trust_score(fake_probability, factors)
    explanation = explain_short("image", result, fake_probability)
    if ai_origin == "ai_manipulated":
        explanation += (" The file appears to have been converted or edited using AI tools "
                        "(localised artifacts detected), which raises the suspicion scale.")
    elif ai_origin == "ai_generated":
        explanation += " The content shows hallmarks of being generated entirely by AI."
    recommendations = _recommendations(result)

    elapsed = int((time.time() - start) * 1000)
    return {
        "scan_type": "image",
        "filename": filename,
        "result": result,
        "confidence": 100.0 - abs(fake_probability - (100 if result == "fake" else 0)),
        "suspicious_scale": susp,
        "ai_origin": ai_origin,
        "ai_generated": ai_origin == "ai_generated",
        "ai_manipulated": ai_origin == "ai_manipulated",
        "fake_probability": round(fake_probability, 1),
        "trust_score": trust,
        "risk_level": risk,
        "explanation": explanation,
        "recommendations": recommendations,
        "processing_time_ms": elapsed,
        "metadata": {**{k: v for k, v in list(meta.items())[:25]},
                     "file_hash_sha256": file_hash},
        "features": features,
        "models": models,
        "reasons": reasons,
        "file_hash": file_hash,
        "face_analysis": face,
        "heatmap_file": heatmap_name,
        "model": "efficientnet-cnn-v1" if cnn_fake_pct is not None else "heuristic-vision-v1",
        "heatmap_available": True,
        "kaggle_reference": kaggle_info,
        "cnn_model": cnn_info,
        "verified": False,
    }


def _entropy(counts):
    import math
    total = sum(counts)
    if total == 0:
        return 0.0
    e = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            e -= p * math.log(p, 2)
    return round(e, 3)


def _interpret(prob):
    if prob >= 65:
        return "fake", "high"
    if prob >= 45:
        return "inconclusive", "medium"
    return "authentic", "low"


def _recommendations(result):
    common = ["Run reverse image search on Google / TinEye",
              "Compare against known original sources",
              "Verify the account / channel that posted the media",
              "Request the original unedited file from the uploader"]
    if result == "fake":
        return "\n".join(["Do not share the media without verification.",
                          "Report the media to the platform / law enforcement.",
                          "Preserve the file and this report as evidence."] + common[:3])
    return "\n".join(common)


def _pack_failure(reason):
    return {"error": reason}
