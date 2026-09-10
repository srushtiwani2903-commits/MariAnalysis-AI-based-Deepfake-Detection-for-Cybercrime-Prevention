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


def _multi_quality_ela(image):
    """Run ELA at multiple JPEG quality levels and return composite metrics.

    AI-generated images tend to compress very uniformly across quality levels,
    while real photos show more variance. This catches images that slip through
    a single-quality ELA check.
    """
    results = {}
    for q in [75, 85, 95]:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=q)
        buf.seek(0)
        recompressed = Image.open(buf).convert("RGB")
        diff = ImageChops.difference(image.convert("RGB"), recompressed)
        stat = ImageStat.Stat(diff)
        rms = sum(stat.mean) / 3.0
        results[q] = rms

    # If ELA is suspiciously similar across all quality levels, it's likely synthetic
    rms_values = list(results.values())
    mean_rms = sum(rms_values) / len(rms_values)
    variance = sum((r - mean_rms) ** 2 for r in rms_values) / len(rms_values)

    # Low variance across quality levels = synthetic source
    quality_consistency = max(0.0, min(1.0, 1.0 - (variance ** 0.5) / 5.0))

    return mean_rms, quality_consistency, results


def _frequency_analysis(image):
    """Detect GAN/diffusion model artifacts via FFT spectral analysis.

    AI-generated images often show characteristic periodic patterns in the
    frequency domain — specific frequency bands are unnaturally suppressed
    or amplified, and the spectral envelope lacks the natural falloff of
    camera-captured images.
    """
    try:
        import numpy as np

        # Convert to grayscale numpy array
        gray = np.asarray(image.convert("L"), dtype=np.float64)

        # Apply 2D FFT
        f_transform = np.fft.fft2(gray)
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.abs(f_shift)

        h, w = magnitude.shape
        cy, cx = h // 2, w // 2

        # Create radial distance map from center
        y, x = np.ogrid[:h, :w]
        r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        max_r = min(cy, cx)

        # Compute radial power spectrum (average magnitude per ring)
        rings = 20
        radial_power = []
        for i in range(rings):
            inner = (i / rings) * max_r
            outer = ((i + 1) / rings) * max_r
            mask = (r >= inner) & (r < outer)
            if mask.any():
                radial_power.append(float(np.mean(magnitude[mask])))
            else:
                radial_power.append(0.0)

        total_power = sum(radial_power)
        if total_power < 1e-10:
            return {"spectral_anomaly": 0.5, "high_freq_ratio": 0.5,
                    "spectral_peaks": 0, "radial_entropy": 0.5}

        # Normalize
        radial_norm = [p / total_power for p in radial_power]

        # High-frequency ratio: real images have more high-freq content
        high_freq_end = rings // 2
        high_freq_ratio = sum(radial_norm[high_freq_end:]) / max(1e-10, sum(radial_norm))

        # Spectral peaks: AI images may have periodic artifacts (sharp spikes)
        mean_power = sum(radial_norm) / len(radial_norm)
        peaks = sum(1 for p in radial_norm if p > mean_power * 2.5)

        # Radial entropy: real images have higher entropy in radial spectrum
        import math
        radial_entropy = -sum(
            p * math.log(p + 1e-10, 2) for p in radial_norm if p > 0
        ) / math.log(rings, 2) if any(p > 0 for p in radial_norm) else 0

        # AI-generated images typically have:
        # - Missing high-frequency content (too smooth, plastic-like)
        # - A steeper spectral slope (unnatural power falloff)
        # - Periodic artifacts (GAN checkerboard)
        # Use STRICT thresholds to avoid false positives on real photos,
        # which also have low high-freq content after compression but DO
        # retain a natural textured pattern in the mid frequencies.
        anomaly_score = 0.0
        if high_freq_ratio < 0.15:
            anomaly_score += 0.35  # extremely smooth (rare in real photos)
        elif high_freq_ratio < 0.22:
            anomaly_score += 0.15  # mild lack of detail (only counts if other signals agree)
        if peaks >= 5:
            anomaly_score += 0.35  # strong periodic artifacts
        elif peaks >= 3:
            anomaly_score += 0.15  # mild periodicity
        mid_energy = sum(radial_norm[5:10])
        low_energy = sum(radial_norm[0:3])
        if low_energy > 0 and mid_energy / low_energy > 0.35:
            anomaly_score += 0.20  # unnatural mid-freq spike

        # Radial entropy: real images have higher entropy in the radial spectrum.
        # Only counts as anomaly when it is VERY low (very uniform energy shape).
        if radial_entropy < 0.55:
            anomaly_score += 0.20

        anomaly_score = max(0.0, min(1.0, anomaly_score))

        return {
            "spectral_anomaly": round(anomaly_score, 4),
            "high_freq_ratio": round(max(0.0, min(1.0, high_freq_ratio)), 4),
            "spectral_peaks": peaks,
            "radial_entropy": round(max(0.0, min(1.0, radial_entropy)), 4),
        }
    except Exception:
        return {"spectral_anomaly": 0.0, "high_freq_ratio": 0.5,
                "spectral_peaks": 0, "radial_entropy": 0.5}


def _noise_pattern_analysis(image):
    """Analyze noise patterns to detect AI-generated content.

    Real camera images have sensor noise that follows a characteristic pattern
    (slightly higher in blue channel, spatially correlated near edges).
    AI-generated images have either no noise or artificially uniform noise
    that lacks these natural patterns.
    """
    try:
        import numpy as np

        arr = np.asarray(image, dtype=np.float64)

        # Estimate noise by subtracting a median-filtered version
        from PIL import ImageFilter
        smoothed = image.filter(ImageFilter.MedianFilter(3))
        smooth_arr = np.asarray(smoothed, dtype=np.float64)
        noise = arr - smooth_arr

        # Noise level per channel
        noise_std = [float(np.std(noise[:, :, c])) for c in range(3)]

        # Channel variance: real cameras have slightly more noise in blue
        # AI generators tend to have equal noise across channels
        ch_mean = sum(noise_std) / 3.0
        ch_variance = sum((n - ch_mean) ** 2 for n in noise_std) / 3.0
        channel_uniformity = 1.0 - min(1.0, (ch_variance ** 0.5) / 5.0)

        # Spatial correlation: real noise is spatially correlated (not pure white noise)
        # Compute autocorrelation at lag 1 for each channel
        autocorr_vals = []
        for c in range(3):
            n = noise[:, :, c].flatten()
            if len(n) > 1:
                corr = float(np.corrcoef(n[:-1], n[1:])[0, 1])
                autocorr_vals.append(abs(corr))
        spatial_correlation = sum(autocorr_vals) / max(1, len(autocorr_vals))

        # AI images: uniform noise across channels + low spatial correlation.
        # STRICT thresholds: compressed real photos also have low noise, so
        # only flag when the noise signature is unmistakably synthetic.
        noise_anomaly = 0.0
        if channel_uniformity > 0.93:
            noise_anomaly += 0.4  # noise identical across all channels (rare in real)
        if spatial_correlation < 0.05:
            noise_anomaly += 0.3  # pure white noise (no sensor correlation)
        if ch_mean < 0.5:
            noise_anomaly += 0.3  # essentially NO noise whatsoever

        noise_anomaly = max(0.0, min(1.0, noise_anomaly))

        return {
            "noise_anomaly": round(noise_anomaly, 4),
            "noise_level": round(ch_mean, 2),
            "noise_uniformity": round(channel_uniformity, 4),
            "noise_spatial_corr": round(spatial_correlation, 4),
        }
    except Exception:
        return {"noise_anomaly": 0.0, "noise_level": 5.0,
                "noise_uniformity": 0.5, "noise_spatial_corr": 0.3}


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

        # Check for AI generator software tags in metadata
        AI_GENERATORS = [
            "stable diffusion", "midjourney", "dall-e", "dalle", "craiyon",
            "nightcafe", "deepai", "artbreeder", "thispersondoesnotexist",
            "generated", "synthetic", "ai ", "dreamstudio", "leonardo.ai",
            "flux", "sdxl", "comfyui", "automatic1111", "a1111", "invoke",
            "fooocus", "sd ", "kandinsky", "ideogram", "playground",
        ]
        meta_str = " ".join(str(v).lower() for v in meta.values())
        detected_ai_tools = [tool for tool in AI_GENERATORS if tool in meta_str]
        meta["ai_generator_detected"] = detected_ai_tools
        meta["has_ai_generator_tag"] = bool(detected_ai_tools)

        # Check for typical camera metadata
        CAMERA_TAGS = ["Make", "Model", "DateTime", "DateTimeOriginal",
                       "Software", "LensModel", "FocalLength", "ISOSpeedRatings",
                       "ExposureTime", "FNumber"]
        has_camera_meta = any(tag in meta for tag in CAMERA_TAGS)
        meta["has_camera_metadata"] = has_camera_meta

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
    # AI generator software tags in metadata are strong indicators.
    if meta.get("has_ai_generator_tag"):
        meta_score = max(meta_score, 0.85)
    # Being too similar after lossy recompression suggests a synthetic source.
    recomp_score = shared["recompression_similarity"]
    # Low color variance reads flat / uncanny.
    flatness = shared["color_flatness"]

    # Run advanced analyses
    _mq_ela_rms, quality_consistency, _mq_results = _multi_quality_ela(img)
    spectral = _frequency_analysis(img)
    noise = _noise_pattern_analysis(img)

    # Face heuristics only apply when a face is present.
    if face["faces_detected"]:
        face_score = (1.0 - face["face_consistency"]) * 0.6 + (1.0 - face["eye_blink_pattern"]) * 0.4
        lighting_score = 1.0 - face["lighting_consistency"]
        face_weight = 0.12
    else:
        face_score = 0.0
        lighting_score = 0.0
        face_weight = 0.0

    # Composite advanced scores
    spectral_score = spectral["spectral_anomaly"]
    noise_score = noise["noise_anomaly"]

    features = {
        "error_level_analysis": round(ela_score, 4),
        "ela_local_variance": round(ela_local_variance, 4),
        "ela_quality_consistency": round(quality_consistency, 4),
        "texture_uniformity": round(texture_score, 4),
        "metadata_anomaly": round(meta_score, 4),
        "recompression_similarity": round(recomp_score, 4),
        "color_flatness": round(flatness, 4),
        "histogram_entropy": round(shared["histogram_entropy"], 3),
        "spectral_anomaly": round(spectral_score, 4),
        "high_freq_ratio": round(spectral["high_freq_ratio"], 4),
        "spectral_peaks": spectral["spectral_peaks"],
        "noise_anomaly": round(noise_score, 4),
        "noise_level": round(noise["noise_level"], 2),
        "noise_uniformity": round(noise["noise_uniformity"], 4),
        "face_consistency": round(face["face_consistency"], 4),
        "eye_blink_pattern": round(face["eye_blink_pattern"], 4),
        "lighting_consistency": round(face["lighting_consistency"], 4),
        "faces_detected": face["faces_detected"],
        "resolution": f"{img.width}x{img.height}",
    }

    # UPDATED: Balanced weight distribution for AI-generated detection
    # Spectral/noise signals get moderate weight. Real camera photos with
    # EXIF metadata are DAMPENED so they don't false-positive.
    is_real_camera = bool(meta.get("has_camera_metadata")) and bool(meta.get("has_exif"))
    if is_real_camera:
        # Real camera photo: spectral/noise signals are unreliable.
        # Real camera images often lack high-freq detail after compression.
        spectral_effective = spectral_score * 0.35
        noise_effective = noise_score * 0.30
    else:
        spectral_effective = spectral_score
        noise_effective = noise_score

    base = (
        0.16 * ela_score           # ELA - catches manipulation (high ELA)
        + 0.18 * texture_score     # Smooth textures = synthetic (most reliable)
        + 0.13 * recomp_score      # Too-clean recompression
        + 0.10 * meta_score        # Missing EXIF / AI tags
        + 0.06 * flatness          # Color flatness
        + 0.05 * face_score        # Face heuristics
        + 0.17 * spectral_effective  # frequency domain artifacts
        + 0.11 * noise_effective     # unnatural noise patterns
    )
    base = max(0.0, min(1.0, base + (lighting_score * 0.03 if face_weight else 0.0)))

    # ---------------------- AI signal agreement bonus ----------------------- #
    # Only trigger when STRONG signals agree. A compressed real photo will
    # have low ELA but will NOT trigger spectral/noise/texture simultaneously,
    # so it won't get the boost.
    ai_signals = 0
    if spectral_score >= 0.5 and not is_real_camera:
        ai_signals += 1
    if noise_score >= 0.5 and not is_real_camera:
        ai_signals += 1
    if texture_score >= 0.75:
        ai_signals += 1
    if recomp_score >= 0.80:
        ai_signals += 1
    if ela_score <= 0.08:
        ai_signals += 1
    if meta.get("has_ai_generator_tag"):
        ai_signals += 2  # Strong signal

    # Boost only when 4+ signals agree (genuine AI output)
    if ai_signals >= 5:
        base = min(1.0, base + 0.18)  # Very strong boost
    elif ai_signals >= 4:
        base = min(1.0, base + 0.10)  # Strong boost

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
    if prob >= 60:
        return "fake", "high"
    if prob >= 42:
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
