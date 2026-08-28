"""Reference comparison for the deepfake scan.

On first use it pulls a small sample of real + fake media (images or audio)
from Kaggle into a temp dir (auto-deleted), builds per-class feature
distributions, and scores later scans against them. The profiles are cached
in-process, so webcam, URL and repeated scans never re-download.

Usage:
    from services.kaggle_reference import kaggle_reference
    kaggle_reference.ensure_built()                  # kick off a background build
    ref = kaggle_reference.score(features)           # image features (default)
    ref = kaggle_reference.score(features, media_type="audio")
"""
import logging
import os
import tempfile
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

from config import Config

logger = logging.getLogger("kaggle_reference")

# Feature keys used for the reference comparison (must match the analyzers).
_KEYS_BY_MEDIA = {
    "image": [
        "error_level_analysis",
        "texture_uniformity",
        "recompression_similarity",
        "color_flatness",
        "histogram_entropy",
    ],
    "audio": [
        "spectral_flatness",
        "zero_crossing_rate",
        "mfcc_variance",
        "rms_energy",
    ],
}
_DEFAULT_MEDIA = "image"


class _Profile:
    """Per-class feature statistics (mean / std per feature)."""

    def __init__(self, slug):
        self.slug = slug
        self.created_at = time.time()
        self.classes = {}   # "real" / "fake" -> {feature: (mean, std)}
        self.samples = {}   # "real" / "fake" -> n


class KaggleReference:
    def __init__(self):
        self._profiles = {}     # media_type -> _Profile
        self._status = {}       # media_type -> idle | building | ready | error
        self._error = {}        # media_type -> message
        self._lock = threading.Lock()
        self._cache = {}

    # ------------------------------------------------------------------ API
    @property
    def status(self):
        return self._status.get(_DEFAULT_MEDIA, "idle")

    def error(self):
        return self._error.get(_DEFAULT_MEDIA, "")

    def ensure_built(self, media_type=_DEFAULT_MEDIA):
        """Trigger a build in a background thread if one hasn't run yet."""
        with self._lock:
            if self._status.get(media_type) in (None, "idle"):
                self._status[media_type] = "building"
                threading.Thread(target=self._build, args=(media_type,),
                                 daemon=True).start()

    def score(self, features, media_type=_DEFAULT_MEDIA):
        """Return reference info for a feature dict, or None if unready."""
        profile = self._profiles.get(media_type)
        if profile is None or features is None:
            return None
        keys = _KEYS_BY_MEDIA.get(media_type, _KEYS_BY_MEDIA[_DEFAULT_MEDIA])
        dists = {}
        for cls, stats in profile.classes.items():
            terms = []
            for key in keys:
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
            "media_type": media_type,
            "dataset": profile.slug,
            "fake_likelihood": round(fake_likelihood, 4),
            "closer_to": "fake" if fake_likelihood >= 0.5 else "real",
            "samples": dict(profile.samples),
            "created_at": int(profile.created_at),
        }

    def available(self, media_type=_DEFAULT_MEDIA):
        return (self._status.get(media_type) == "ready"
                and media_type in self._profiles)

    # ------------------------------------------------------------- internals
    def _build(self, media_type):
        try:
            profile = self._build_profile(media_type)
            with self._lock:
                self._profiles[media_type] = profile
                self._status[media_type] = "ready"
            logger.info("Kaggle reference profile ready (dataset=%s, media=%s).",
                        profile.slug, media_type)
        except Exception as exc:  # noqa: BLE001
            self._error[media_type] = str(exc)
            with self._lock:
                self._status[media_type] = "error"
            logger.warning("Kaggle reference build failed (%s): %s", media_type, exc)

    def _build_profile(self, media_type):
        from ml.kaggle_pipeline import resolve_credentials, write_kaggle_json

        # Force credentials resolution so the Kaggle client is authenticated.
        write_kaggle_json()
        resolve_credentials()

        slug = _reference_slug(media_type)
        n = Config.KAGGLE_REFERENCE_SAMPLE_SIZE
        keys = _KEYS_BY_MEDIA.get(media_type, _KEYS_BY_MEDIA[_DEFAULT_MEDIA])

        profile = _Profile(slug)
        with _temp_reference_media(media_type, slug, n) as (per_class, _parent):
            for cls, paths in per_class.items():
                vectors = [_features(path, media_type) for path in paths]
                vectors = [v for v in vectors if v is not None]
                profile.samples[cls] = len(vectors)
                stats = defaultdict(list)
                for v in vectors:
                    for key in keys:
                        stats[key].append(v[key])
                profile.classes[cls] = {
                    key: _mean_std(values) for key, values in stats.items()
                }
        if profile.samples.get("fake", 0) < 5 or profile.samples.get("real", 0) < 5:
            raise RuntimeError("Not enough labelled samples fetched from Kaggle.")
        return profile


def _reference_slug(media_type=_DEFAULT_MEDIA):
    from ml.data_config import get_registry

    for entry in get_registry():
        if entry["media"] == media_type:
            return entry["slug"]
    raise RuntimeError(f"No {media_type} dataset configured in the Kaggle registry.")


# Parent-folder keywords used to split a raw Kaggle dataset into class labels.
_REAL_TOKENS = ("real", "bonafide", "genuine", "original", "human", "natural")
_FAKE_TOKENS = ("fake", "spoof", "cloned", "clone", "synthetic", "generated", "ai_")
# Casual/genre folders that mean "just clips", not a class. Audio datasets
# usually group synthetic voices by TTS-engine folder and real voices under a
# "real" folder, so an unmatched engine folder is treated as fake there.
_NEUTRAL_FOLDERS = {"clips", "audio", "samples", "data", "wav", "files", "dataset", "train", "test"}


def _label(name, media_type=_DEFAULT_MEDIA):
    """Return 'fake' / 'real' from the file's parent folder (best-effort)."""
    folder = os.path.basename(os.path.dirname(name)).lower()
    if any(tok in folder for tok in _REAL_TOKENS):
        return "real"
    if any(tok in folder for tok in _FAKE_TOKENS):
        return "fake"
    if media_type == "audio" and folder and folder not in _NEUTRAL_FOLDERS:
        return "fake"  # unmatched top-level dir in an audio dataset = TTS engine
    return None


def _features(path, media_type=_DEFAULT_MEDIA):
    """Compute the analyzer feature vector for a reference file (best-effort)."""
    try:
        if media_type == "audio":
            from services.analyze_audio import _librosa_features
            feats, ok = _librosa_features(path)
            return feats if ok else None
        from PIL import Image

        with Image.open(path) as img:
            img.verify()
        from services.analyze_image import feature_vector
        return feature_vector(Image.open(path).convert("RGB"))
    except Exception:  # noqa: BLE001
        return None


def _mean_std(values):
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return round(mean, 4), round(max(var, 0.0) ** 0.5, 4)


@contextmanager
def _temp_reference_media(media_type, slug, n):
    """Download n real + n fake samples straight from Kaggle into a temp dir.

    Yields ({'fake': [...paths], 'real': [...]}, temp_dir). The temp dir (and
    every downloaded file) is deleted when the block exits, so nothing from the
    raw dataset ever persists in the project.
    """
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()

    # List files to discover real/fake paths. Judge by the parent folder, not
    # the full path - dataset roots often contain "real_and_fake".
    fake_paths, real_paths = [], []
    page_token = None
    for _ in range(60):
        resp = api.dataset_list_files(slug, page_size=1000, page_token=page_token)
        files = getattr(resp, "dataset_files", None) or []
        if not files:
            break
        for f in files:
            name = getattr(f, "name", "") or ""
            cls = _label(name, media_type)
            if cls == "fake":
                fake_paths.append(name)
            elif cls == "real":
                real_paths.append(name)
        page_token = getattr(resp, "next_page_token", None)
        if not page_token:
            break
        if len(fake_paths) >= n and len(real_paths) >= n:
            break

    if not fake_paths or not real_paths:
        raise RuntimeError(
            f"Could not locate real/fake labelled files in Kaggle dataset {slug}.")

    fmt = "audio sample" if media_type == "audio" else "image"
    timeout = 15 if media_type == "audio" else 12
    parent = tempfile.mkdtemp(prefix="marianalysis_ref_")
    out = {"fake": [], "real": []}
    try:
        for cls, paths in (("fake", fake_paths), ("real", real_paths)):
            candidates = paths[: n * 3]
            for name in candidates:
                if len(out[cls]) >= n:
                    break
                try:
                    _download_with_timeout(api, slug, name, parent, timeout=timeout)
                    claimed = set(out["fake"]) | set(out["real"])
                    cand = _locate_download(parent, name, claimed)
                    if cand:
                        out[cls].append(cand)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("skip %s: %s", name, exc)
        if not out["fake"] or not out["real"]:
            raise RuntimeError(f"Kaggle sample download produced no {fmt}s.")
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


def _locate_download(parent, name, claimed=None):
    """Locate a just-downloaded file anywhere under ``parent`` (Kaggle nests).

    Prefers the file whose basename matches, otherwise the newest unclaimed file.
    Returns None when nothing usable is found.
    """
    claimed = set(claimed or ())
    target = os.path.basename(name).lower()
    best, best_mtime = None, 0.0
    for root, _dirs, files in os.walk(parent):
        for fname in files:
            full = os.path.join(root, fname)
            if full in claimed or not (os.path.isfile(full) and os.path.getsize(full) > 0):
                continue
            if fname.lower() == target:
                return full
            mtime = os.path.getmtime(full)
            if mtime > best_mtime:
                best, best_mtime = full, mtime
    return best


kaggle_reference = KaggleReference()
