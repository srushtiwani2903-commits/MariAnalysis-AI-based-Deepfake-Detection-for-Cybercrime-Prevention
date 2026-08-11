"""Real AI model providers (Hybrid engine).

The heuristic analyzers in services/* compute a deterministic base score. This
module adds genuine model signals on top so every scan benefits from a real
AI without ever breaking:

  - Google Gemini (gemini-2.5-flash / flash-lite) via the free tier. One API
    key, multimodal: images, sampled video frames, audio and text.
  - Local Hugging Face transformers models (image + text) that run fully
    offline - free, unlimited and private.

Both providers are best-effort: if the SDK is missing, the API key is absent,
the quota is exhausted (429) or the call times out, the provider returns None
and the caller blends only the sources it actually got. The deterministic
heuristic is always the guaranteed fallback, so the app never goes down.

Every function returns a dict like::

    {"available": bool, "fake_probability": 0-100, "reason": str,
     "provider": str, "model": str}

or None when the provider could not produce a score.
"""
import hashlib
import io
import logging
import os
import threading
import time

logger = logging.getLogger("model_providers")

# ---------------------------------------------------------------------------
# SDK / dependency availability (checked lazily so imports never crash)
# ---------------------------------------------------------------------------
_HAS_GEMINI = False
try:
    from google import genai  # noqa: F401
    from google.genai import types as genai_types  # noqa: F401
    _HAS_GEMINI = True
except Exception:  # noqa: BLE001
    logger.info("google-genai SDK not installed - Gemini provider disabled.")

_HAS_TORCH = False
_HAS_TF = False
try:
    import torch  # noqa: F401
    _HAS_TORCH = True
except Exception:  # noqa: BLE001
    pass
try:
    import transformers  # noqa: F401
    _HAS_TF = True
except Exception:  # noqa: BLE001
    pass

# ---------------------------------------------------------------------------
# Simple in-memory rate budget for the free Gemini tier (best effort). It keeps
# us from hammering the 429s on the free quota (default ~250 req/day).
# ---------------------------------------------------------------------------
_BUDGET = {"count": 0, "window_start": time.time()}
_BUDGET_LOCK = threading.Lock()
_MAX_PER_WINDOW = 200
_WINDOW_SECONDS = 24 * 3600


def _consume_budget() -> bool:
    """Return True if we may fire a Gemini request under the local budget."""
    with _BUDGET_LOCK:
        now = time.time()
        if now - _BUDGET["window_start"] > _WINDOW_SECONDS:
            _BUDGET["count"] = 0
            _BUDGET["window_start"] = now
        if _BUDGET["count"] >= _MAX_PER_WINDOW:
            return False
        _BUDGET["count"] += 1
        return True


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------
_client = None
_client_lock = threading.Lock()
_MODEL_CACHE = {}


def _gemini_client():
    """Lazily build the Gemini client. Returns None if unusable."""
    global _client
    if _client is not None:
        return _client
    from config import Config
    if not Config.GEMINI_API_KEY:
        return None
    if not _HAS_GEMINI:
        return None
    with _client_lock:
        if _client is None:
            try:
                _client = genai.Client(api_key=Config.GEMINI_API_KEY)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini client init failed: %s", exc)
                _client = None
    return _client


def _gemini_model_name():
    from config import Config
    return Config.GEMINI_MODEL


def _infer_json(text):
    """Best-effort JSON parse of a model reply (handles code fences)."""
    import json
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.lstrip("json").strip()
    try:
        return json.loads(cleaned)
    except Exception:  # noqa: BLE001
        # fall back to first JSON object found in the text
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:  # noqa: BLE001
                return None
        return None


def _sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def _gemini_prompt(media_type):
    """One shared instruction that produces a stable JSON verdict."""
    base = (
        "You are a forensic deepfake detection expert. Analyse the provided "
        "media and estimate the probability (0-100) that it is AI-generated or "
        "manipulated. Return STRICTLY valid JSON only, no extra text: "
        '{"fake_probability": <0-100 integer>, "reason": "<short one-line reason>"}'
    )
    media_hints = {
        "image": ("For the image, look for recompression artifacts, unnatural "
                  "texture, face/eye/lighting inconsistencies and generation "
                  "fingerprints."),
        "video": ("The video is provided as sampled frames. Assess facial "
                  "consistency, lighting and per-frame generation artifacts "
                  "and give an overall video verdict."),
        "audio": ("For the audio, assess spectral/prosodic naturalness and "
                  "voice-cloning artifacts."),
        "text": ("For the text, assess whether it reads like AI-generated "
                 "writing (uniformity, repetition, no personal nuance)."),
        "email": ("This is an email. Assess whether it is AI-written AND "
                  "phishing/scam content."),
        "post": ("This is a social-media post (image + caption). Assess whether "
                 "image and/or caption are AI-generated or misleading."),
    }
    return f"{base} {media_hints.get(media_type, '')}"


def _run_gemini(parts, media_type):
    """Send contents to Gemini, parse the verdict. Returns dict or None."""
    client = _gemini_client()
    if client is None or not _consume_budget():
        return None
    try:
        resp = client.models.generate_content(
            model=_gemini_model_name(),
            contents=parts,
            config={"response_mime_type": "application/json"},
        )
        if not resp or not resp.text:
            return None
        data = _infer_json(resp.text)
        if not data:
            return None
        prob = float(data.get("fake_probability", -1))
        if prob < 0 or prob > 100:
            return None
        return {
            "available": True,
            "fake_probability": round(prob, 1),
            "reason": str(data.get("reason", ""))[:500],
            "provider": "gemini",
            "model": _gemini_model_name(),
        }
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
            logger.warning("Gemini rate limit hit: %s", msg)
        else:
            logger.warning("Gemini request failed: %s", msg)
        return None


def _media_parts_for(media_type, file_path=None, text=None, max_kb=18 * 1024):
    """Build Gemini contents (Parts) for a media type. None if no payload."""
    from google.genai import types as gtypes
    if media_type in ("text", "email"):
        if not text:
            return None
        prompt = _gemini_prompt(media_type)
        return [prompt, text[:20000]]
    if file_path and os.path.exists(file_path):
        mime_map = {
            "image": "image/jpeg",
            "post": "image/jpeg",
            "video": "image/jpeg",
            "audio": "audio/mp3",
        }
        mime = mime_map.get(media_type, "application/octet-stream")
        size = os.path.getsize(file_path)
        prompt = _gemini_prompt(media_type)
        if media_type in ("image", "post") and size <= max_kb:
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                return [prompt, gtypes.Part.from_bytes(data=data, mime_type=mime)]
            except Exception:  # noqa: BLE001
                return None
        if media_type == "audio" and size <= max_kb:
            try:
                import mimetypes
                amime = mimetypes.guess_type(file_path)[0] or "audio/mp3"
                with open(file_path, "rb") as f:
                    data = f.read()
                return [prompt, gtypes.Part.from_bytes(data=data, mime_type=amime)]
            except Exception:  # noqa: BLE001
                return None
        if media_type == "video":
            frames = _sample_video_frames(file_path, max_frames=6)
            if frames:
                parts = [prompt]
                parts.extend(gtypes.Part.from_bytes(data=f, mime_type="image/jpeg")
                             for f in frames)
                return parts
    return None


def _sample_video_frames(file_path, max_frames=6):
    """Evenly spaced JPEG frames for Gemini (audio+visual not needed)."""
    frames = []
    try:
        import cv2
        cap = cv2.VideoCapture(file_path)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if count <= 0:
            count = 240
        step = max(1, count // max_frames)
        idx = 0
        seen = 0
        while seen < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                ok_jpg, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok_jpg:
                    frames.append(buf.tobytes())
                    seen += 1
            idx += 1
        cap.release()
    except Exception:  # noqa: BLE001
        pass
    return frames


def gemini_score(media_type, file_path=None, text=None):
    """Best-effort Gemini verdict. None when unavailable/failed."""
    try:
        parts = _media_parts_for(media_type, file_path, text)
        if not parts:
            return None
        # Run with a hard timeout so a slow API never blocks the request.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
        from config import Config
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_gemini, parts, media_type)
            try:
                return future.result(timeout=Config.GEMINI_TIMEOUT_SECONDS)
            except FutTimeout:
                logger.warning("Gemini timed out for %s", media_type)
                return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("gemini_score error (%s): %s", media_type, exc)
        return None


# ---------------------------------------------------------------------------
# Local Hugging Face providers (offline, free, unlimited)
# ---------------------------------------------------------------------------
_LOCAL_MODELS = {}
_LOCAL_LOCK = threading.Lock()

_LOCAL_REGISTRY = {
    "image": {
        "model": "dima806/deepfake_vs_real_image_detection",
        "label": "Local ViT (deepfake-vs-real)",
        "kind": "image",
    },
    "text": {
        "model": "roberta-base-openai-detector",
        "label": "Local RoBERTa (openai-detector)",
        "kind": "text",
    },
}


def local_available():
    """True if local inference is usable on this machine."""
    from config import Config
    return bool(Config.LOCAL_MODELS_ENABLED and _HAS_TORCH and _HAS_TF)


def _load_local(name):
    """Lazy-load + cache a local model by registry key."""
    if name in _LOCAL_MODELS:
        return _LOCAL_MODELS[name]
    if not local_available():
        return None
    with _LOCAL_LOCK:
        if name in _LOCAL_MODELS:
            return _LOCAL_MODELS[name]
        spec = _LOCAL_REGISTRY.get(name)
        if not spec:
            return None
        try:
            from transformers import (AutoImageProcessor, AutoModelForImageClassification,
                                      AutoModelForSequenceClassification, AutoTokenizer)
            if spec["kind"] == "image":
                processor = AutoImageProcessor.from_pretrained(spec["model"])
                model = AutoModelForImageClassification.from_pretrained(spec["model"])
                _LOCAL_MODELS[name] = {"spec": spec, "processor": processor, "model": model}
            else:
                tokenizer = AutoTokenizer.from_pretrained(spec["model"])
                model = AutoModelForSequenceClassification.from_pretrained(spec["model"])
                _LOCAL_MODELS[name] = {"spec": spec, "tokenizer": tokenizer, "model": model}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local model load failed (%s): %s", name, exc)
            _LOCAL_MODELS[name] = None
    return _LOCAL_MODELS.get(name)


def _local_image_score(file_path):
    loaded = _load_local("image")
    if not loaded:
        return None
    try:
        import torch
        from PIL import Image
        with torch.inference_mode():
            image = Image.open(file_path).convert("RGB")
            inputs = loaded["processor"](images=image, return_tensors="pt")
            logits = loaded["model"](**inputs).logits
            probs = torch.softmax(logits, dim=1)[0]
            id2label = getattr(loaded["model"].config, "id2label", {}) or {}
            fake_prob = None
            for idx in range(probs.shape[0]):
                label = str(id2label.get(idx, "")).lower()
                if "fake" in label or "ai" in label:
                    fake_prob = float(probs[idx] * 100)
            if fake_prob is None:
                # Fallback: assume class order [real, fake]
                fake_prob = float(probs[-1] * 100)
        return {
            "available": True,
            "fake_probability": round(min(100.0, max(0.0, fake_prob)), 1),
            "reason": "Local ViT deepfake-vs-real classifier.",
            "provider": "local-hf",
            "model": "dima806/deepfake_vs_real_image_detection",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local image inference failed: %s", exc)
        return None


def _local_text_score(text):
    loaded = _load_local("text")
    if not loaded:
        return None
    try:
        import torch
        with torch.inference_mode():
            inputs = loaded["tokenizer"](text[:20000], return_tensors="pt",
                                         truncation=True, max_length=512)
            logits = loaded["model"](**inputs).logits
            probs = torch.softmax(logits, dim=1)[0]
            id2label = getattr(loaded["model"].config, "id2label", {}) or {}
            fake_prob = None
            for idx in range(probs.shape[0]):
                label = str(id2label.get(idx, "")).lower()
                if "fake" in label or "ai" in label or "machine" in label:
                    fake_prob = float(probs[idx] * 100)
            if fake_prob is None:
                # roberta-base-openai-detector: index 1 is "Fake"
                fake_prob = float(probs[1] * 100) if probs.shape[0] > 1 else float(probs[0] * 100)
        return {
            "available": True,
            "fake_probability": round(min(100.0, max(0.0, fake_prob)), 1),
            "reason": "Local RoBERTa (openai-detector) AI-text classifier.",
            "provider": "local-hf",
            "model": "roberta-base-openai-detector",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local text inference failed: %s", exc)
        return None


def local_score(media_type, file_path=None, text=None):
    """Best-effort local model verdict. None when unavailable/failed."""
    if media_type in ("image", "post"):
        if file_path and os.path.exists(file_path):
            return _local_image_score(file_path)
        return None
    if media_type in ("text", "email"):
        if text and len(text.strip()) >= 20:
            return _local_text_score(text)
        return None
    # audio / video local models are not wired yet - Gemini covers them.
    return None


# ---------------------------------------------------------------------------
# Blending
# ---------------------------------------------------------------------------
def blend_scores(heuristic, gemini=None, local=None):
    """Blend available probability sources (0-100 each) into one verdict.

    Unavailable providers are automatically dropped and the remaining weights
    are re-normalised, so the heuristic always has a guaranteed floor.
    """
    from config import Config
    weights = {
        "heuristic": Config.AI_BLEND_HEURISTIC,
        "gemini": Config.AI_BLEND_GEMINI,
        "local": Config.AI_BLEND_LOCAL,
    }
    sources = []
    if heuristic is not None:
        sources.append((max(0.0, min(100.0, float(heuristic))), weights["heuristic"]))
    if gemini and gemini.get("available"):
        sources.append((max(0.0, min(100.0, float(gemini["fake_probability"]))),
                        weights["gemini"]))
    if local and local.get("available"):
        sources.append((max(0.0, min(100.0, float(local["fake_probability"]))),
                        weights["local"]))
    if not sources:
        return 50.0
    total_w = sum(w for _, w in sources)
    return round(sum(p * w for p, w in sources) / total_w, 1)


def providers_status():
    """Human-readable status used by /api/model/health and admin."""
    from config import Config
    return {
        "gemini": {
            "enabled": bool(Config.GEMINI_API_KEY and _HAS_GEMINI),
            "api_key_set": bool(Config.GEMINI_API_KEY),
            "sdk_installed": _HAS_GEMINI,
            "model": Config.GEMINI_MODEL,
            "daily_budget_used": _BUDGET["count"],
            "daily_budget_max": _MAX_PER_WINDOW,
        },
        "local": {
            "enabled": bool(Config.LOCAL_MODELS_ENABLED and _HAS_TORCH and _HAS_TF),
            "torch_installed": _HAS_TORCH,
            "transformers_installed": _HAS_TF,
            "models": list(_LOCAL_REGISTRY.keys()),
        },
        "blend_weights": {
            "heuristic": Config.AI_BLEND_HEURISTIC,
            "gemini": Config.AI_BLEND_GEMINI,
            "local": Config.AI_BLEND_LOCAL,
        },
    }


def score_reason(provider_result, media_type):
    """Short human string used to enrich an analyzer's explanation."""
    if not provider_result or not provider_result.get("available"):
        return ""
    r = provider_result.get("reason") or ""
    return f" [{provider_result.get('provider')}: {r}]" if r else ""
