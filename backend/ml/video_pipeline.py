"""Multi-source training/testing data pipeline for video deepfake detection.

Pulls labelled real + fake videos from three independent source types:

* **Kaggle** — reuse ``ml.kaggle_pipeline.stream_dataset`` (no persistence).
* **Hugging Face** — streams labelled video datasets via ``datasets`` /
  ``huggingface_hub`` into a temp cache.
* **Google Drive** — downloads FaceForensics++ / Celeb-DF style archives via
  ``gdown`` (file IDs configured through the environment).

Videos are classified by their parent folder name (real / fake / unknown),
a balanced frame-set is extracted into ``train / val / test`` splits, and the
frames feed the frame-CNN trainer (``ml/train_video_cnn_kaggle.py``) and the
video reference profile builder. Everything lives in a temp cache unless
``--keep`` is passed; user uploads are NEVER added to this corpus.

Usage:
    python -m ml.video_pipeline --list
    python -m ml.video_pipeline --source hf --videos-per-class 6 --frames 8
    python -m ml.video_pipeline --keep                 # persist ml/video_datasets
"""
import logging
import os
import random
import shutil
import tempfile
from contextlib import contextmanager

from config import Config

logger = logging.getLogger("video_pipeline")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
              ".mpeg", ".mpg", ".3gp", ".3g2", ".ogv", ".wmv", ".ts", ".mts"}

SUPPORTED_SOURCES = ("kaggle", "huggingface", "google")

# ---------------------------------------------------------------------------
# Source registry. ``required`` marks sources whose absence should abort a
# build; everything else degrades to a warning. Google entries are only
# enabled when their Drive ID is configured (approval-form datasets).
# ---------------------------------------------------------------------------
VIDEO_SOURCES = [
    {
        "source": "kaggle",
        "name": "unidpro/deepfake-videos-dataset",
        "required": False,
        "note": "Real short clips (video/) + AI-face-swapped clips (deepfake/).",
    },
    {
        "source": "kaggle",
        "name": "nanduncs/1000-videos-split",
        "required": False,
        "note": "FaceForensics++ + Celeb-DF combined: 200 real / 200 fake.",
    },
    {
        "source": "kaggle",
        "name": "simongraves/deepfake-dataset",
        "required": False,
        "note": "10k+ videos with AI-generated faces (video/ real, deepfake/ fake).",
    },
    {
        "source": "huggingface",
        "name": "KhunPop/deepfake",
        "required": False,
        "note": "3.3k real/fake clips split into combined_data/{train,val}/{real,fake} "
                "folders (in-repo mp4 blobs, no auth).",
    },
    {
        "source": "huggingface",
        "name": "belkhir-nacim/deepfake-videos",
        "required": False,
        "note": "Unified 913k-video corpus - clips are public, the label is "
                "encoded in each filename (real_audio_real_visual / "
                "fake_audio_fake_visual), probed via shard folders.",
    },
    {
        "source": "google",
        "name": "faceforensics++",
        "required": False,
        "drive_id_env": "VIDEO_GOOGLE_FFPP_DRIVE_ID",
        "note": "FF++ real + Deepfakes/Face2Face/FaceSwap manipulation videos.",
    },
    {
        "source": "google",
        "name": "celeb-df-v2",
        "required": False,
        "drive_id_env": "VIDEO_GOOGLE_CELEBDF_DRIVE_ID",
        "note": "Celeb-DF v2 real interviews + synthesized swaps (approval form).",
    },
]


def list_sources():
    for entry in VIDEO_SOURCES:
        env = entry.get("drive_id_env")
        configured = (not env) or bool(getattr(Config, env, ""))
        print(f"[{entry['source']:11s}] {entry['name']:35s} "
              f"{'ON' if configured else 'off (set ' + env + ')'}: {entry['note']}")


# ---------------------------------------------------------------------------
# Labelling helpers
# ---------------------------------------------------------------------------
_REAL_TOKENS = ("real", "original", "bonafide", "genuine", "source",
                "youtube-real", "celeb-real", "real_task")
_FAKE_TOKENS = ("deepfake", "synthesis", "synthesized", "manipulated",
                "fake", "swap", "deepfakedetection", "faceswap", "face2face",
                "neuraltexture", "spoof", "generated", "synthetic", "_df_")
_NEUTRAL_DIRS = {"videos", "images", "image", "clips", "dataset", "data",
                 "train", "test", "val", "valid", "sample", "samples",
                 "original_sequences", "manipulated_sequences", "actors"}


def classify_dir(name):
    """Best-effort label ('real' / 'fake' / None) from a folder basename."""
    n = (name or "").lower()
    if any(tok in n for tok in _REAL_TOKENS):
        return "real"
    if any(tok in n for tok in _FAKE_TOKENS):
        return "fake"
    return None


def normalize_label(value):
    """Map a dataset label column to 'real' / 'fake' / None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "fake" if value else "real"
    s = str(value).strip().lower()
    if s in {"", "0", "1", "false", "true", "nan", "none"}:
        return ("fake" if s in {"1", "true"} else "real") if s not in {"", "nan", "none"} else None
    if any(t in s for t in _FAKE_TOKENS):
        return "fake"
    if any(t in s for t in _REAL_TOKENS):
        return "real"
    return None


def _walk_videos(root):
    """Yield absolute paths of video files under ``root`` (no deep recursion)."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                full = os.path.join(dirpath, f)
                if os.path.isfile(full) and os.path.getsize(full) > 0:
                    out.append(full)
    return out


def classify_relpath(rel, filename=None):
    """Label a repo-relative media path as 'real' / 'fake' / None.

    Label resolution order (deepfake-video layouts seen in the wild):
    * the *top-level* folder of the video (``deepfake/``, ``video/``,
      ``original_sequences/``, ``manipulated_sequences/``, ``Celeb-real/``,
      ``Celeb-synthesis/``, ...), then
    * the immediate parent folder name (``combined_data/train/real/`` style),
    * finally the filename itself (the unified HF corpus encodes the label in
      the basename, e.g. ``*_fake_audio_fake_visual__<hash>.mp4``).

    The top-level ``video/`` folder means **real** for the unidpro &
    simongraves Kaggle mirrors (``video/`` real clips, ``deepfake/`` swaps).
    Paths that can not be classified return None so callers skip them and we
    never mislabel a sample.
    """
    top = rel.split("/", 1)[0].lower()
    cls = classify_dir(top)
    if cls is None and top == "video":       # unidpro / simongraves: video/ = real
        cls = "real"
    if cls is None and "/" in rel:
        cls = classify_dir(rel.rsplit("/", 1)[-2])
    if cls is None and filename:
        cls = classify_dir(os.path.splitext(os.path.basename(filename))[0])
    return cls


def classify_videos(root):
    """Return {'real': [paths...], 'fake': [...]} from a downloaded corpus.

    Labels are resolved by ``classify_relpath`` (top-level folder -> parent
    folder -> filename). Leaves that can not be classified are skipped so we
    never mislabel a sample.
    """
    result = {"real": [], "fake": []}
    for path in _walk_videos(root):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        cls = classify_relpath(rel, filename=os.path.basename(path))
        if cls in result:
            result[cls].append(path)
    return result


# ---------------------------------------------------------------------------
# Source adapters (each fills real/ + fake/ folders under a temp root)
# ---------------------------------------------------------------------------
def _plan_per_class(taken, limit, per_class):
    """How many more clips to take for a class given limits."""
    want = per_class - taken
    if want <= 0:
        return 0
    if limit is not None and limit > 0:
        want = min(want, limit)
    return max(want, 0)


def _copy_balanced(src_cls, dest_root, per_class, slug):
    """Copy up to ``per_class`` videos of each class into dest real/fake dirs."""
    copied = {"real": 0, "fake": 0}
    for cls in ("real", "fake"):
        os.makedirs(os.path.join(dest_root, cls), exist_ok=True)
        paths = src_cls[cls]
        for i, video in enumerate(paths):
            if copied[cls] >= per_class:
                break
            ext = os.path.splitext(video)[1].lower()
            target = os.path.join(dest_root, cls, f"{slug.replace('/','__')}_{cls}_{i}{ext}")
            try:
                shutil.copy2(video, target)
                copied[cls] += 1
            except OSError as exc:  # noqa: BLE001
                logger.debug("skip copy %s: %s", video, exc)
    return copied


def _kaggle_fetch(entry, dest_root, per_class):
    from ml.kaggle_pipeline import stream_dataset
    with stream_dataset(entry["name"]) as folder:
        logger.info("Kaggle %s: fetched %s, classifying videos ...", entry["name"], folder)
        classified = classify_videos(folder)
        return _copy_balanced(classified, dest_root, per_class, entry["name"])


# ---------------------------------------------------------------------------
# Hugging Face adapters (each fills real/ + fake/ folders under a temp root)
# ---------------------------------------------------------------------------
# belkhir-nacim/deepfake-videos stores 913k clips in numbered shard folders;
# each shard mixes real + fake clips and the label lives in the filename.
UNIFIED_CORPUS_PREFIX = "videos/DDL_dataset/videos"


def _unified_corpus_paths(repo, token, per_class):
    """Probe the unified 913k-video corpus for labelled video paths.

    Returns a list of repo file paths (real + fake mixed), or ``None`` when the
    repo is not the unified-corpus layout (caller falls back to a recursive
    listing). Only a handful of shard folders are listed - we stop as soon as
    ``per_class`` videos of each class have been found - so a 913k-file repo
    costs a few cheap API calls instead of a full tree enumeration.
    """
    from huggingface_hub import RepoFile, RepoFolder, list_repo_tree  # noqa: WPS433

    try:
        top_entries = list_repo_tree(repo, path_in_repo="videos", recursive=False,
                                     repo_type="dataset", token=token)
    except Exception:  # noqa: BLE001
        return None
    if not any(isinstance(e, RepoFolder) and os.path.basename(e.path) == "DDL_dataset"
               for e in top_entries):
        return None

    picked = {"real": [], "fake": []}
    shard_idx = 0
    while len(picked["real"]) < per_class or len(picked["fake"]) < per_class:
        if shard_idx > 2000:              # safety valve past the last shard
            break
        shard = f"{shard_idx:03d}"
        try:
            entries = list_repo_tree(repo, path_in_repo=f"{UNIFIED_CORPUS_PREFIX}/{shard}",
                                     recursive=False, repo_type="dataset", token=token)
        except Exception:  # noqa: BLE001
            break                         # shard index beyond the last one
        if not entries:
            break
        for f in entries:
            if not isinstance(f, RepoFile):
                continue
            if os.path.splitext(f.path)[1].lower() not in VIDEO_EXTS:
                continue
            cls = classify_relpath(f.path, filename=f.path)
            if cls in picked and len(picked[cls]) < per_class:
                picked[cls].append(f.path)
        shard_idx += 1
    if not picked["real"] and not picked["fake"]:
        return None
    logger.info("Hugging Face %s (unified corpus): located %d real + %d fake "
                "clips after probing %d shard(s).",
                repo, len(picked["real"]), len(picked["fake"]), shard_idx)
    return picked["real"] + picked["fake"]


def _hf_fetch(entry, dest_root, per_class):
    """Pull labelled videos from a Hugging Face dataset repo.

    Two layouts are supported:

    * **Folder-structured** repos (``KhunPop/deepfake``, ...) - the repo tree
      is listed over the HF HTTP API (paginated by the SDK) and videos are
      labelled by ``classify_relpath`` (top-level / parent folder / filename).
    * **Unified corpus** (``belkhir-nacim/deepfake-videos``) - 913k clips in
      numbered shard folders whose labels are encoded in the filenames. Clips
      are public (no auth), so we probe a handful of shard folders until we have
      ``per_class`` of each class instead of enumerating the whole repo.

    Videos are downloaded via ``hf_hub_download`` (SDK cache means a re-run
    does not re-download). Public repos work with no credentials; gated/missing
    repos degrade to a warning.
    """
    from huggingface_hub import RepoFile, hf_hub_download, list_repo_tree  # noqa: WPS433

    repo = entry["name"]
    token = os.environ.get("HUGGINGFACE_TOKEN") or None

    video_paths = _unified_corpus_paths(repo, token, per_class)
    if video_paths is None:
        try:
            entries = list_repo_tree(repo, recursive=True, repo_type="dataset", token=token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Hugging Face %s not listable (gated or missing), skipping: %s",
                           repo, exc)
            return {}
        video_paths = []
        for f in entries:
            if not isinstance(f, RepoFile):
                continue
            if os.path.splitext(f.path)[1].lower() not in VIDEO_EXTS:
                continue
            video_paths.append(f.path)
            if len(video_paths) > 100000:
                logger.info("Hugging Face %s: stopped at 100k listed video files.", repo)
                break
    if not video_paths:
        logger.warning("Hugging Face %s: no video files found.", repo)
        return {}

    by_class = {"real": [], "fake": []}
    for path in video_paths:
        cls = classify_relpath(path, filename=path)
        if cls in by_class:
            by_class[cls].append(path)

    counts = {"real": 0, "fake": 0}
    for cls in counts:
        os.makedirs(os.path.join(dest_root, cls), exist_ok=True)
    random.shuffle(by_class["real"])
    random.shuffle(by_class["fake"])

    missing = {cls for cls, paths in by_class.items() if not paths}
    if missing:
        logger.warning("Hugging Face %s: no %s-labelled videos found.",
                       repo, ", ".join(sorted(missing)))

    for cls in counts:
        for path in by_class[cls]:
            if counts[cls] >= per_class:
                break
            try:
                local = hf_hub_download(repo_id=repo, filename=path,
                                        repo_type="dataset", token=token)
            except Exception as exc:  # noqa: BLE001
                # A gated repo 401s on the very first blob - do not hammer it
                # with one request per file, skip the whole source instead.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if (status == 401 or "401" in str(exc)[:120]) and counts[cls] == 0:
                    logger.warning("Hugging Face %s requires Hub access (401) for "
                                   "file blobs - skipping source.", repo)
                    return dict(counts)
                logger.debug("Hugging Face %s skip %s: %s", repo, path, exc)
                continue
            idx = counts[cls]
            ext = os.path.splitext(path)[1].lower()
            dest = os.path.join(dest_root, cls, f"hf_{idx}{ext}")
            try:
                shutil.copy2(local, dest)
                counts[cls] += 1
            except OSError as exc:  # noqa: BLE001
                logger.debug("Hugging Face %s copy skip %s: %s", repo, path, exc)
    logger.info("Hugging Face %s: sampled %s", repo, counts)
    return dict(counts)


def _google_fetch(entry, dest_root, per_class):
    """Download a Google-Drive-hosted archive (FaceForensics++ / Celeb-DF)."""
    env_name = entry.get("drive_id_env")
    drive_id = (getattr(Config, env_name, "") or "") if env_name else ""
    if not drive_id:
        raise RuntimeError(
            f"Google source {entry['name']} needs a Drive file ID in {env_name} "
            "(see config.py / .env).")
    import gdown  # noqa: WPS433
    parent = tempfile.mkdtemp(prefix="marianalysis_gdrive_")
    try:
        archive = os.path.join(parent, "download.zip")
        gdown.download(id=drive_id, output=archive, quiet=False)
        if not os.path.isfile(archive) or os.path.getsize(archive) == 0:
            raise RuntimeError("Google Drive download produced an empty file.")
        extract = os.path.join(parent, "data")
        os.makedirs(extract, exist_ok=True)
        import zipfile
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract)
        classified = classify_videos(extract)
        return _copy_balanced(classified, dest_root, per_class, entry["name"])
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _fetch_sources(dest_root, sources, per_class, hf_per_class):
    """Ask each chosen source for labelled clips. Returns summary."""
    summary = []
    for entry in VIDEO_SOURCES:
        if entry["source"] not in sources:
            continue
        limit = hf_per_class if entry["source"] == "huggingface" else per_class
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


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------
def extract_frames(video_path, out_dir, prefix, frames_per_video=None):
    """Sample evenly-spaced frames from a video into ``out_dir`` as JPEG.

    Also returns the number of frames written. Frames are downscaled to the
    longest-side target configured in VIDEO_DATASET_FRAME_SIZE for compact,
    fast-to-train datasets.
    """
    frames_per_video = frames_per_video or Config.VIDEO_DATASET_FRAMES_PER_VIDEO
    try:
        import cv2
    except Exception:  # noqa: BLE001
        logger.warning("OpenCV missing - cannot extract frames from %s", video_path)
        return 0
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    try:
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if count <= 0:
            count = 240
        step = max(1, count // max(1, frames_per_video))
        target = Config.VIDEO_DATASET_FRAME_SIZE
        written = 0
        idx = 0
        while written < frames_per_video:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                h, w = frame.shape[:2]
                scale = target / max(h, w)
                if scale < 1.0:
                    frame = cv2.resize(
                        frame, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA)
                cv2.imwrite(os.path.join(out_dir, f"{prefix}_{written:02d}.jpg"), frame,
                            [cv2.IMWRITE_JPEG_QUALITY, 88])
                written += 1
            idx += 1
        return written
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Dataset builder (train / val / test splits by video)
# ---------------------------------------------------------------------------
def _dataset_root():
    return os.path.join(Config.BASE_DIR, "ml", "video_datasets")


@contextmanager
def build_video_dataset(sources=None, videos_per_class=None, frames_per_video=None,
                        keep=False):
    """Fetch labelled videos, split by video into train/val/test frame-sets.

    Yields the dataset root:
        <root>/train/{real,fake}/*.jpg
        <root>/val/{real,fake}/*.jpg
        <root>/test/{real,fake}/*.jpg
    With ``keep=False`` the whole thing is a temp cache deleted on exit.
    """
    sources = sources or list(SUPPORTED_SOURCES)
    videos_per_class = videos_per_class or Config.VIDEO_PIPELINE_VIDEOS_PER_CLASS
    frames_per_video = frames_per_video or Config.VIDEO_DATASET_FRAMES_PER_VIDEO

    if keep:
        root = _dataset_root()
        shutil.rmtree(root, ignore_errors=True)
        os.makedirs(root, exist_ok=True)
    else:
        root = tempfile.mkdtemp(prefix="marianalysis_video_ds_")

    try:
        staging = os.path.join(root, "_staging")
        os.makedirs(staging, exist_ok=True)
        summary = _fetch_sources(staging, sources, videos_per_class,
                                 Config.VIDEO_HF_VIDEOS_PER_CLASS)
        logger.info("Pipeline summary: %s",
                    [{**s, "copied": s["copied"]} for s in summary])

        all_videos = {"real": [], "fake": []}
        for cls in all_videos:
            for f in sorted(os.listdir(os.path.join(staging, cls))):
                full = os.path.join(staging, cls, f)
                if os.path.splitext(f)[1].lower() in VIDEO_EXTS and os.path.getsize(full) > 0:
                    all_videos[cls].append(full)
        if not all_videos["real"] or not all_videos["fake"]:
            raise RuntimeError(
                "No labelled videos fetched. Enable at least one working source "
                "(currently fetched: %d real, %d fake)."
                % (len(all_videos["real"]), len(all_videos["fake"])))

        for cls, paths in all_videos.items():
            n = len(paths)
            # Always reserve a held-out test split; with few videos only train
            # is populated (evaluation then reuses the val fold).
            n_test = max(1, int(n * 0.15)) if n >= 3 else 0
            n_val = max(1, int(n * 0.15)) if n >= 3 else 0
            n_train = n - n_val - n_test
            for split in ("train", "val", "test"):
                if split == "train":
                    chunk = paths[:max(n_train, 0)]
                elif split == "val":
                    chunk = paths[n_train:n_train + n_val]
                else:
                    chunk = paths[n_train + n_val:]
                if not chunk:
                    continue
                for vid_no, video in enumerate(chunk):
                    out_dir = os.path.join(root, split, cls)
                    extract_frames(video, out_dir,
                                   prefix=f"{os.path.splitext(os.path.basename(video))[0]}_{vid_no}",
                                   frames_per_video=frames_per_video)
        total_frames = sum(
            len(files) for _dir, _sub, files in os.walk(root)
            if os.path.basename(_dir) in ("real", "fake"))
        logger.info("Dataset ready at %s (%d frames).", root, total_frames)
        yield root
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)


def fetch_reference_videos(per_class=None):
    """Pull a small labelled real/fake video sample across the sources.

    Used by the video reference-profile builder so user scans are compared
    against the pipeline corpus. Yields a dict of real/ -> [video paths];
    the caller owns the temp root (it is cleaned when ``ctx`` is exited).
    """
    per_class = per_class or Config.VIDEO_REFERENCE_SAMPLE_SIZE
    parent = tempfile.mkdtemp(prefix="marianalysis_video_ref_")
    try:
        staging = os.path.join(parent, "staging")
        os.makedirs(staging, exist_ok=True)
        _fetch_sources(staging, list(SUPPORTED_SOURCES), per_class,
                       Config.VIDEO_HF_VIDEOS_PER_CLASS)
        result = {"real": [], "fake": []}
        for cls in result:
            for f in sorted(os.listdir(os.path.join(staging, cls))):
                full = os.path.join(staging, cls, f)
                if os.path.splitext(f)[1].lower() in VIDEO_EXTS and os.path.getsize(full) > 0:
                    result[cls].append(full)
        yield result, parent
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MariAnalysis multi-source video data pipeline "
                    "(Kaggle / Hugging Face / Google Drive).")
    parser.add_argument("--list", action="store_true", help="List configured sources.")
    parser.add_argument("--source", nargs="*", default=list(SUPPORTED_SOURCES),
                        help="Sources to use: kaggle huggingface google.")
    parser.add_argument("--videos-per-class", type=int, default=None)
    parser.add_argument("--frames", type=int, help="Frames per video.")
    parser.add_argument("--keep", action="store_true",
                        help="Persist the frame-set under ml/video_datasets.")
    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    unknown = set(args.source) - set(SUPPORTED_SOURCES)
    if unknown:
        parser.error(f"Unknown source(s): {sorted(unknown)}")

    with build_video_dataset(sources=args.source,
                             videos_per_class=args.videos_per_class,
                             frames_per_video=args.frames,
                             keep=args.keep) as root:
        print(f"Video frame-set ready at {root}")
        for split in ("train", "val", "test"):
            for cls in ("real", "fake"):
                d = os.path.join(root, split, cls)
                print(f"  {split}/{cls}: {len(os.listdir(d)) if os.path.isdir(d) else 0} frames")


if __name__ == "__main__":
    main()