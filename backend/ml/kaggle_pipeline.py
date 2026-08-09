"""On-demand Kaggle dataset fetcher (temp cache only, nothing persists).

Usage:
    with stream_dataset("user/dataset") as folder:
        ...use files inside folder...   # temp dir is auto-cleaned

Credentials come from KAGGLE_USERNAME/KAGGLE_KEY, KAGGLE_JSON_PATH, or
~/.kaggle/kaggle.json, and are written to ~/.kaggle/kaggle.json so the Kaggle
client never needs manual re-authentication.
"""
import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from contextlib import contextmanager

from config import Config
from ml.data_config import get_registry

logger = logging.getLogger("kaggle_pipeline")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Persistent cache location (optional). On-demand mode ignores this.
DATASET_ROOT = os.path.join(Config.BASE_DIR, "ml", "datasets")


def _ensure_dirs():
    os.makedirs(DATASET_ROOT, exist_ok=True)


def resolve_credentials():
    """Return (username, key) or raise with helpful instructions."""
    username = os.environ.get("KAGGLE_USERNAME", "").strip()
    key = os.environ.get("KAGGLE_KEY", "").strip()
    if username and key:
        return username, key

    json_path = os.environ.get("KAGGLE_JSON_PATH", "").strip()
    candidates = [json_path] if json_path else []
    candidates += [os.path.join(os.path.expanduser("~"), ".kaggle", "kaggle.json")]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return data.get("username", ""), data.get("key", "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not read kaggle.json at %s: %s", path, exc)

    raise RuntimeError(
        "Kaggle credentials not found. Add KAGGLE_USERNAME and KAGGLE_KEY to your "
        ".env (get an API key from https://www.kaggle.com/settings -> API). The "
        "pipeline stores them in ~/.kaggle/kaggle.json automatically."
    )


def write_kaggle_json():
    """Persist env-based credentials to the standard kaggle.json location."""
    username, key = resolve_credentials()
    kaggle_dir = os.path.join(os.path.expanduser("~"), ".kaggle")
    os.makedirs(kaggle_dir, exist_ok=True)
    kaggle_path = os.path.join(kaggle_dir, "kaggle.json")
    existing = {}
    if os.path.isfile(kaggle_path):
        try:
            with open(kaggle_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except Exception:  # noqa: BLE001
            existing = {}
    if existing.get("username") != username or existing.get("key") != key:
        with open(kaggle_path, "w", encoding="utf-8") as fh:
            json.dump({"username": username, "key": key}, fh)
        try:
            os.chmod(kaggle_path, 0o600)
        except OSError:
            pass
        logger.info("Wrote Kaggle credentials to %s", kaggle_path)
    return kaggle_path


def _api():
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def _extract_download(files, tmp_dir, dest_dir):
    """Move/extract the downloaded files from tmp_dir into dest_dir.

    Newer kaggle client versions return ``None`` from dataset_download_files,
    so if no file list is given we scan ``tmp_dir`` for the downloaded zip
    (or any file) instead.
    """
    os.makedirs(dest_dir, exist_ok=True)
    if not files:
        files = []
        for f in os.listdir(tmp_dir):
            full = os.path.join(tmp_dir, f)
            if os.path.isfile(full) and os.path.getsize(full) > 0:
                files.append(full)
    files = [f for f in files if f and os.path.isfile(f) and os.path.getsize(f) > 0]

    zips = [f for f in files if f.lower().endswith(".zip")]
    if zips:
        with zipfile.ZipFile(zips[0], "r") as zf:
            zf.extractall(dest_dir)
        return True
    # Some datasets download as plain files.
    for f in files:
        shutil.copy(f, os.path.join(dest_dir, os.path.basename(f)))
    return bool(files)


@contextmanager
def stream_dataset(slug, session_cache=None, force=False):
    """Download + extract one Kaggle dataset, yield its local folder, auto-clean.

    ``session_cache`` (optional dict) keeps one download per session so a
    training run that calls this multiple times reuses the same temp folder
    instead of re-downloading. The cache is deleted when the process exits
    (TemporaryDirectory) - nothing persists in the project.
    """
    write_kaggle_json()

    # Reuse the in-session cache so callers don't re-download mid-run.
    if session_cache is not None:
        cached = session_cache.get(slug)
        if cached and os.path.isdir(cached) and not force:
            logger.info("Reusing in-session Kaggle cache for %s", slug)
            yield cached
            return

    logger.info("Fetching dataset directly from Kaggle: %s", slug)
    parent = tempfile.mkdtemp(prefix="marianalysis_kaggle_")
    try:
        tmp = os.path.join(parent, "dl")
        os.makedirs(tmp, exist_ok=True)
        files = _api().dataset_download_files(slug, path=tmp, unzip=False)
        dest = os.path.join(parent, "data")
        ok = _extract_download(files, tmp, dest)
        if not ok:
            raise RuntimeError(f"Dataset {slug} produced no files.")
        if session_cache is not None:
            session_cache[slug] = dest
        logger.info("Dataset %s ready at %s", slug, dest)
        yield dest
    finally:
        if session_cache is None:
            shutil.rmtree(parent, ignore_errors=True)
            logger.info("Temp cache cleaned for %s", slug)


def stream_media(media_type, session_cache=None, force=False):
    """Stream the first configured dataset for a media type (on-demand)."""
    for entry in get_registry():
        if entry["media"] == media_type:
            return stream_dataset(entry["slug"], session_cache=session_cache, force=force)
    raise RuntimeError(f"No dataset configured for media type '{media_type}'.")


def sync_all(force=False, media_type=None, keep=False):
    """Optional: download every dataset into a persistent local cache.

    Default keeps the project clean (temp download then delete). With
    ``keep=True`` the data stays under ``ml/datasets`` for offline reuse.
    """
    _ensure_dirs()
    try:
        write_kaggle_json()
    except RuntimeError as exc:
        logger.error(str(exc))
        return False

    all_ok = True
    entries = get_registry()
    if media_type:
        entries = [e for e in entries if e["media"] == media_type]

    session_cache = {} if keep else None
    for entry in entries:
        try:
            with stream_dataset(entry["slug"], session_cache=session_cache, force=force) as src:
                if keep:
                    dest = os.path.join(DATASET_ROOT, entry["dir"])
                    shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(src, dest)
                    logger.info("Persisted %s -> %s", entry["slug"], dest)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", entry["slug"], exc)
            if entry.get("required", True):
                all_ok = False

    return all_ok


def list_datasets():
    for entry in get_registry():
        print(f"{entry['slug']:55s} [{entry['media']}] {entry.get('note','')}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MariAnalysis Kaggle data pipeline (on-demand, no persistent storage)")
    parser.add_argument("--keep", action="store_true",
                        help="Persist datasets under ml/datasets for offline reuse.")
    parser.add_argument("--media", choices=["image", "video", "audio", "text"],
                        help="Only fetch datasets for one media type.")
    parser.add_argument("--list", action="store_true", help="Show configured datasets.")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if cached.")
    args = parser.parse_args()

    if args.list:
        list_datasets()
        sys.exit(0)

    ok = sync_all(force=args.force, media_type=args.media, keep=args.keep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
