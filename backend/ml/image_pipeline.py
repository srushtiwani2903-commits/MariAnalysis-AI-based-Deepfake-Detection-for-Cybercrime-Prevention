"""Multi-source image data pipeline for image deepfake / AI-generated detection.

Pulls labelled real + fake images from three independent source types, mirroring
``ml/video_pipeline.py``:

* **Kaggle** - reuses ``ml.kaggle_pipeline.stream_dataset`` (no persistence).
* **Hugging Face** - optional image repos configured via ``IMAGE_HF_DATASETS``.
* **Google Drive** - zipped real / AI-generated image archives downloaded via
  ``gdown`` (file IDs configured through ``IMAGE_GOOGLE_*_DRIVE_ID``).

Images are labelled by their parent folder name (real / fake / unknown). An
archive that contains a single class (e.g. an "AI-generated faces" Google
folder) can be forced to ``fake``/``real`` through the source's ``label`` field.
Everything lives in a temp cache that is auto-deleted; user uploads are NEVER
added to this corpus.

Usage:
    python -m ml.image_pipeline --list
    python -m ml.image_pipeline --source google --images-per-class 500
    python -m ml.image_pipeline --source huggingface
"""
import logging
import os
import random
import shutil
import tempfile
from contextlib import contextmanager

from config import Config

logger = logging.getLogger("image_pipeline")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
              ".gif", ".avif", ".heic", ".heif", ".jfif"}

SUPPORTED_SOURCES = ("kaggle", "huggingface", "google")

_REAL_TOKENS = ("real", "original", "bonafide", "genuine", "human", "natural",
                "authentic", "camera")
_FAKE_TOKENS = ("fake", "ai", "generated", "synthetic", "gan", "spoof",
                "diffusion", "midjourney", "sd", "deepfake", "manipulated")


def _google_sources():
    """Build Google Drive source entries from the configured file IDs."""
    sources = []
    real_id = getattr(Config, "IMAGE_GOOGLE_REAL_DRIVE_ID", "") or ""
    fake_id = getattr(Config, "IMAGE_GOOGLE_FAKE_DRIVE_ID", "") or ""
    if real_id:
        sources.append({
            "source": "google", "name": "google-real-images",
            "drive_id": real_id, "label": "real",
            "note": "Google Drive archive of real images.",
        })
    if fake_id:
        sources.append({
            "source": "google", "name": "google-ai-fake-images",
            "drive_id": fake_id, "label": "fake",
            "note": "Google Drive archive of AI-generated / fake images.",
        })
    return sources


def _hf_sources():
    """Build Hugging Face source entries from IMAGE_HF_DATASETS."""
    raw = (getattr(Config, "IMAGE_HF_DATASETS", "") or "").strip()
    out = []
    for repo in [r.strip() for r in raw.split(",") if r.strip()]:
        out.append({
            "source": "huggingface", "name": repo, "label": None,
            "note": f"User-supplied Hugging Face image dataset {repo}.",
        })
    return out


def _base_sources():
    """Kaggle registry entries as pipeline sources (always available)."""
    from ml.data_config import get_registry

    return [
        {"source": "kaggle", "name": entry["slug"], "label": None,
         "note": entry.get("note", "")}
        for entry in get_registry() if entry["media"] == "image"
    ]


def image_sources():
    return _base_sources() + _hf_sources() + _google_sources()


def list_sources():
    for entry in image_sources():
        if entry["source"] == "google":
            state = "ON"
        elif entry["source"] == "huggingface":
            state = "ON"
        else:
            state = "ON"
        label = f" [{entry['label']}]" if entry.get("label") else ""
        print(f"[{entry['source']:11s}] {entry['name']:45s} {state}{label}: {entry['note']}")


# ---------------------------------------------------------------------------
# Labelling helpers
# ---------------------------------------------------------------------------
def classify_dir(name):
    """Best-effort label ('real' / 'fake' / None) from a folder basename."""
    n = (name or "").lower()
    if any(tok in n for tok in _FAKE_TOKENS):
        return "fake"
    if any(tok in n for tok in _REAL_TOKENS):
        return "real"
    return None


def classify_relpath(rel, filename=None):
    """Label a repo-relative image path as 'real' / 'fake' / None.

    Resolution order: top-level folder -> immediate parent folder -> filename.
    Unclassifiable paths return None so the sample is skipped (never mislabelled).
    """
    top = rel.split("/", 1)[0].lower()
    cls = classify_dir(top)
    if cls is None and "/" in rel:
        cls = classify_dir(rel.rsplit("/", 1)[-2])
    if cls is None and filename:
        cls = classify_dir(os.path.splitext(os.path.basename(filename))[0])
    return cls


def _walk_images(root):
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                full = os.path.join(dirpath, f)
                if os.path.isfile(full) and os.path.getsize(full) > 0:
                    out.append(full)
    return out


def classify_images(root):
    result = {"real": [], "fake": []}
    for path in _walk_images(root):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        cls = classify_relpath(rel, filename=os.path.basename(path))
        if cls in result:
            result[cls].append(path)
    return result


# ---------------------------------------------------------------------------
# Source adapters (each fills real/ + fake/ folders under a temp root)
# ---------------------------------------------------------------------------
def _copy_balanced(src_cls, dest_root, per_class, slug, forced_label=None):
    """Copy up to ``per_class`` images of each class into dest real/fake dirs.

    When ``forced_label`` is set, every source image is treated as that class
    (used for single-class archives, e.g. an AI-generated-only Google folder).
    """
    copied = {"real": 0, "fake": 0}
    if forced_label:
        src_cls = {c: (src_cls.get("real", []) + src_cls.get("fake", []))
                   if c == forced_label else [] for c in ("real", "fake")}
    for cls in ("real", "fake"):
        os.makedirs(os.path.join(dest_root, cls), exist_ok=True)
        for i, image in enumerate(src_cls[cls]):
            if copied[cls] >= per_class:
                break
            ext = os.path.splitext(image)[1].lower() or ".jpg"
            target = os.path.join(
                dest_root, cls, f"{slug.replace('/','__')}_{cls}_{i}{ext}")
            try:
                shutil.copy2(image, target)
                copied[cls] += 1
            except OSError as exc:  # noqa: BLE001
                logger.debug("skip copy %s: %s", image, exc)
    return copied


def _kaggle_fetch(entry, dest_root, per_class):
    from ml.kaggle_pipeline import stream_dataset

    with stream_dataset(entry["name"]) as folder:
        logger.info("Kaggle %s: fetched %s, classifying images ...", entry["name"], folder)
        classified = classify_images(folder)
        return _copy_balanced(classified, dest_root, per_class, entry["name"])


def _hf_fetch(entry, dest_root, per_class):
    """Pull labelled images from a Hugging Face dataset repo."""
    from huggingface_hub import RepoFile, hf_hub_download, list_repo_tree  # noqa: WPS433

    repo = entry["name"]
    token = os.environ.get("HUGGINGFACE_TOKEN") or None
    try:
        entries = list_repo_tree(repo, recursive=True, repo_type="dataset", token=token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hugging Face %s not listable (gated or missing), skipping: %s",
                       repo, exc)
        return {}

    paths = []
    for f in entries:
        if not isinstance(f, RepoFile):
            continue
        if os.path.splitext(f.path)[1].lower() not in IMAGE_EXTS:
            continue
        paths.append(f.path)
        if len(paths) > 100000:
            logger.info("Hugging Face %s: stopped at 100k listed image files.", repo)
            break
    if not paths:
        logger.warning("Hugging Face %s: no image files found.", repo)
        return {}

    by_class = {"real": [], "fake": []}
    for path in paths:
        cls = classify_relpath(path, filename=path)
        if cls in by_class:
            by_class[cls].append(path)
    random.shuffle(by_class["real"])
    random.shuffle(by_class["fake"])

    counts = {"real": 0, "fake": 0}
    for cls in counts:
        os.makedirs(os.path.join(dest_root, cls), exist_ok=True)
    for cls in counts:
        for path in by_class[cls]:
            if counts[cls] >= per_class:
                break
            try:
                local = hf_hub_download(repo_id=repo, filename=path,
                                        repo_type="dataset", token=token)
            except Exception as exc:  # noqa: BLE001
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if (status == 401 or "401" in str(exc)[:120]) and counts[cls] == 0:
                    logger.warning("Hugging Face %s requires access (401) - skipping.", repo)
                    return dict(counts)
                logger.debug("Hugging Face %s skip %s: %s", repo, path, exc)
                continue
            idx = counts[cls]
            ext = os.path.splitext(path)[1].lower() or ".jpg"
            dest = os.path.join(dest_root, cls, f"hf_{idx}{ext}")
            try:
                shutil.copy2(local, dest)
                counts[cls] += 1
            except OSError as exc:  # noqa: BLE001
                logger.debug("Hugging Face %s copy skip %s: %s", repo, path, exc)
    logger.info("Hugging Face %s: sampled %s", repo, counts)
    return dict(counts)


def _google_fetch(entry, dest_root, per_class):
    """Download a Google-Drive-hosted image archive (optionally single-class)."""
    drive_id = entry.get("drive_id") or ""
    if not drive_id:
        raise RuntimeError(f"Google source {entry['name']} needs a Drive file ID.")
    import gdown  # noqa: WPS433

    parent = tempfile.mkdtemp(prefix="marianalysis_gdrive_img_")
    try:
        archive = os.path.join(parent, "download.zip")
        gdown.download(id=drive_id, output=archive, quiet=False)
        if not os.path.isfile(archive) or os.path.getsize(archive) == 0:
            raise RuntimeError("Google Drive download produced an empty file.")
        extract = os.path.join(parent, "data")
        os.makedirs(extract, exist_ok=True)
        import zipfile

        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract)
        else:
            shutil.copy2(archive, os.path.join(extract, os.path.basename(archive)))
        classified = classify_images(extract)
        return _copy_balanced(classified, dest_root, per_class, entry["name"],
                              forced_label=entry.get("label"))
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _fetch_sources(dest_root, sources, per_class):
    summary = []
    for entry in image_sources():
        if entry["source"] not in sources:
            continue
        limit = (Config.IMAGE_HF_IMAGES_PER_CLASS
                 if entry["source"] == "huggingface" else per_class)
        slug = f"{entry['source'][:3]}:{entry['name']}"
        try:
            if entry["source"] == "kaggle":
                copied = _kaggle_fetch(entry, dest_root, limit)
            elif entry["source"] == "huggingface":
                copied = _hf_fetch(entry, dest_root, limit)
            else:
                copied = _google_fetch(entry, dest_root, limit)
            summary.append({**entry, "copied": copied})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Source %s failed (%s) - continuing with the rest.", slug, exc)
    return summary


def _collect_staging(staging):
    result = {"real": [], "fake": []}
    for cls in result:
        folder = os.path.join(staging, cls)
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            full = os.path.join(folder, f)
            if (os.path.splitext(f)[1].lower() in IMAGE_EXTS
                    and os.path.isfile(full) and os.path.getsize(full) > 0):
                result[cls].append(full)
    return result


@contextmanager
def fetch_reference_images(per_class=None, sources=None):
    """Pull a small labelled real/fake image sample across the sources.

    Yields ({'real': [...paths], 'fake': [...]}, temp_dir). The caller owns the
    temp root; it is deleted when the block exits.
    """
    per_class = per_class or Config.IMAGE_PIPELINE_IMAGES_PER_CLASS
    sources = sources or list(SUPPORTED_SOURCES)
    parent = tempfile.mkdtemp(prefix="marianalysis_image_ref_")
    try:
        staging = os.path.join(parent, "staging")
        os.makedirs(os.path.join(staging, "real"), exist_ok=True)
        os.makedirs(os.path.join(staging, "fake"), exist_ok=True)
        _fetch_sources(staging, sources, per_class)
        yield _collect_staging(staging), parent
    finally:
        shutil.rmtree(parent, ignore_errors=True)


@contextmanager
def fetch_extra_images(per_class=None):
    """Pull images only from the optional extra sources (Hugging Face + Google).

    Used to augment the (Kaggle / local) reference profile. Yields the same
    shape as ``fetch_reference_images``; empty when nothing is configured.
    """
    per_class = per_class or Config.IMAGE_PIPELINE_IMAGES_PER_CLASS
    parent = tempfile.mkdtemp(prefix="marianalysis_image_extra_")
    try:
        staging = os.path.join(parent, "staging")
        os.makedirs(os.path.join(staging, "real"), exist_ok=True)
        os.makedirs(os.path.join(staging, "fake"), exist_ok=True)
        _fetch_sources(staging, ["huggingface", "google"], per_class)
        yield _collect_staging(staging), parent
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MariAnalysis multi-source image data pipeline "
                    "(Kaggle / Hugging Face / Google Drive).")
    parser.add_argument("--list", action="store_true", help="List configured sources.")
    parser.add_argument("--source", nargs="*", default=list(SUPPORTED_SOURCES),
                        help="Sources to use: kaggle huggingface google.")
    parser.add_argument("--images-per-class", type=int, default=None)
    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    unknown = set(args.source) - set(SUPPORTED_SOURCES)
    if unknown:
        parser.error(f"Unknown source(s): {sorted(unknown)}")

    with fetch_reference_images(per_class=args.images_per_class,
                                sources=args.source) as (per_class, _parent):
        for cls in ("real", "fake"):
            print(f"  {cls}: {len(per_class.get(cls, []))} images")


if __name__ == "__main__":
    main()
