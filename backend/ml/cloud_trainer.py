"""Kaggle cloud trainer - push training notebooks, poll status, pull weights.

Runs training ENTIRELY on Kaggle's GPU cloud. The Kaggle datasets are mounted
on Kaggle's machine via kagglehub inside each notebook - no dataset is ever
downloaded into the MariAnalysis project. Only the trained weights file comes
back (via ``kaggle kernels output``), into backend/models/<media>/.

Typical usage:
    from ml.cloud_trainer import submit_training, job_status, download_weights
    job = submit_training("image")          # pushes notebook, returns job info
    status = job_status("image")            # queued | running | complete | failed
    download_weights("image")               # fetch model.pth into models/image/
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone

from config import Config
from ml.kaggle_pipeline import resolve_credentials

logger = logging.getLogger("cloud_trainer")

MODEL_FOLDER = Config.MODEL_WEIGHTS_FOLDER or os.path.join(Config.BASE_DIR, "models")
TRAINERS_DIR = os.path.join(Config.BASE_DIR, "ml", "trainers")

# media -> notebook definition (kernel slug suffix + title + dataset + script).
# The kernel's id uses the "no_account/..." convention: Kaggle fills in the
# real owner on first push, so re-pushes update the same kernel.
TRAINERS = {
    "image": {
        "script": "image_trainer.py",
        "kernel": "marianalysis-image-trainer",
        "title": "MariAnalysis Image Trainer",
        "dataset": "ciplab/real-and-fake-face-detection",
        "gpu": True,
    },
    "video": {
        "script": "video_trainer.py",
        "kernel": "marianalysis-video-trainer",
        "title": "MariAnalysis Video Trainer",
        "dataset": "unidpro/deepfake-videos-dataset",
        "gpu": True,
        "folder": "Videos",
    },
    "audio": {
        "script": "audio_trainer.py",
        "kernel": "marianalysis-audio-trainer",
        "title": "MariAnalysis Audio Trainer",
        "dataset": "adarshsingh0903/audio-deepfake-detection-dataset",
        "gpu": True,
    },
    "text": {
        "script": "text_trainer.py",
        "kernel": "marianalysis-text-trainer",
        "title": "MariAnalysis Text Trainer",
        "dataset": "alitaqishah/ai-vs-human-text-classification-dataset-2026",
        "gpu": False,
    },
}

JOBS = {}          # media -> job dict (in-memory; fine for a single-node app)
LOCK = threading.Lock()
POLL_INTERVAL = Config.KAGGLE_TRAIN_POLL_SECONDS
MAX_POLL_SECONDS = Config.KAGGLE_TRAIN_MAX_HOURS * 3600


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _kaggle_cmd():
    return [sys.executable, "-m", "kaggle"]


def _run(cmd, timeout=300):
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _username():
    username, _key = resolve_credentials()
    return username


def _kernel_slug(media):
    return f"{_username()}/{TRAINERS[media]['kernel']}"


def kernel_available():
    """True when the kaggle client + credentials are usable."""
    try:
        import kaggle  # noqa: F401
        resolve_credentials()
        return True
    except Exception:  # noqa: BLE001
        return False


def job_status(media):
    return JOBS.get(media, {"status": "idle"})


def _build_kernel_dir(media):
    """Create a temporary folder with metadata.json + the trainer script."""
    spec = TRAINERS[media]
    kernel_dir = tempfile.mkdtemp(prefix=f"marianalysis_kernel_{media}_")
    script_src = os.path.join(TRAINERS_DIR, spec["script"])
    script_dst = os.path.join(kernel_dir, spec["script"])
    if not os.path.isfile(script_src):
        raise FileNotFoundError(f"Trainer script missing: {script_src}")
    shutil.copy(script_src, script_dst)
    metadata = {
        # Use the real owner slug: a fresh push creates the kernel, re-pushes
        # update the same one (no_account/... would 409 on the second push).
        "id": f"{_username()}/{spec['kernel']}",
        "title": spec["title"],
        "code_file": spec["script"],
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": spec["gpu"],
        "enable_internet": True,
        "dataset_sources": [spec["dataset"]],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    with open(os.path.join(kernel_dir, "kernel-metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
    return kernel_dir


def _push(media):
    kernel_dir = _build_kernel_dir(media)
    try:
        code, out = _run([*_kaggle_cmd(), "kernels", "push", "-p", kernel_dir], timeout=600)
        if code != 0:
            raise RuntimeError(f"kaggle kernels push failed ({code}): {out}")
        return True
    finally:
        shutil.rmtree(kernel_dir, ignore_errors=True)


def _kernel_state(media):
    slug = _kernel_slug(media)
    code, out = _run([*_kaggle_cmd(), "kernels", "status", slug], timeout=120)
    if code != 0:
        return "unknown", out
    for line in out.splitlines():
        line = line.strip().lower()
        if line.startswith("status"):
            state = line.split(":", 1)[-1].strip()
        elif " has status " in line:
            state = line.split(" has status ", 1)[-1].strip().strip('"')
        else:
            continue
        # New CLI reports states as "KernelWorkerStatus.COMPLETE" etc.
        state = state.rsplit(".", 1)[-1]
        if state in ("complete", "running", "queued", "pending", "error", "canceled", "cancelled"):
            return state, out
    return "unknown", out


def _media_folder(media):
    """Local folder name where a media type's weights are stored."""
    return TRAINERS[media].get("folder", media)


def _download_output(media, slug):
    os.makedirs(MODEL_FOLDER, exist_ok=True)
    target = os.path.join(MODEL_FOLDER, _media_folder(media))
    tmp = os.path.join(MODEL_FOLDER, f".{media}_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    code, out = _run([*_kaggle_cmd(), "kernels", "output", slug, "-p", tmp], timeout=600)
    if code != 0:
        raise RuntimeError(f"kaggle kernels output failed ({code}): {out}")
    files = os.listdir(tmp)
    zips = [f for f in files if f.endswith(".zip")]
    if not zips:
        # Kaggle sometimes drops the raw files instead of a zip.
        shutil.rmtree(target, ignore_errors=True)
        os.makedirs(target, exist_ok=True)
        for f in files:
            shutil.copy(os.path.join(tmp, f), os.path.join(target, f))
    else:
        shutil.rmtree(target, ignore_errors=True)
        os.makedirs(target, exist_ok=True)
        with zipfile.ZipFile(os.path.join(tmp, zips[0]), "r") as zf:
            zf.extractall(target)
    shutil.rmtree(tmp, ignore_errors=True)
    return target


def _run_job(media):
    """Background worker: push notebook -> poll -> download weights."""
    with LOCK:
        JOBS[media] = {
            "status": "starting",
            "media": media,
            "submitted_at": _now(),
            "error": None,
            "kernel_slug": _kernel_slug(media),
        }
    try:
        _push(media)
        with LOCK:
            JOBS[media].update(status="running", pushed_at=_now())

        slug = _kernel_slug(media)
        deadline = time.time() + MAX_POLL_SECONDS
        while time.time() < deadline:
            state, out = _kernel_state(media)
            with LOCK:
                JOBS[media].update(last_check=_now(), kernel_state=state)
            if state == "complete":
                path = _download_output(media, slug)
                with LOCK:
                    JOBS[media].update(status="complete", completed_at=_now(), weights_path=path)
                logger.info("Training complete for %s -> %s", media, path)
                return
            if state in ("error", "canceled", "cancelled"):
                raise RuntimeError(f"Kaggle kernel ended with state '{state}': {out[:500]}")
            time.sleep(POLL_INTERVAL)
        raise TimeoutError("Kaggle kernel did not finish before the timeout.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cloud training failed for %s: %s", media, exc)
        with LOCK:
            JOBS[media].update(status="failed", error=str(exc), ended_at=_now())


def submit_training(media):
    if media not in TRAINERS:
        raise ValueError(f"Unsupported media type '{media}'. Choose from {sorted(TRAINERS)}.")
    with LOCK:
        current = JOBS.get(media, {}).get("status")
    if current in ("starting", "running"):
        raise RuntimeError(f"Training already running for '{media}'.")
    if not kernel_available():
        raise RuntimeError(
            "Kaggle API not configured. Add KAGGLE_USERNAME + KAGGLE_KEY to "
            ".env (https://www.kaggle.com/settings -> API) and run "
            "`pip install -r requirements-ai.txt` to install the kaggle client.")
    thread = threading.Thread(target=_run_job, args=(media,), daemon=True)
    thread.start()
    return job_status(media)


def download_weights(media):
    """Force-refresh the local weights for a media type from the kernel output."""
    state = job_status(media)
    slug = state.get("kernel_slug") or _kernel_slug(media)
    return _download_output(media, slug)


def local_weights():
    """List media types that already have a trained model checked out locally."""
    result = {}
    if not os.path.isdir(MODEL_FOLDER):
        return result
    for media in TRAINERS:
        folder = os.path.join(MODEL_FOLDER, _media_folder(media))
        if not os.path.isdir(folder):
            continue
        info = {}
        info_path = os.path.join(folder, "model_info.json")
        if os.path.isfile(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as fh:
                    info = json.load(fh)
            except Exception:  # noqa: BLE001
                info = {}
        result[media] = {
            "present": True,
            "path": folder,
            "info": info,
        }
    return result
