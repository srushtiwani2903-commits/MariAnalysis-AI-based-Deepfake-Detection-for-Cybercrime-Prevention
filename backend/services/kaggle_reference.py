"""Reference comparison for the deepfake scan.

On first use it pulls a small sample of real + fake images from Kaggle into a
temp dir (auto-deleted), builds per-class feature distributions, and scores
later scans against them. The profile is cached in-process, so webcam and URL
scans never re-download.

Usage:
    from services.kaggle_reference import kaggle_reference
    kaggle_reference.ensure_built()        # kick off a background build
    ref = kaggle_reference.score(features) # dict or None
"""
import logging
import os
import tempfile
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

from config import Config
from services.analyze_image import feature_vector

logger = logging.getLogger("kaggle_reference")

# Feature keys used for the reference comparison (must match analyze_image).
_KEYS = [
    "error_level_analysis",
    "texture_uniformity",
    "recompression_similarity",
    "color_flatness",
    "histogram_entropy",
]


class _Profile:
    """Per-class feature statistics (mean / std per feature)."""

    def __init__(self, slug):
        self.slug = slug
        self.created_at = time.time()
        self.classes = {}   # "real" / "fake" -> {feature: (mean, std)}
        self.samples = {}   # "real" / "fake" -> n


class KaggleReference:
    def __init__(self):
        self._profile = None
        self._status = "idle"          # idle | building | ready | error
        self._error = ""
        self._lock = threading.Lock()
        self._cache = {}

    # ------------------------------------------------------------------ API
    @property
    def status(self):
        return self._status

    def error(self):
        return self._error

    def ensure_built(self):
        """Trigger a build in a background thread if one hasn't run yet."""
        with self._lock:
            if self._status in ("idle",):
                self._status = "building"
                threading.Thread(target=self._build, daemon=True).start()

    def score(self, features):
        """Return reference info for an image feature dict, or None if unready."""
        profile = self._profile
        if profile is None or features is None:
            return None
        dists = {}
        for cls, stats in profile.classes.items():
            terms = []
            for key in _KEYS:
                value = features.get(key)
                mean, std = stats.get(key, (0.5, 1.0))
                if value is None or std <= 1e-9:
                    continue
                terms.append(((value - mean) / std) ** 2)
            # RMS z-distance averaged per feature, so no single low-std
            # feature dominates the comparison.
            dists[cls] = (sum(terms) / len(terms)) ** 0.5 if terms else 0.0
        if len(dists) < 2 or sum(dists.values()) <= 0:
            return None
        fake_d, real_d = dists["fake"], dists["real"]
        fake_likelihood = real_d / (real_d + fake_d) if (real_d + fake_d) > 0 else 0.5
        return {
            "status": "ready",
            "dataset": profile.slug,
            "fake_likelihood": round(fake_likelihood, 4),
            "closer_to": "fake" if fake_likelihood >= 0.5 else "real",
            "samples": dict(profile.samples),
            "created_at": int(profile.created_at),
        }

    def available(self):
        return self._status == "ready" and self._profile is not None

    # ------------------------------------------------------------- internals
    def _build(self):
        try:
            self._profile = self._build_profile()
            with self._lock:
                self._status = "ready"
            logger.info("Kaggle reference profile ready (dataset=%s).",
                        self._profile.slug)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            with self._lock:
                self._status = "error"
            logger.warning("Kaggle reference build failed: %s", exc)

    def _build_profile(self):
        from ml.kaggle_pipeline import resolve_credentials, write_kaggle_json

        # Force credentials resolution so the Kaggle client is authenticated.
        write_kaggle_json()
        resolve_credentials()

        slug = _reference_slug()
        n = Config.KAGGLE_REFERENCE_SAMPLE_SIZE

        profile = _Profile(slug)
        with _temp_reference_media(slug, n) as (per_class, _parent):
            for cls, paths in per_class.items():
                vectors = [_features(path) for path in paths]
                vectors = [v for v in vectors if v is not None]
                profile.samples[cls] = len(vectors)
                stats = defaultdict(list)
                for v in vectors:
                    for key in _KEYS:
                        stats[key].append(v[key])
                profile.classes[cls] = {
                    key: _mean_std(values) for key, values in stats.items()
                }
        if profile.samples.get("fake", 0) < 5 or profile.samples.get("real", 0) < 5:
            raise RuntimeError("Not enough labelled samples fetched from Kaggle.")
        return profile


def _reference_slug():
    from ml.data_config import get_registry

    for entry in get_registry():
        if entry["media"] == "image":
            return entry["slug"]
    raise RuntimeError("No image dataset configured in the Kaggle registry.")


def _features(path):
    """Compute the analyzer feature vector for a reference image (best-effort)."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            img.verify()
        return feature_vector(Image.open(path).convert("RGB"))
    except Exception:  # noqa: BLE001
        return None


def _mean_std(values):
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return round(mean, 4), round(max(var, 0.0) ** 0.5, 4)


@contextmanager
def _temp_reference_media(slug, n):
    """Download n real + n fake images straight from Kaggle into a temp dir.

    Yields ({'fake': [...paths], 'real': [...]}, temp_dir). The temp dir (and
    every downloaded image) is deleted when the block exits, so nothing from the
    raw dataset ever persists in the project.
    """
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()

    # List files to discover real/fake paths.
    fake_paths, real_paths = [], []
    page_token = None
    for _ in range(60):
        resp = api.dataset_list_files(slug, page_size=1000, page_token=page_token)
        files = getattr(resp, "dataset_files", None) or []
        if not files:
            break
        for f in files:
            name = getattr(f, "name", "") or ""
            low = os.path.basename(name).lower()
            folder = os.path.basename(os.path.dirname(name)).lower()
            # Judge by parent folder (training_fake / training_real), not the
            # full path - dataset roots often contain "real_and_fake".
            if "fake" in folder:
                fake_paths.append(name)
            elif "real" in folder:
                real_paths.append(name)
        page_token = getattr(resp, "next_page_token", None)
        if not page_token:
            break
        if len(fake_paths) >= n and len(real_paths) >= n:
            break

    if not fake_paths or not real_paths:
        raise RuntimeError(
            f"Could not locate real/fake labelled files in Kaggle dataset {slug}.")

    parent = tempfile.mkdtemp(prefix="marianalysis_ref_")
    out = {"fake": [], "real": []}
    try:
        for cls, paths in (("fake", fake_paths), ("real", real_paths)):
            candidates = paths[: n * 3]
            for name in candidates:
                if len(out[cls]) >= n:
                    break
                try:
                    _download_with_timeout(api, slug, name, parent, timeout=12)
                    cand = os.path.join(parent, os.path.basename(name))
                    if not (os.path.isfile(cand) and os.path.getsize(cand) > 0):
                        claimed = set(out["fake"]) | set(out["real"])
                        cand = _find_file(parent, claimed)
                    if cand:
                        out[cls].append(cand)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("skip %s: %s", name, exc)
        if not out["fake"] or not out["real"]:
            raise RuntimeError("Kaggle sample download produced no images.")
        yield out, parent
    finally:
        import shutil
        shutil.rmtree(parent, ignore_errors=True)
        logger.debug("Kaggle reference temp cache cleaned.")


def _download_with_timeout(api, slug, name, path, timeout=20):
    """Download one Kaggle file, aborting if it takes longer than ``timeout``.

    The Kaggle client offers no built-in timeout, so a slow/hanging file is
    run in a worker thread and abandoned if it exceeds the limit - the profile
    build must never stall the app.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(api.dataset_download_file, slug, name, path=path)
        try:
            future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Kaggle download timed out: {name}")


def _find_file(directory, claimed=None):
    claimed = set(claimed or ())
    best, best_mtime = None, 0.0
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if os.path.isfile(full) and os.path.getsize(full) > 0 and full not in claimed:
            mtime = os.path.getmtime(full)
            if mtime > best_mtime:
                best, best_mtime = full, mtime
    return best


kaggle_reference = KaggleReference()
