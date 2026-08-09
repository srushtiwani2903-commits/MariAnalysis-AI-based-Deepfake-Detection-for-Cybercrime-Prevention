"""AI service orchestrator.

Selects the correct analyzer per media type. Runs the smart heuristic
engines (ELA, spectral analysis, NLP metrics, temporal analysis) which need
no model weights, so the full product works out of the box.

Every result dict shares the same schema so the frontend never changes.
"""
import logging
import time

from ml.data_config import get_registry
from services.analyze_audio import analyze_audio
from services.analyze_email import analyze_email
from services.analyze_image import analyze_image
from services.analyze_post import analyze_post
from services.analyze_text import analyze_text
from services.analyze_video import analyze_video

logger = logging.getLogger("ai_service")

# Reference Kaggle dataset backing each media type's heuristic scan.
# Primary dataset per media type: first registry entry wins (extra/optional
# datasets are appended later, so they never shadow the main reference).
_REFERENCE_DATASETS = {}
for _entry in get_registry():
    if _entry["media"] not in _REFERENCE_DATASETS:
        _REFERENCE_DATASETS[_entry["media"]] = _entry["slug"]


class AIService:
    def analyze(self, media_type: str, file_path: str, filename: str, size_bytes: int,
                text: str = None, caption: str = None):
        """Run the full pipeline and return a normalised prediction result."""
        started = time.time()

        if media_type == "image":
            result = analyze_image(file_path, filename, size_bytes)
        elif media_type == "video":
            result = analyze_video(file_path, filename, size_bytes)
        elif media_type == "audio":
            result = analyze_audio(file_path, filename, size_bytes)
        elif media_type == "text":
            result = analyze_text(text or "", filename or "text-input.txt")
        elif media_type == "email":
            result = analyze_email(text or "", filename or "email-input.txt")
        elif media_type == "post":
            result = analyze_post(file_path, filename, size_bytes, caption or "")
        else:
            result = {"error": "Unsupported media type."}

        if "error" not in result:
            result["model_version"] = "1.0.0"
            result["total_pipeline_ms"] = int((time.time() - started) * 1000)
            result["reference_dataset"] = _REFERENCE_DATASETS.get(media_type, "")
            result["reference_source"] = "kaggle"
            result["kaggle_reference_status"] = self._kaggle_status()
            result["explainable_ai"] = self._build_xai(result)
        return result

    @staticmethod
    def _kaggle_status():
        try:
            from services.kaggle_reference import kaggle_reference
            return kaggle_reference.status
        except Exception:  # noqa: BLE001
            return "unavailable"

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
