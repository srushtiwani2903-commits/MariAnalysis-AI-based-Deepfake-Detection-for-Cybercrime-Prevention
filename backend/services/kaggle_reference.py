"""Reference comparison for the deepfake scan.

On first use it pulls a small sample of real + fake media (images or audio)
from Kaggle into a temp dir (auto-deleted), builds per-class feature
distributions, and scores later scans against them. The profiles are cached
in-process, so webcam, URL and repeated scans never re-download. When a local
real/fake image dataset is present on disk (see Config.IMAGE_REFERENCE_DATASET_PATH)
the image profile is built from ALL of those images and cached to disk, so the
full dataset is used for every image scan without re-building on each restart.

Usage:
    from services.kaggle_reference import kaggle_reference
    kaggle_reference.ensure_built()                  # kick off a background build
    ref = kaggle_reference.score(features)           # image features (default)
    ref = kaggle_reference.score(features, media_type="audio")
"""
import json
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
    "video": [
        "face_presence",
        "synthetic_smoothness",
        "temporal_flicker",
        "byte_hash_drift",
        "compression_ratio",
        "texture_uniformity",
        "error_level_analysis",
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

    # ------------------------------------------------ persistence
    def to_dict(self):
        return {
            "slug": self.slug,
            "created_at": self.created_at,
            "samples": dict(self.samples),
            "classes": {
                cls: {feat: list(stats) for feat, stats in class_stats.items()}
                for cls, class_stats in self.classes.items()
            },
        }

    @classmethod
    def from_dict(cls, data):
        profile = cls(data["slug"])
        profile.created_at = data.get("created_at", time.time())
        profile.samples = dict(data.get("samples", {}))
        profile.classes = {
            cls: {
                feat: (tuple(v) if isinstance(v, list) else v)
                for feat, v in class_stats.items()
            }
            for cls, class_stats in data.get("classes", {}).items()
        }
        return profile


def _profile_cache_path(media_type):
    """Disk cache location for a local reference profile."""
    folder = os.path.join(Config.BASE_DIR, "ml", "datasets", "_reference_cache")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{media_type}_profile.json")


class KaggleReference:
    def __init__(self):
        self._profiles = {}     # media_type -> _Profile
        self._status = {}       # media_type -> idle | building | ready | error
        self._error = {}        # media_type -> message
        self._lock = threading.Lock()
        self._cache = {}
        self._load_disk_cache()

    def _load_disk_cache(self):
        """Load any previously built local reference profile from disk."""
        for media_type in (m for m in _KEYS_BY_MEDIA):  # noqa: C416
            path = _profile_cache_path(media_type)
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as fh:
                        profile = _Profile.from_dict(json.load(fh))
                    # Only auto-load the cache when it matches the local dataset
                    # source; otherwise ignore it (will rebuild).
                    if _is_local_source(profile.slug):
                        self._profiles[media_type] = profile
                        self._status[media_type] = "ready"
                        logger.info("Loaded cached local reference profile (%s).",
                                    profile.slug)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load reference cache %s: %s", path, exc)

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
            self._save_disk_cache(profile, media_type)
            logger.info("Kaggle reference profile ready (dataset=%s, media=%s).",
                        profile.slug, media_type)
        except Exception as exc:  # noqa: BLE001
            self._error[media_type] = str(exc)
            with self._lock:
                self._status[media_type] = "error"
            logger.warning("Kaggle reference build failed (%s): %s", media_type, exc)

    def _save_disk_cache(self, profile, media_type):
        """Persist a local (non-Kaggle) profile so restarts skip the rebuild."""
        try:
            if _is_local_source(profile.slug):
                path = _profile_cache_path(media_type)
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(profile.to_dict(), fh)
                logger.info("Saved local reference profile to %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save reference cache: %s", exc)

    def _build_profile(self, media_type):
        # Local dataset mode (image scans compare against a real/fake folder
        # you already have on disk instead of hitting Kaggle).
        local_root = _local_dataset_root(media_type)
        if local_root:
            return self._build_profile_from_local(media_type, local_root)

        # Video scans are compared against the multi-source pipeline corpus
        # (Kaggle + Hugging Face + Google Drive), so a video profile is built
        # there instead of forcing a raw Kaggle sample fetch.
        if media_type == "video":
            return self._build_video_profile()

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

    def _build_video_profile(self):
        """Build the video reference profile from the pipeline corpus.

        ``ml.video_pipeline.fetch_reference_videos`` pulls a labelled real/fake
        sample across Kaggle / Hugging Face / Google Drive into a temp cache
        (auto-deleted), and every later user upload is scored against these
        per-class distributions. User uploads are never part of the corpus.
        """
        from ml.video_pipeline import fetch_reference_videos

        n = Config.VIDEO_REFERENCE_SAMPLE_SIZE
        keys = _KEYS_BY_MEDIA["video"]
        profile = _Profile("pipeline:video")
        with fetch_reference_videos(n) as (per_class, _parent):
            for cls, paths in per_class.items():
                vectors = [_features(path, "video") for path in paths]
                vectors = [v for v in vectors if v is not None]
                profile.samples[cls] = len(vectors)
                stats = defaultdict(list)
                for v in vectors:
                    for key in keys:
                        stats[key].append(v[key])
                profile.classes[cls] = {
                    key: _mean_std(values) for key, values in stats.items()
                }
        if profile.samples.get("fake", 0) < 3 or profile.samples.get("real", 0) < 3:
            raise RuntimeError(
                "Not enough labelled videos fetched from the pipeline "
                f"(real={profile.samples.get('real', 0)}, "
                f"fake={profile.samples.get('fake', 0)}). Enable at least one "
                "working source (see ml/video_pipeline.py).")
        logger.info("Video reference profile built from pipeline datasets: %s",
                    dict(profile.samples))
        return profile

    def _build_profile_from_local(self, media_type, root):
        """Build per-class feature stats from a local real/fake folder set.

        ``root`` should contain ``real/`` and ``fake/`` subfolders (optionally
        train/test/valid splits whose basenames are also matched). Uses up to
        MAX_PER_CLASS media items per class (images or videos).
        """
        keys = _KEYS_BY_MEDIA.get(media_type, _KEYS_BY_MEDIA[_DEFAULT_MEDIA])
        # Image profiles cap the corpus with IMAGE_REFERENCE_MAX_PER_CLASS,
        # video with VIDEO_REFERENCE_MAX_PER_CLASS.
        max_per_class = getattr(
            Config,
            "VIDEO_REFERENCE_MAX_PER_CLASS" if media_type == "video"
            else "IMAGE_REFERENCE_MAX_PER_CLASS",
            50000)
        exts = _VIDEO_EXTS if media_type == "video" else _IMAGE_EXTS

        def _collect(dirs):
            """Yield items up to max_per_class per class."""
            counts = {"real": 0, "fake": 0}
            for d in sorted(dirs):
                if not os.path.isdir(d):
                    continue
                cls = _label_dir(os.path.basename(d).lower(), media_type)
                if cls not in counts or counts[cls] >= max_per_class:
                    continue
                for name in sorted(os.listdir(d)):
                    if counts[cls] >= max_per_class:
                        break
                    full = os.path.join(d, name)
                    if not os.path.isfile(full):
                        continue
                    if os.path.splitext(name)[1].lower() not in exts:
                        continue
                    yield cls, full
                    counts[cls] += 1

        # Look for real/ + fake/ in the root itself and in split-like subfolders.
        seeds = []

        def _scan(folder):
            if os.path.isfile(folder):
                return
            for sub in os.listdir(folder):
                abs_sub = os.path.join(folder, sub)
                if os.path.isdir(abs_sub) and _label_dir(sub, media_type):
                    # real/ or fake/ directly
                    seeds.append(abs_sub)
                    for inner in os.listdir(abs_sub):
                        inner_path = os.path.join(abs_sub, inner)
                        if os.path.isdir(inner_path) and _label_dir(inner, media_type):
                            seeds.append(inner_path)
                elif os.path.isdir(abs_sub):
                    _scan(abs_sub)

        _scan(root)
        seeds = [s for s in seeds if os.path.isdir(s)]

        real_dirs = [s for s in seeds if _label_dir(os.path.basename(s), media_type) == "real"]
        fake_dirs = [s for s in seeds if _label_dir(os.path.basename(s), media_type) == "fake"]
        if not real_dirs or not fake_dirs:
            raise RuntimeError(
                f"No real/ and fake/ folders found under local dataset root: {root}")

        profile = _Profile(f"local:{root}")
        total = 0
        for cls, dirs in (("real", real_dirs), ("fake", fake_dirs)):
            vectors = []
            for _cls, path in _collect(dirs):
                vectors.append(_features(path, media_type))
            vectors = [v for v in vectors if v is not None]
            profile.samples[cls] = len(vectors)
            stats = defaultdict(list)
            for v in vectors:
                for key in keys:
                    stats[key].append(v[key])
            profile.classes[cls] = {
                key: _mean_std(values) for key, values in stats.items()
            }
            total += profile.samples[cls]
            logger.info("Local reference %s: %d %s %ss profiled.",
                        media_type, profile.samples[cls], cls, media_type)
        if profile.samples.get("fake", 0) < 5 or profile.samples.get("real", 0) < 5:
            raise RuntimeError("Not enough labelled samples in local dataset "
                               f"{root} (real={profile.samples.get('real', 0)}, "
                               f"fake={profile.samples.get('fake', 0)}).")
        logger.info("Local reference profile built from %d %ss in %s.",
                    total, media_type, root)
        return profile


def _is_local_source(slug):
    """True when a profile slug points at a local/pipeline dataset source.

    Both ``local:...`` and ``pipeline:...`` profiles are cached on disk so a
    restart reuses them instead of re-downloading the corpus.
    """
    return isinstance(slug, str) and (slug.startswith("local:") or slug.startswith("pipeline:"))


def _reference_slug(media_type=_DEFAULT_MEDIA):
    from ml.data_config import get_registry

    for entry in get_registry():
        if entry["media"] == media_type:
            return entry["slug"]
    raise RuntimeError(f"No {media_type} dataset configured in the Kaggle registry.")


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
               ".mpeg", ".mpg", ".3gp", ".3g2", ".ogv", ".wmv", ".ts", ".mts"}

# Parent-folder keywords used to split a raw Kaggle dataset into class labels.
_REAL_TOKENS = ("real", "bonafide", "genuine", "original", "human", "natural")
_FAKE_TOKENS = ("fake", "spoof", "cloned", "clone", "synthetic", "generated", "ai_")
# Video datasets organise classes differently (FF++/Celeb-DF): real clips to
# YouTube/Celeb-real/original folders, fakes under the manipulation method.
_VIDEO_REAL_TOKENS = _REAL_TOKENS + ("youtube-real", "celeb-real", "source", "video")
_VIDEO_FAKE_TOKENS = _FAKE_TOKENS + (
    "synthesis", "synthesized", "manipulated", "swap", "neuralt",
    "face2face", "deeppareid", "headreenact", "deepfakedetection")
# Casual/genre folders that mean "just clips", not a class. Audio datasets
# usually group synthetic voices by TTS-engine folder and real voices under a
# "real" folder, so an unmatched engine folder is treated as fake there.
_NEUTRAL_FOLDERS = {"clips", "audio", "samples", "data", "wav", "files", "dataset", "train", "test",
                    "videos", "images", "image", "video"}


def _tokens(media_type):
    if media_type == "video":
        return _VIDEO_REAL_TOKENS, _VIDEO_FAKE_TOKENS
    return _REAL_TOKENS, _FAKE_TOKENS


def _label_dir(folder, media_type=_DEFAULT_MEDIA):
    """Classify a folder basename as real / fake / unknown."""
    folder = (folder or "").lower()
    real_tokens, fake_tokens = _tokens(media_type)
    if any(tok in folder for tok in real_tokens):
        return "real"
    if any(tok in folder for tok in fake_tokens):
        return "fake"
    if media_type == "audio" and folder and folder not in _NEUTRAL_FOLDERS:
        return "fake"
    return None


def _local_dataset_root(media_type=_DEFAULT_MEDIA):
    """Return a local dataset folder with real/+fake/ inside, or None.

    An explicit ``<MEDIA>_REFERENCE_DATASET_PATH`` wins; otherwise the standard
    Kaggle cache + pipeline dataset locations are probed (no deep walks).
    """
    env_name = "VIDEO_REFERENCE_DATASET_PATH" if media_type == "video" \
        else "IMAGE_REFERENCE_DATASET_PATH"
    configured = getattr(Config, env_name, "") or ""
    candidates = [configured] if configured.strip() else []

    tmp_root = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    candidates += [
        os.path.join(tmp_root, "Temp", "opencode", "df_download",
                     "140k face detection datasets", "real_vs_fake", "real-vs-fake"),
        os.path.join(tmp_root, "Temp", "opencode", "df_download",
                     "140k face detection datasets", "real_vs_fake", "real-vs-fake", "train"),
        os.path.join(os.path.expanduser("~"), ".cache", "kagglehub", "datasets"),
        os.path.join(Config.BASE_DIR, "ml", "datasets"),
        os.path.join(Config.BASE_DIR, "ml", "video_datasets"),
        os.path.join(Config.BASE_DIR, "models", "datasets"),
    ]
    if media_type != "image":
        # The face-dataset candidate paths above only ever hold images.
        candidates = [c for c in candidates
                      if "real-vs-fake" not in c]

    for root in candidates:
        if root and os.path.isdir(root) and _real_fake_folders_exist(root, media_type):
            logger.info("Using local %s reference dataset: %s", media_type, root)
            return root
    return None


def _real_fake_folders_exist(root, media_type=_DEFAULT_MEDIA, depth=3):
    """True when the folder (or its split subfolders) contains real/ + fake/."""
    try:
        entries = os.listdir(root)
    except OSError:
        return False
    direct_real = any(_label_dir(e, media_type) == "real" for e in entries)
    direct_fake = any(_label_dir(e, media_type) == "fake" for e in entries)
    if direct_real and direct_fake:
        return True
    if depth <= 0:
        return False
    # Look one level deeper (e.g. Kaggle-style train/test/valid splits).
    for entry in entries:
        sub = os.path.join(root, entry)
        if os.path.isdir(sub) and not os.path.islink(sub):
            if _real_fake_folders_exist(sub, media_type, depth - 1):
                return True
    return False


def _label(name, media_type=_DEFAULT_MEDIA):
    """Return 'fake' / 'real' from the file's parent folder (best-effort)."""
    folder = os.path.basename(os.path.dirname(name)).lower()
    real_tokens, fake_tokens = _tokens(media_type)
    if any(tok in folder for tok in real_tokens):
        return "real"
    if any(tok in folder for tok in fake_tokens):
        return "fake"
    if media_type == "audio" and folder and folder not in _NEUTRAL_FOLDERS:
        return "fake"  # unmatched top-level dir in an audio dataset = TTS engine
    return None


def _features(path, media_type=_DEFAULT_MEDIA):
    """Compute the analyzer feature vector for a reference file (best-effort)."""
    try:
        if media_type == "video":
            from services.analyze_video import feature_vector as _video_features
            feats = _video_features(path)
            return feats if feats and feats.get("frame_count", 0) > 0 else None
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

    fmt = "video" if media_type == "video" else ("audio sample" if media_type == "audio" else "image")
    timeout = 60 if media_type == "video" else (15 if media_type == "audio" else 12)
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
