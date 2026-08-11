"""Video deepfake trainer - runs on the Kaggle GPU cloud.

Self-contained script executed by a Kaggle Notebook. Frames are sampled from
real vs fake videos (pulled on Kaggle's machine via kagglehub) and used to
train a compact frame-level CNN. At inference, frame scores are averaged.

Output (in /kaggle/working):
    model.pth          trained CNN weights (torch)
    model_info.json    frame setup, test accuracy, video-level accuracy
"""
import json
import os
import random
import sys

try:
    import kagglehub
except ImportError:  # pragma: no cover
    kagglehub = None

try:
    import cv2
    import torch
    import torch.nn as nn
except ImportError as exc:  # pragma: no cover
    print(f"FATAL: missing dependency: {exc}", file=sys.stderr)
    sys.exit(1)

DATASET_SLUG = os.environ.get("KAGGLE_DATASET", "unidpro/deepfake-videos-dataset")
SAMPLE_VIDEOS = int(os.environ.get("SAMPLE_VIDEOS", "300"))
FRAMES_PER_VIDEO = int(os.environ.get("FRAMES_PER_VIDEO", "8"))
EPOCHS = int(os.environ.get("KAGGLE_EPOCHS", "3"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "64"))
FRAME_SIZE = int(os.environ.get("FRAME_SIZE", "64"))
SEED = int(os.environ.get("KAGGLE_SEED", "42"))

random.seed(SEED)
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def load_dataset():
    if kagglehub is not None:
        try:
            return kagglehub.dataset_download(DATASET_SLUG)
        except Exception as exc:  # noqa: BLE001
            print(f"kagglehub failed ({exc}); scanning /kaggle/input", file=sys.stderr)
    root = "/kaggle/input"
    if os.path.isdir(root):
        for entry in sorted(os.listdir(root)):
            path = os.path.join(root, entry)
            if os.path.isdir(path):
                return path
    raise RuntimeError("Dataset not available on Kaggle machine.")


def collect_videos(root):
    """Label by the top-level subfolder only.

    The dataset root folder name (e.g. "deepfake-videos-dataset") can itself
    contain the word "fake", so matching on the full path would mislabel every
    video. We match on the first path component under the dataset root:
    <root>/deepfake/...  -> fake,  <root>/video/... -> real.
    """
    samples = {0: [], 1: []}
    for dirpath, _dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
        top = rel.split("/")[0].lower() if rel != "." else ""
        if "fake" in top or "deepfake" in top:
            label = 1
        elif top in ("real", "original", "video", "authentic"):
            label = 0
        else:
            label = None
        if label is None:
            continue
        for name in files:
            if os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
                continue
            samples[label].append(os.path.join(dirpath, name))
    return samples


def extract_frames(video_path, max_frames=FRAMES_PER_VIDEO, size=FRAME_SIZE):
    frames = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return frames
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            total = max_frames
        step = max(1, total // max_frames)
        idx = 0
        while len(frames) < max_frames and idx < total:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (size, size))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append((torch.from_numpy(frame).permute(2, 0, 1).float() / 127.5) - 1.0)
            idx += step
    finally:
        cap.release()
    return frames


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  dataset: {DATASET_SLUG}", flush=True)

    root = load_dataset()
    samples = collect_videos(root)
    print(f"Found real={len(samples[0])} fake={len(samples[1])}", flush=True)

    cap_videos = min(SAMPLE_VIDEOS, min(len(samples[0]), len(samples[1])))
    if cap_videos == 0:
        raise RuntimeError("No labeled real/fake videos found - check the dataset structure.")
    chosen = {0: random.sample(samples[0], cap_videos), 1: random.sample(samples[1], cap_videos)}

    # Extract frame-level training pairs (each frame carries the video label).
    pairs = []
    for label, paths in chosen.items():
        for vp in paths:
            for frame in extract_frames(vp):
                pairs.append((frame, label))
    if len(pairs) < 100:
        raise RuntimeError("Too few frames extracted - check the video files.")
    random.shuffle(pairs)
    n_test = max(1, int(len(pairs) * 0.15))
    test_pairs, train_pairs = pairs[:n_test], pairs[n_test:]
    print(f"train_frames={len(train_pairs)} test_frames={len(test_pairs)}", flush=True)


    class FrameCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.body = nn.Sequential(
                nn.Conv2d(3, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(inplace=True), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2),
                nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            )
            self.head = nn.Sequential(nn.Flatten(), nn.Linear(64 * 8 * 8, 64), nn.ReLU(), nn.Linear(64, 2))

        def forward(self, x):
            return self.head(self.body(x))


    model = FrameCNN().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    train_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(
            torch.stack([x for x, _ in train_pairs]),
            torch.tensor([y for _, y in train_pairs]),
        ), batch_size=BATCH_SIZE, shuffle=True)

    for epoch in range(1, EPOCHS + 1):
        model.train()
        total, correct = 0, 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            total += yb.size(0)
            correct += (model(xb).argmax(1) == yb).sum().item()
        print(f"epoch {epoch}/{EPOCHS} loss={loss.item():.4f} acc={correct / total:.4f}", flush=True)

    model.eval()
    with torch.no_grad():
        test_imgs = torch.stack([x for x, _ in test_pairs]).to(device)
        test_labels = torch.tensor([y for _, y in test_pairs]).to(device)
        test_acc = (model(test_imgs).argmax(1) == test_labels).float().mean().item()

    torch.save(model.state_dict(), "/kaggle/working/model.pth")
    info = {
        "media": "video",
        "dataset": DATASET_SLUG,
        "architecture": "FrameCNN (per-frame, averaged at inference)",
        "frame_size": FRAME_SIZE,
        "frames_per_video": FRAMES_PER_VIDEO,
        "frame_accuracy": round(test_acc, 4),
        "train_frames": len(train_pairs),
        "test_frames": len(test_pairs),
        "label_map": {"0": "real", "1": "fake"},
    }
    with open("/kaggle/working/model_info.json", "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    print(json.dumps(info), flush=True)
    print("TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
