"""AI service orchestrator.

Selects the correct analyzer per media type and inserts a plug point for real
trained models. When MODEL_ENABLED is False, the smart heuristic engines provide
production-ready "dummy" predictions so the full product works out of the box.
To integrate a real model later:
  1. Train/save weights under backend/models/weights
  2. Set MODEL_ENABLED=true in the environment
  3. Implement `predict_*` below (or drop a load_model() hook in).

Every result dict shares the same schema so the frontend never changes.
"""
import time

from config import Config
from services.analyze_audio import analyze_audio
from services.analyze_image import analyze_image
from services.analyze_text import analyze_text
from services.analyze_video import analyze_video


class AIService:
    def __init__(self):
        self.model_enabled = Config.MODEL_ENABLED
        self._models = {}

    # ------------------------------------------------------------------ #
    # Real-model plug points (implement when you have trained weights)   #
    # ------------------------------------------------------------------ #
    def _load_real_models(self):
        """Load trained CNN/ViT weights once. Called only when MODEL_ENABLED=True."""
        if not self.model_enabled or self._models:
            return
        # Example placeholder - replace with your model loading code.
        # import torch
        # self._models["image"] = torch.load(os.path.join(Config.MODEL_PATH, "image_vit.pt"))
        pass

    def predict_image_real(self, file_path):
        raise NotImplementedError("Integrate your CNN/ViT image model here.")

    def predict_video_real(self, file_path):
        raise NotImplementedError("Integrate your temporal video model here.")

    def predict_audio_real(self, file_path):
        raise NotImplementedError("Integrate your voice-clone model here.")

    def predict_text_real(self, text):
        # Already integrated optionally via HuggingFace in analyze_text.
        return None

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def analyze(self, media_type: str, file_path: str, filename: str, size_bytes: int,
                text: str = None):
        """Run the full pipeline and return a normalised prediction result."""
        started = time.time()

        if media_type == "image":
            result = analyze_image(file_path, filename, size_bytes, self.model_enabled)
        elif media_type == "video":
            result = analyze_video(file_path, filename, size_bytes, self.model_enabled)
        elif media_type == "audio":
            result = analyze_audio(file_path, filename, size_bytes, self.model_enabled)
        elif media_type == "text":
            result = analyze_text(text or "", filename or "text-input.txt", self.model_enabled)
        else:
            result = {"error": "Unsupported media type."}

        if "error" not in result:
            result["model_version"] = "1.0.0"
            result["total_pipeline_ms"] = int((time.time() - started) * 1000)
            result["explainable_ai"] = self._build_xai(result)
        return result

    @staticmethod
    def _build_xai(result):
        """Explainable AI payload consumed by the results page."""
        return {
            "decision_factors": [
                {"factor": k, "importance": round(float(v), 3)}
                for k, v in (result.get("features") or {}).items()
                if isinstance(v, (int, float))
            ][:8],
            "summary": result.get("explanation", ""),
            "suggested_verification": (result.get("recommendations") or "").split("\n")[:5],
        }


service = AIService()
