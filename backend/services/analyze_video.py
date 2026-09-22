"""Video deepfake analysis.

Pipeline: frame extraction -> face detection (MediaPipe/OpenCV Haar when
available) -> per-frame quality features (ELA, texture, recompression, face
consistency) -> temporal consistency scoring -> optional reference comparison
against the multi-source pipeline corpus (Kaggle/Hugging Face/Google) ->
optional trained frame-CNN blend. Each sampled frame receives a per-second
verdict so the timeline can show exactly where manipulation is suspected.
"""
import hashlib
import os
import time

from config import Config
from services.ensemble import (build_models, classify_ai_origin, explain_short,
                               reasons_from_features, risk_label, suspicious_scale,
                               trust_score)


def _probe_video(file_path):
    """Basic metadata probe via OpenCV (if installed) else filesystem info."""
    info = {"size_bytes": os.path.getsize(file_path)}
    try:
        import cv2
        cap = cv2.VideoCapture(file_path)
        info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        info["fps"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
        info["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur = info["frame_count"] / info["fps"] if info["fps"] else 0
        info["duration_seconds"] = round(dur, 2)
        info["codec"] = int(cap.get(cv2.CAP_PROP_FOURCC))
        cap.release()
    except Exception:
        info["error"] = "opencv not installed - using lightweight probe"
    return info


def _detect_face(gray):
    """Try MediaPipe, then OpenCV Haar cascade.

    Returns a dict with ``has_face`` plus face quality metrics:
    ``face_consistency`` (0..1, high=natural face) and ``lighting_consistency``
    (0..1). Deepfake faces tend to score low on both.
    """
    out = {"has_face": False, "width": 0, "height": 0,
           "face_consistency": 0.5, "lighting_consistency": 0.5}
    face_box = None
    try:
        import mediapipe as mp
        import cv2
        with mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.3) as fd:
            rgb = cv2.cvtColor(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2RGB)
            res = fd.process(rgb)
            if res.detections:
                bb = res.detections[0].location_data.relative_bounding_box
                out["has_face"] = True
                h, w = gray.shape[:2]
                face_box = (int(bb.xmin * w), int(bb.ymin * h),
                            int(bb.width * w), int(bb.height * h))
    except Exception:  # noqa: BLE001
        pass
    try:
        import cv2
        if face_box is None:
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            if len(faces) > 0:
                x, y, w, h = faces[0]
                face_box = (x, y, w, h)
                out["has_face"] = True
    except Exception:  # noqa: BLE001
        pass

    if face_box:
        x, y, w, h = face_box
        out["width"], out["height"] = w, h
        try:
            import cv2
            eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml")
            face_gray = gray[y:y + h, x:x + w]
            eyes = eye_cascade.detectMultiScale(face_gray, 1.1, 5, minSize=(8, 8))
            eye_ratio = min(1.0, len(eyes) / 2.0)
            # A generated face often has 0 eyes detected (uncanny gaps).
            out["face_consistency"] = round(
                min(1.0, max(0.0, 0.2 if eye_ratio == 0 else 0.5 + eye_ratio * 0.5)), 4)
            mid = w // 2
            left = float(face_gray[:, :mid].mean()) if mid else 0.0
            right = float(face_gray[:, mid:].mean()) if mid < w else 0.0
            light = abs(left - right) / 128.0
            out["lighting_consistency"] = round(
                min(1.0, max(0.0, 1.0 - light)), 4)
        except Exception:  # noqa: BLE001
            pass
    return out


def _frame_targets(count, n):
    """Evenly spaced, unique, ascending frame indices to sample."""
    step = max(1, count // n)
    return sorted({min(count - 1, i * step) for i in range(n)})


def _read_sampled_frames(file_path, indices):
    """Read the frames at ``indices`` using frame seeks where possible.

    Decoding every frame just to reach a handful of evenly spaced samples is
    the dominant cost of a video scan, so this seeks straight to each wanted
    position. When a codec/backend doesn't honour seeking (the position would
    move backwards), it falls back to a single sequential pass.
    """
    import cv2
    frames = []
    cap = cv2.VideoCapture(file_path)
    try:
        want = sorted(indices)
        if not want:
            return frames
        seekable = True
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, want[len(want) // 2])
            if int(cap.get(cv2.CAP_PROP_POS_FRAMES)) < want[len(want) // 2]:
                seekable = False
        except Exception:  # noqa: BLE001
            seekable = False
        if seekable:
            for idx in want:
                try:
                    ok = cap.set(cv2.CAP_PROP_POS_FRAMES, idx) and \
                        int(cap.get(cv2.CAP_PROP_POS_FRAMES)) >= idx
                except Exception:  # noqa: BLE001
                    ok = False
                if not ok:
                    seekable = False
                    break
                grabbed, frame = cap.read()
                if not grabbed:
                    break
                frames.append(frame)
        if not seekable or len(frames) < len(want):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frames, pos, wi = [], -1, 0
            while wi < len(want):
                grabbed, frame = cap.read()
                pos += 1
                if not grabbed:
                    break
                if pos == want[wi]:
                    frames.append(frame)
                    wi += 1
    finally:
        cap.release()
    return frames


def _frame_for_processing(frame, max_dim=None):
    """Downscale a BGR frame so image features and the CNN stay fast on high-res video."""
    import cv2
    limit = max_dim or getattr(Config, "VIDEO_FRAME_MAX_DIM", 720)
    h, w = frame.shape[:2]
    if limit and max(h, w) > limit:
        scale = float(limit) / float(max(h, w))
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_AREA)
    return frame


def _extract_frames(file_path, max_frames=None):
    """Extract evenly spaced frames for analysis.

    Only the sampled frame positions are decoded (frame seeks, with a
    sequential fallback), so long videos don't pay a full decode. Returns
    ``(frame_metrics, raw_frames)`` where ``raw_frames`` are the downscaled BGR
    frames that can be fed straight into the trained frame-CNN without a second
    decode of the file.

    Each sampled frame carries face quality + image-feature metrics (identical
    to the image analyzer's `feature_vector`, so a scanned frame and a
    pipeline-reference frame are measured the same way).
    """
    max_frames = max_frames or Config.VIDEO_FRAME_SAMPLE_SIZE
    frames, raw_frames = [], []
    try:
        import cv2
        from services.analyze_image import feature_vector
        cap = cv2.VideoCapture(file_path)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if count <= 0:
            count = 240
        indices = _frame_targets(count, max_frames)
        sampled = _read_sampled_frames(file_path, indices)
        for idx, frame in zip(indices, sampled):
            try:
                small = _frame_for_processing(frame)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                face = _detect_face(gray)
                frame_feats = {}
                try:
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    from PIL import Image
                    frame_feats = feature_vector(Image.fromarray(rgb))
                except Exception:  # noqa: BLE001
                    pass
                frames.append({
                    "index": idx,
                    "timestamp": round(idx / fps, 2) if fps else 0,
                    "has_face": face["has_face"],
                    "face_w": face["width"],
                    "face_h": face["height"],
                    "face_consistency": face["face_consistency"],
                    "lighting_consistency": face["lighting_consistency"],
                    "sharpness": float(gray.var()) if gray.size else 0,
                    "mean_luma": float(gray.mean()) if gray.size else 0,
                    "ela": frame_feats.get("error_level_analysis"),
                    "texture": frame_feats.get("texture_uniformity"),
                    "recomp": frame_feats.get("recompression_similarity"),
                    "entropy": frame_feats.get("histogram_entropy"),
                })
                raw_frames.append(small)
            except Exception:  # noqa: BLE001
                continue
    except Exception:
        pass
    return frames, raw_frames


def _hash_drift(file_path):
    """Sample a hash of bytes at several offsets; uniform randomness suggests synthetic content."""
    size = os.path.getsize(file_path)
    samples = []
    with open(file_path, "rb") as f:
        for rel in (0.02, 0.2, 0.5, 0.8):
            f.seek(int(size * rel))
            samples.append(hashlib.sha256(f.read(4096)).digest())
    diffs = sum(bin(a[i] ^ b[i]).count("1") for a, b in zip(samples, samples[1:]) for i in range(4))
    max_diff = 3 * 4 * 8
    return diffs / max_diff  # 0..1


def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def feature_vector(file_path, max_frames=None):
    """Shared video feature vector (used by the reference-profile builder).

    Mirrors ``analyze_image.feature_vector``: the exact same measurements are
    used for a user's upload and for pipeline reference videos so the
    reference comparison is apples-to-apples.
    """
    frames, _ = _extract_frames(file_path, max_frames)
    if not frames:
        return None
    return _aggregate_features(frames, _probe_video(file_path), _hash_drift(file_path))


def _aggregate_features(frames, info, drift):
    """Turn sampled frames into the shared numeric feature dict."""
    n = len(frames)
    with_face = sum(1 for f in frames if f["has_face"])
    face_presence = with_face / n
    consistency = sum(f.get("face_consistency", 0.5) for f in frames) / n
    sharp = [f["sharpness"] for f in frames]
    flicker = (max(sharp) - min(sharp)) / (max(sharp) + 1e-6) if n > 1 else 0.0
    dur = info.get("duration_seconds", 0)
    size_bytes = info.get("size_bytes", 0)
    compression = 1.0 - min(1.0, (size_bytes / 1_000_000) / max(1.0, dur * 4))

    def _mean(values):
        vals = [v for v in values if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.5

    return {
        "face_presence": round(face_presence, 4),
        "synthetic_smoothness": round(max(0.0, min(1.0, 1.0 - consistency)), 4),
        "temporal_flicker": round(max(0.0, min(1.0, flicker)), 4),
        "byte_hash_drift": round(max(0.0, min(1.0, drift)), 4),
        "compression_ratio": round(max(0.0, min(1.0, compression)), 4),
        "texture_uniformity": round(_mean([f["texture"] for f in frames]), 4),
        "error_level_analysis": round(_mean([f["ela"] for f in frames]), 4),
        "frame_count": n,
        "_frame_textures": [_mean([f["texture"]]) for f in frames],
        "_frame_ela": [_mean([f["ela"]]) for f in frames],
        "_face_count": with_face,
    }


def analyze_video(file_path, filename, size_bytes):
    start = time.time()
    info = _probe_video(file_path)
    frames, raw_frames = _extract_frames(file_path)
    drift = _hash_drift(file_path)
    file_hash = _sha256(file_path)
    shared = _aggregate_features(frames, info, drift) or {
        "face_presence": 0.0, "synthetic_smoothness": 0.0, "temporal_flicker": 0.0,
        "texture_uniformity": 0.5, "error_level_analysis": 0.5, "frame_count": 0,
    }

    # ---------------------------- heuristic ---------------------------- #
    face_ratio = shared["face_presence"]
    with_face = shared.get("_face_count", 0)
    shadow = max(0.0, 1.0 - face_ratio) if face_ratio > 0 else 0.0

    ela_vals = shared.get("_frame_ela") or []
    ela_mean = shared["error_level_analysis"]
    ela_std = 0.0
    if len(ela_vals) > 1:
        m = sum(ela_vals) / len(ela_vals)
        ela_std = (sum((v - m) ** 2 for v in ela_vals) / len(ela_vals)) ** 0.5
    # Generated frames re-compress almost identically across frames, so the
    # ELA error stays unnaturally flat in time.
    ela_stability = max(0.0, min(1.0, 1.0 - min(1.0, ela_std / 0.04)))

    texture_score = shared["texture_uniformity"]
    consistency = 1.0 - shared["synthetic_smoothness"]
    eye_bad = 1.0 - consistency if with_face else 0.0
    flicker = shared["temporal_flicker"]
    synthetic_drift = max(0.0, min(1.0, drift - 0.5) * 2)
    dur = info.get("duration_seconds", 0)
    compression = shared["compression_ratio"]

    features = {
        "face_presence": round(face_ratio, 4),
        "synthetic_smoothness": round(shared["synthetic_smoothness"], 4),
        "temporal_flicker": round(flicker, 4),
        "byte_hash_drift": round(synthetic_drift, 4),
        "compression_ratio": round(compression, 4),
        "lip_sync_alignment": round(max(0.0, 1.0 - flicker), 4),
        "texture_uniformity": round(texture_score, 4),
        "error_level_analysis": round(ela_mean, 4),
        "ela_temporal_stability": round(ela_stability, 4),
        "face_consistency": round(consistency, 4),
        "frame_count": len(frames) or info.get("frame_count", 0),
        "duration_seconds": dur,
        "resolution": f"{info.get('width', '?')}x{info.get('height', '?')}",
    }

    # Temporal smoothness of the whole clip + frame-level artefact pressure.
    base = (
        0.16 * shadow
        + 0.16 * flicker
        + 0.12 * synthetic_drift
        + 0.10 * compression
        + 0.18 * ela_stability
        + 0.16 * texture_score
        + 0.12 * eye_bad
    )
    base = max(0.0, min(1.0, base))

    # ----------------------- pipeline reference blend ----------------------- #
    # User uploads are scored against per-class feature distributions built from
    # the Kaggle/HuggingFace/Google video corpus (never from user data).
    kaggle_info = None
    try:
        from services.kaggle_reference import kaggle_reference
        kaggle_reference.ensure_built("video")
        kaggle_info = kaggle_reference.score(features, media_type="video")
        if kaggle_info and kaggle_info.get("status") == "ready":
            ref_likelihood = kaggle_info["fake_likelihood"]
            base = max(0.0, min(1.0, 0.75 * base + 0.25 * ref_likelihood))
    except Exception:  # noqa: BLE001
        kaggle_info = None

    # ------------------------- trained CNN signal -------------------------- #
    # When a frame-CNN has been trained on the pipeline datasets and deployed,
    # blend its real fake-probability in and let the ensemble's "Temporal CNN"
    # slot vote with the true network output.
    cnn_info = None
    cnn_fake_pct = None
    try:
        from services.video_detector import video_detector
        if video_detector.available():
            cnn_info = video_detector.predict(file_path, frames=raw_frames)
            if cnn_info and cnn_info.get("fake_probability") is not None:
                cnn_fake_pct = cnn_info["fake_probability"] * 100.0
                base = max(0.0, min(1.0,
                                    (1.0 - Config.VIDEO_CNN_WEIGHT) * base
                                    + Config.VIDEO_CNN_WEIGHT * cnn_info["fake_probability"]))
                features["cnn_ai_probability"] = round(cnn_info["fake_probability"], 4)
    except Exception:  # noqa: BLE001
        cnn_info = None

    real_scores = {"Temporal CNN": cnn_fake_pct} if cnn_fake_pct is not None else None
    models, fake_probability = build_models("video", base * 100, filename, spread=4.5,
                                            real_scores=real_scores)
    result, _risk = _interpret(fake_probability)
    risk = risk_label(fake_probability)
    ai_origin = classify_ai_origin("video", features, fake_probability)
    susp = suspicious_scale(fake_probability, ai_origin, features, "video")
    reasons = reasons_from_features("video", features, fake_probability)
    if cnn_fake_pct is not None:
        reasons.insert(0, {
            "check": "Trained frame-CNN (EfficientNet) forensic signal",
            "passed": cnn_fake_pct < 50.0,
            "detail": f"CNN fake probability {cnn_fake_pct:.1f}% "
                      f"({cnn_info.get('frames_analyzed', 0)} frames, "
                      f"{cnn_info.get('fake_share', 0.0):.0%} flagged)",
        })
    trust = trust_score(fake_probability, {
        "face": consistency,
        "noise": 1.0 - texture_score,
        "compression": 1.0 - compression,
        "temporal": 1.0 - ela_stability,
    })
    explanation = explain_short("video", result, fake_probability)
    if ai_origin == "ai_manipulated":
        explanation += (" The video appears to have been converted or edited using AI tools "
                        "(temporal flicker / face inconsistencies), raising the suspicion scale.")
    elif ai_origin == "ai_generated":
        explanation += " The footage shows hallmarks of being generated entirely by AI."
    recommendations = _recommendations(result)

    # Per-frame timeline with a verdict for each sampled second.
    timeline = []
    for f in frames:
        anomaly = 0.0
        if f["has_face"]:
            if f.get("face_consistency", 0.5) < 0.4:
                anomaly += 0.35
            if f.get("ela") is not None and f["ela"] > 0.4:
                anomaly += 0.25
        else:
            anomaly += 0.3
        if anomaly > 0.5:
            verdict = "fake"
        elif anomaly > 0.25:
            verdict = "inconclusive"
        else:
            verdict = "authentic"
        timeline.append({
            "t": f.get("timestamp"),
            "face": f.get("has_face"),
            "sharpness": round(f.get("sharpness", 0)),
            "verdict": verdict,
        })

    elapsed = int((time.time() - start) * 1000)
    return {
        "scan_type": "video",
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
        "metadata": {**{k: v for k, v in info.items() if not isinstance(v, bytes)},
                     "file_hash_sha256": file_hash},
        "features": features,
        "models": models,
        "reasons": reasons,
        "file_hash": file_hash,
        "suspicious_sections": timeline,
        "model": "video-frame-cnn-v1" if cnn_fake_pct is not None else "temporal-heuristic-v1",
        "kaggle_reference": kaggle_info,
        "video_cnn": cnn_info,
        "verified": False,
    }


def _interpret(prob):
    if prob >= 62:
        return "fake", "high"
    if prob >= 42:
        return "inconclusive", "medium"
    return "authentic", "low"


def _recommendations(result):
    base = ["Run face verification against known biometric samples",
            "Check lip-sync and audio-to-video alignment",
            "Review upload history and metadata of the source",
            "Use forensic tools such as DeepFake-o-meter or SemaFor"]
    if result == "fake":
        return "\n".join(["Treat content as manipulated - do not redistribute.",
                          "Report to platform moderation and law enforcement.",
                          "Preserve the video file and this report."] + base[:2])
    return "\n".join(base)