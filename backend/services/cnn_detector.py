"""Optional trained-CNN inference for image scans.

Loads the checkpoint trained by ``ml/train_cnn_kaggle.py`` once (thread-safe),
preprocesses the uploaded image identically to training and returns a fake
probability in [0, 1]. When no weights are present (or ``MODEL_ENABLED=false``
or torch is not installed) the detector reports ``available() == False`` and
``predict()`` returns None, so the heuristic engine in ``analyze_image.py``
keeps working untouched.
"""
import logging
import os
import threading
import time

from config import Config

logger = logging.getLogger("cnn_detector")

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class _CnnDetector:
    def __init__(self):
        self._model = None
        self._meta = {}
        self._lock = threading.Lock()

    def available(self):
        """True only when MODEL_ENABLED, weights exist and torch is importable."""
        if not Config.MODEL_ENABLED:
            return False
        if not os.path.isfile(Config.IMAGE_CNN_PATH):
            return False
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

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
            ckpt = torch.load(Config.IMAGE_CNN_PATH, map_location="cpu", weights_only=True)
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
            logger.info("Loaded image CNN: %s classes=%s val_acc=%s", backbone,
                        classes, self._meta.get("val_accuracy"))
            return model

    def predict(self, image_path):
        """Return a dict with fake_probability, or None when unavailable/failed."""
        if not self.available():
            return None
        try:
            torch = self._torch()
            from PIL import Image
            from torchvision import transforms

            model = self._ensure_loaded()
            img = Image.open(image_path).convert("RGB")
            size = self._meta["image_size"]
            tf = transforms.Compose([
                transforms.Resize(int(size * 256 / 224)),
                transforms.CenterCrop(size),
                transforms.ToTensor(),
                transforms.Normalize(self._meta["transform"]["mean"],
                                     self._meta["transform"]["std"]),
            ])
            x = tf(img).unsqueeze(0)
            start = time.time()
            with torch.no_grad():
                logits = model(x)
            probs = torch.softmax(logits, dim=1)[0]
            latency_ms = int((time.time() - start) * 1000)
            fake_prob = float(probs[self._meta["fake_label"]])
            top = int(torch.argmax(probs).item())
            return {
                "fake_probability": round(min(1.0, max(0.0, fake_prob)), 4),
                "confidence": round(float(probs[top]), 4),
                "predicted_class": self._meta["classes"][top],
                "class_probabilities": {
                    str(c): round(float(p), 4)
                    for c, p in zip(self._meta["classes"], probs.tolist())
                },
                "backbone": self._meta["backbone"],
                "val_accuracy": self._meta.get("val_accuracy"),
                "latency_ms": latency_ms,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("CNN inference failed: %s", exc)
            return None


cnn_detector = _CnnDetector()
