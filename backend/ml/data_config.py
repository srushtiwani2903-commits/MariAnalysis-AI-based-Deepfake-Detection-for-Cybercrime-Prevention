"""Dataset registry for the on-demand Kaggle data pipeline.

Each entry maps a Kaggle dataset slug to a media type. The pipeline fetches
each dataset directly from Kaggle (temp cache) ONLY when the corresponding
training script runs - data is never stored in the project.

When a Kaggle dataset is required (non-optional) but cannot be downloaded
(for example, gated / requires acceptance), set ``required=False`` so the
pipeline logs a warning instead of aborting.
"""
import os

from config import Config

DATASET_ROOT = os.path.join(Config.BASE_DIR, "models", "datasets")

# media_type -> (kaggle slug, local dir name, required, note)
DATASET_REGISTRY = [
    {
        "media": "image",
        "slug": "ciplab/real-and-fake-face-detection",
        "dir": "faces_real_vs_fake",
        "required": True,
        "note": "CelebA real faces + AI-generated fake faces for image CNN/ViT training.",
    },
    {
        "media": "image",
        "slug": "splcher/animefacedataset",
        "dir": "anime_faces",
        "required": False,
        "note": "Optional extra class of generated faces for harder generalization.",
    },
    {
        "media": "video",
        "slug": "unidpro/deepfake-videos-dataset",
        "dir": "video_fake_vs_real",
        "required": True,
        "note": "Real videos + videos with AI-generated faces for frame-level training.",
    },
    {
        "media": "audio",
        "slug": "adarshsingh0903/audio-deepfake-detection-dataset",
        "dir": "audio_real_vs_cloned",
        "required": True,
        "note": "Real human speech + AI-generated speech for spectral CNN training.",
    },
    {
        "media": "text",
        "slug": "alitaqishah/ai-vs-human-text-classification-dataset-2026",
        "dir": "text_ai_vs_human",
        "required": True,
        "note": "AI-generated vs human-written samples for transformer fine-tuning.",
    },
]

# Extra datasets can be merged from the environment, e.g.:
#   KAGGLE_EXTRA_DATASETS=user/dataset1,user/dataset2
# Each is treated as an image dataset under its own folder.
EXTRA_DATASETS = os.environ.get(
    "KAGGLE_EXTRA_DATASETS",
    os.environ.get("KAGGLE_EXTRA_DATASET", ""),
).strip()


def load_extra_datasets():
    """Parse KAGGLE_EXTRA_DATASETS into registry-compatible dicts."""
    extra = []
    for slug in [s.strip() for s in EXTRA_DATASETS.split(",") if s.strip()]:
        extra.append({
            "media": "image",
            "slug": slug,
            "dir": slug.replace("/", "__"),
            "required": False,
            "note": f"User-supplied extra dataset {slug}.",
        })
    return extra


def get_registry():
    return DATASET_REGISTRY + load_extra_datasets()
