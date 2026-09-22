"""Optional trained-CNN inference for video scans (frame-level).

Loads the checkpoint trained by ``ml/train_video_cnn_kaggle.py`` from
``Config.VIDEO_CNN_PATH`` once (thread-safe), samples ``N`` evenly spaced
frames from the uploaded video, predicts each frame with the same
preprocessing used at training (Real/Fake face frames) and aggregates the
per-frame fake probabilities into a video verdict. When no weights are
present (or ``VIDEO_MODEL_ENABLED=false`` or torch is not installed) the
detector reports ``available() == False`` and ``predict()`` returns None, so
the heuristic engine in ``analyze_video.py`` keeps working untouched.
"""
import logging
import os
import threading
import time

from config import Config

logger = logging.getLogger("video_detector")

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class _VideoDetector:
    def __init__(self):
        self._model = None
        self._meta = {}
        self._lock = threading.Lock()

    def available(self):
        """True only when VIDEO_MODEL_ENABLED, weights exist and torch is importable."""
        if not Config.VIDEO_MODEL_ENABLED:
            return False
        if not os.path.isfile(Config.VIDEO_CNN_PATH):
            return False
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def preload(self):
        """Warm the model + torch in the background (no-op if unavailable)."""
        if not self.available():
            return
        try:
            self._ensure_loaded()
            logger.info("Video CNN preloaded for faster first scan.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Video CNN preload failed: %s", exc)

    def _torch(self):
        import torch
        return torch

    def _build(self, backbone, num_classes):
        import torch.nn as nn
        from torchvision import models

        factory = getattr(models, backbone, None)
        if factory is None:
            raise ValueError(f"Unknown backbone '{backbone}' in checkpoint.")
        try:
            model = factory(weights=None)
        except Exception:
            model = factory(pretrained=False)  # legacy torchvision API
        if hasattr(model, "fc"):                       # ResNet family
            model.fc = nn.Linear(model.fc.in_features, num_classes)
        elif hasattr(model, "classifier"):             # EfficientNet / MobileNet
            if isinstance(model.classifier, nn.Sequential):
                model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, num_classes)
            else:
                model.classifier = nn.Linear(model.classifier.in_features, num_classes)
        elif hasattr(model, "heads"):                  # ViT family
            model.heads.head = nn.Linear(model.heads.head.in_features, num_classes)
        else:
            raise ValueError(f"Unsupported head for backbone '{backbone}'")
        return model

    def _ensure_loaded(self):
        torch = self._torch()
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            ckpt = torch.load(Config.VIDEO_CNN_PATH, map_location="cpu", weights_only=True)
            backbone = ckpt.get("backbone", "efficientnet_b0")
            classes = list(ckpt.get("classes", ["real", "fake"]))
            model = self._build(backbone, len(classes))
            model.load_state_dict(ckpt["model"])
            model.eval()
            self._model = model
            self._meta = {
                "backbone": backbone,
                "classes": classes,
                "fake_label": int(ckpt.get("fake_label", 1)),
                "image_size": int(ckpt.get("image_size", 224)),
                "val_accuracy": ckpt.get("val_accuracy"),
                "transform": ckpt.get("transform") or {"mean": IMAGENET_MEAN, "std": IMAGENET_STD},
            }
            logger.info("Loaded video CNN: %s classes=%s val_acc=%s", backbone,
                        classes, self._meta.get("val_accuracy"))
            return model

    def _frames(self, video_path, max_frames):
        """Return evenly spaced RGB PIL frames. Best-effort with OpenCV.

        Uses frame seeks (with a sequential fallback) so only the sampled
        positions are decoded instead of the whole video.
        """
        from services.analyze_video import _frame_targets, _read_sampled_frames
        frames = []
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
            if count <= 0:
                count = 240
            for frame in _read_sampled_frames(
                    video_path, _frame_targets(count, max_frames)):
                from PIL import Image
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(Image.fromarray(rgb))
        except Exception:  # noqa: BLE001
            pass
        return frames

    def predict(self, video_path, frames=None):
        """Return a dict with fake_probability, or None when unavailable/failed.

        The video-level probability is the mean of per-frame fake probabilities;
        ``max_fake`` and ``fake_share`` tell how consistently the network flags
        frames (a face-swapped section only flags part of the timeline).

        ``frames`` optionally passes already-decoded BGR numpy frames (the same
        ones the heuristic extractor sampled) so the video file is decoded only
        once across the whole scan.
        """
        if not self.available():
            return None
        try:
            torch = self._torch()
            import cv2
            from torchvision import transforms

            model = self._ensure_loaded()
            size = self._meta["image_size"]
            tf = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(size),
                transforms.ToTensor(),
                transforms.Normalize(self._meta["transform"]["mean"],
                                     self._meta["transform"]["std"]),
            ])

            if frames is None:
                frames_pil = self._frames(
                    video_path, max_frames=Config.VIDEO_FRAME_SAMPLE_SIZE)
            else:
                frames_pil = []
                for frame in frames:
                    from PIL import Image
                    frames_pil.append(Image.fromarray(
                        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            if not frames_pil:
                logger.warning("Video CNN: no frames could be sampled from %s", video_path)
                return None

            start = time.time()
            with torch.no_grad():
                batch = torch.stack([tf(img) for img in frames_pil])
                logits = model(batch)
                probs = torch.softmax(logits, dim=1)
                probs = [float(p) for p in probs[:, self._meta["fake_label"]].tolist()]
            latency_ms = int((time.time() - start) * 1000)

            mean_prob = sum(probs) / len(probs)
            p95 = sorted(probs)[int(len(probs) * 0.95) - 1] if probs else 0.0
            import statistics
            spread = statistics.pstdev(probs) if len(probs) > 1 else 0.0
            return {
                "fake_probability": round(min(1.0, max(0.0, mean_prob)), 4),
                "confidence": round(1.0 - spread, 4),
                "predicted_class": self._meta["classes"][1 if mean_prob >= 0.5 else 0],
                "fake_share": round(sum(1 for p in probs if p >= 0.5) / len(probs), 4),
                "max_fake": round(max(probs), 4),
                "p95_fake": round(max(0.0, min(1.0, p95)), 4),
                "spread": round(spread, 4),
                "frames_analyzed": len(probs),
                "backbone": self._meta["backbone"],
                "val_accuracy": self._meta.get("val_accuracy"),
                "latency_ms": latency_ms,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Video CNN inference failed: %s", exc)
            return None


video_detector = _VideoDetector()