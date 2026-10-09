"""Bulk-download real/fake image corpora onto a large drive (e.g. a pendrive).

Unlike ``ml.image_pipeline`` (which samples a small balanced set into a temp
dir), this module pulls **whole** Kaggle datasets and folder-structured
Hugging Face repos and lays them out as::

    <root>/real/<source>__real_<n>.<ext>
    <root>/fake/<source>__fake_<n>.<ext>

Downloads are resumable (a JSON manifest records finished sources) and capped
(``--max-gb``); the process stops once the on-disk total reaches the cap.

Usage:
    python -m ml.download_image_datasets --root G:\\MariAnalysis_Datasets\\image
    python -m ml.download_image_datasets --list
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time

try:  # package-relative when imported, absolute when run as a script
    from ml.kaggle_pipeline import resolve_credentials, write_kaggle_json
except Exception:  # noqa: BLE001
    from kaggle_pipeline import resolve_credentials, write_kaggle_json

logger = logging.getLogger("download_image_datasets")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
              ".gif", ".avif", ".heic", ".heif", ".jfif", ".jpe"}

DEFAULT_ROOT = r"G:\MariAnalysis_Datasets\image"
DEFAULT_MAX_GB = 20.0

# Normalised folder names that unambiguously mean one class. Combined names such
# as "real_vs_fake" normalise to "realvsfake" and intentionally match nothing so
# the resolver falls through to the deeper real/ or fake/ folder.
REAL_NAMES = {
    "real", "reals", "realimage", "realimages", "realface", "real_faces",
    "real_face", "realfaces", "trainingreal", "training_real", "valreal",
    "testreal", "original", "originals", "bonafide", "genuine", "authentic",
    "human", "humans", "humanwritten", "realart", "realartdata", "0", "no",
    "nature", "natural", "camera",
}
FAKE_NAMES = {
    "fake", "fakes", "fakeimage", "fakeimages", "fakeface", "fake_faces",
    "fake_face", "fakefaces", "trainingfake", "training_fake", "valfake",
    "testfake", "ai", "aigenerated", "ai_generated", "aiimage", "aiimages",
    "aiart", "aiartdata", "generated", "generatedimages", "gan", "gans",
    "synthetic", "syntheticimages", "artificial", "manipulated", "deepfake",
    "deepfakes", "diffusion", "midjourney", "sd", "stylegan", "spoof", "1",
    "yes", "aiartwork",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def classify_relpath(rel: str) -> str | None:
    """Label an image path by its deepest unambiguous folder name.

    Walks the parent folders from deepest to shallowest and returns the first
    exact (normalised) real/fake match. Combined folder names such as
    ``real_vs_fake`` match neither set, so their child ``real``/``fake`` folder
    wins. Unknown paths return ``None`` (never mislabelled).
    """
    parts = [p for p in re.split(r"[\\/]+", rel) if p]
    for part in reversed(parts[:-1]):
        n = _norm(part)
        if n in FAKE_NAMES:
            return "fake"
        if n in REAL_NAMES:
            return "real"
    return None


# ---------------------------------------------------------------------------
# Curated sources (sizes are the reported Kaggle/HF totals, used for the cap).
# ---------------------------------------------------------------------------
KAGGLE_SOURCES = [
    {"slug": "birdy654/cifake-real-and-ai-generated-synthetic-images",
     "size_gb": 0.11, "note": "CIFAKE: real photos vs AI (32x32)."},
    {"slug": "ciplab/real-and-fake-face-detection",
     "size_gb": 0.23, "note": "Real vs GAN-generated faces (600x600)."},
    {"slug": "manjilkarki/deepfake-and-real-images",
     "size_gb": 1.80, "note": "Real vs deepfake faces."},
    {"slug": "xhlulu/140k-real-and-fake-faces",
     "size_gb": 4.04, "note": "140k real (FFHQ) vs fake (StyleGAN) faces."},
    {"slug": "splcher/animefacedataset",
     "size_gb": 0.42, "note": "Anime faces (AI-ish style) -> fake."},
    {"slug": "alessandrasala79/ai-vs-human-generated-dataset",
     "size_gb": 11.69, "note": "AI vs human images (labelled train.csv).",
     "csv": "train.csv", "img_col": 1, "label_col": 2, "fake_label": "1"},
]

HF_SOURCES = [
    {"repo_id": "Hemg/AI-Generated-vs-Real-Images-Datasets",
     "size_gb": 0.25, "note": "AiArtData vs RealArt folders."},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def _dir_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _iter_images(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                full = os.path.join(dirpath, f)
                if os.path.isfile(full):
                    yield full


def _copy_image(src: str, dest_root: str, label: str, prefix: str, index: int) -> int:
    ext = (os.path.splitext(src)[1].lower() or ".jpg")
    if ext not in IMAGE_EXTS:
        ext = ".jpg"
    dest = os.path.join(dest_root, label, f"{prefix}_{label}_{index:07d}{ext}")
    try:
        size = os.path.getsize(src)
        shutil.copy2(src, dest)
        return size
    except OSError as exc:  # noqa: BLE001
        logger.debug("copy failed %s: %s", src, exc)
        return 0


def _load_manifest(path: str) -> dict:
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            logger.warning("manifest unreadable, starting fresh: %s", path)
    return {"sources": {}, "total_bytes": 0}


def _save_manifest(path: str, mf: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(mf, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Kaggle
# ---------------------------------------------------------------------------
def _kaggle_authenticate():
    write_kaggle_json()
    resolve_credentials()
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()
    return api


def _download_kaggle_folder(api, entry, dest_root, prefix):
    slug = entry["slug"]
    # Keep any previously downloaded zip so an interrupted run resumes without
    # re-downloading (the Kaggle client skips existing archives when force=False).
    staging = os.path.join(dest_root, "_staging", prefix)
    os.makedirs(staging, exist_ok=True)
    try:
        logger.info("[kaggle] downloading %s ...", slug)
        api.dataset_download_files(slug, path=staging, unzip=True, quiet=False, force=False)
        counts = {"real": 0, "fake": 0}
        written = 0
        for src in _iter_images(staging):
            rel = os.path.relpath(src, staging)
            label = classify_relpath(rel)
            if label is None:
                continue
            size = _copy_image(src, dest_root, label, prefix, counts[label])
            if size:
                counts[label] += 1
                written += size
        logger.info("[kaggle] %s -> real=%d fake=%d (%s)", slug, counts["real"],
                    counts["fake"], _human(written))
        return written, counts
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _download_kaggle_csv(api, entry, dest_root, prefix):
    slug = entry["slug"]
    staging = os.path.join(dest_root, "_staging", prefix)
    os.makedirs(staging, exist_ok=True)
    try:
        logger.info("[kaggle] downloading %s (csv-labelled) ...", slug)
        api.dataset_download_files(slug, path=staging, unzip=True, quiet=False, force=False)
        import csv as _csv

        csv_path = os.path.join(staging, entry["csv"])
        if not os.path.isfile(csv_path):
            candidates = [os.path.join(r, f)
                          for r, _d, fs in os.walk(staging) for f in fs
                          if f.lower() == entry["csv"].lower()]
            if not candidates:
                raise RuntimeError(f"label csv {entry['csv']} not found in {slug}")
            csv_path = candidates[0]
        img_col = entry.get("img_col", 1)
        label_col = entry.get("label_col", 2)
        fake_label = str(entry.get("fake_label", "1"))
        labels = {}
        with open(csv_path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = _csv.reader(fh)
            header = next(reader, None)
            for row in reader:
                if len(row) <= max(img_col, label_col):
                    continue
                name = os.path.basename(row[img_col].strip().replace("\\", "/"))
                labels[name] = "fake" if row[label_col].strip() == fake_label else "real"
        counts = {"real": 0, "fake": 0}
        written = 0
        for src in _iter_images(staging):
            label = labels.get(os.path.basename(src))
            if label is None:
                continue
            size = _copy_image(src, dest_root, label, prefix, counts[label])
            if size:
                counts[label] += 1
                written += size
        logger.info("[kaggle] %s -> real=%d fake=%d (%s)", slug, counts["real"],
                    counts["fake"], _human(written))
        return written, counts
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ---------------------------------------------------------------------------
# Hugging Face
# ---------------------------------------------------------------------------
def _download_hf(entry, dest_root, prefix):
    from huggingface_hub import hf_hub_download, list_repo_tree, RepoFile

    repo = entry["repo_id"]
    token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN") or None
    staging = os.path.join(dest_root, "_staging", prefix)
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    try:
        entries = list_repo_tree(repo, recursive=True, repo_type="dataset", token=token)
        paths = [f.path for f in entries
                 if isinstance(f, RepoFile)
                 and os.path.splitext(f.path)[1].lower() in IMAGE_EXTS]
        if not paths:
            logger.warning("[hf] %s: no image files found.", repo)
            return 0, {"real": 0, "fake": 0}
        logger.info("[hf] %s: %d image files listed, downloading ...", repo, len(paths))
        counts = {"real": 0, "fake": 0}
        written = 0
        for path in paths:
            label = classify_relpath(path)
            if label is None:
                continue
            try:
                local = hf_hub_download(repo_id=repo, filename=path,
                                        repo_type="dataset", token=token)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[hf] skip %s: %s", path, exc)
                continue
            size = _copy_image(local, dest_root, label, prefix, counts[label])
            if size:
                counts[label] += 1
                written += size
        logger.info("[hf] %s -> real=%d fake=%d (%s)", repo, counts["real"],
                    counts["fake"], _human(written))
        return written, counts
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def _prepare_root(root: str) -> None:
    for label in ("real", "fake"):
        os.makedirs(os.path.join(root, label), exist_ok=True)


def run(root: str = DEFAULT_ROOT, max_gb: float = DEFAULT_MAX_GB,
        only: list[str] | None = None) -> dict:
    _prepare_root(root)
    manifest_path = os.path.join(root, "manifest.json")
    manifest = _load_manifest(manifest_path)
    used = int(manifest.get("total_bytes", 0))
    max_bytes = int(max_gb * (1024 ** 3))

    # Recompute used from disk on first run for accuracy.
    if used == 0:
        for label in ("real", "fake"):
            used += _dir_bytes(os.path.join(root, label))
        manifest["total_bytes"] = used

    logger.info("target root: %s", root)
    logger.info("already on disk: %s (cap %.1f GB)", _human(used), max_gb)

    kaggle_api = None
    sources = ([{"type": "kaggle", **e} for e in KAGGLE_SOURCES]
               + [{"type": "hf", **e} for e in HF_SOURCES])
    for entry in sources:
        key = entry.get("slug") or entry.get("repo_id")
        if only and key not in only:
            continue
        prefix = re.sub(r"[^a-z0-9]+", "_", key.split("/")[-1].lower())[:40]
        done = manifest["sources"].get(key)
        if done and done.get("done"):
            logger.info("[skip] %s already downloaded (%s)", key,
                        _human(done.get("bytes", 0)))
            continue
        if used >= max_bytes:
            logger.info("[cap] reached %.1f GB - stopping.", max_gb)
            break
        remaining = max_bytes - used
        need = int(entry.get("size_gb", 0) * (1024 ** 3))
        # Allow the first source to exceed the cap; skip later ones that don't fit.
        if need > remaining and used > 0:
            logger.info("[cap] %s (~%.2f GB) does not fit in %.1f GB remaining - stopping.",
                        key, entry.get("size_gb", 0), remaining / 1024 ** 3)
            break
        started = time.time()
        try:
            if entry["type"] == "kaggle":
                if kaggle_api is None:
                    kaggle_api = _kaggle_authenticate()
                if entry.get("csv"):
                    written, counts = _download_kaggle_csv(kaggle_api, entry, root, prefix)
                else:
                    written, counts = _download_kaggle_folder(kaggle_api, entry, root, prefix)
            else:
                written, counts = _download_hf(entry, root, prefix)
        except Exception as exc:  # noqa: BLE001
            logger.warning("source %s failed: %s", key, exc)
            manifest["sources"][key] = {"done": False, "error": str(exc)[:200]}
            _save_manifest(manifest_path, manifest)
            continue
        used += written
        manifest["total_bytes"] = used
        manifest["sources"][key] = {
            "done": True, "bytes": written, "counts": counts,
            "seconds": round(time.time() - started, 1),
        }
        _save_manifest(manifest_path, manifest)
        logger.info("[ok] %s: %s total on disk (%.1f GB cap)",
                    key, _human(used), max_gb)

    logger.info("finished. total on disk: %s (%d sources recorded)",
                _human(used), len(manifest["sources"]))
    return manifest


def _setup_logging(root: str, verbose: bool) -> None:
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        os.makedirs(root, exist_ok=True)
        handlers.append(logging.FileHandler(os.path.join(root, "download.log"),
                                            encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers, force=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--max-gb", type=float, default=DEFAULT_MAX_GB)
    parser.add_argument("--only", nargs="*", default=None,
                        help="Only these slugs / repo ids.")
    parser.add_argument("--list", action="store_true", help="List sources and exit.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.list:
        for e in KAGGLE_SOURCES:
            print(f"[kaggle] {e['slug']:55s} {e['size_gb']:6.2f} GB  {e['note']}")
        for e in HF_SOURCES:
            print(f"[hf]     {e['repo_id']:55s} {e['size_gb']:6.2f} GB  {e['note']}")
        return 0

    _setup_logging(args.root, args.verbose)
    run(root=args.root, max_gb=args.max_gb, only=args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
