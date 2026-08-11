"""Image deepfake trainer - runs on the Kaggle GPU cloud.

Self-contained script executed by a Kaggle Notebook (pushed by
backend/ml/cloud_trainer.py). The dataset is pulled directly on Kaggle's
machine via kagglehub - nothing is ever downloaded to the MariAnalysis server.

Output (saved into /kaggle/working, downloadable back to the app):
    model.pth          trained CNN weights (torch)
    model_info.json    class map, preprocessing stats, test accuracy
"""
import json
import os
import random
import sys

# kagglehub is preinstalled on Kaggle Notebooks; fall back to /kaggle/input
try:
    import kagglehub
except ImportError:  # pragma: no cover
    kagglehub = None

try:
    import torch
    import torch.nn as nn
    import torchvision.transforms as T
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    print(f"FATAL: missing dependency: {exc}", file=sys.stderr)
    sys.exit(1)

DATASET_SLUG = os.environ.get("KAGGLE_DATASET", "ciplab/real-and-fake-face-detection")
SAMPLE_PER_CLASS = int(os.environ.get("SAMPLE_PER_CLASS", "4000"))
EPOCHS = int(os.environ.get("KAGGLE_EPOCHS", "3"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "64"))
IMAGE_SIZE = int(os.environ.get("IMAGE_SIZE", "128"))
SEED = int(os.environ.get("KAGGLE_SEED", "42"))

random.seed(SEED)


def load_dataset():
    """Download on Kaggle's machine and return the dataset folder path."""
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


def collect_images(root):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    samples = {0: [], 1: []}
    for dirpath, _dirs, files in os.walk(root):
        # Match on exact path components, not substrings: the dataset root
        # folder itself (e.g. "real-and-fake-face-detection") contains "fake".
        rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
        parts = set(rel.split("/"))
        if "fake" in parts or "forged" in parts or "synthetic" in parts:
            label = 1
        elif "real" in parts or "original" in parts or "authentic" in parts:
            label = 0
        else:
            continue
        for name in files:
            if os.path.splitext(name)[1].lower() not in exts:
                continue
            samples[label].append(os.path.join(dirpath, name))
    return samples


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  dataset: {DATASET_SLUG}", flush=True)

    root = load_dataset()
    samples = collect_images(root)
    print(f"Found real={len(samples[0])} fake={len(samples[1])}", flush=True)

    # Balanced sample per class to keep cloud training quick.
    cap = min(SAMPLE_PER_CLASS, min(len(samples[0]), len(samples[1])))
    if cap == 0:
        raise RuntimeError("No labeled real/fake images found - check the dataset structure.")
    chosen = {0: random.sample(samples[0], cap), 1: random.sample(samples[1], cap)}

    tf = T.Compose([
        T.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        T.ToTensor(),
        T.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
    ])
    pairs = []
    for label, paths in chosen.items():
        for p in paths:
            try:
                img = Image.open(p).convert("RGB")
                pairs.append((tf(img), label))
            except Exception:  # noqa: BLE001
                continue
    random.shuffle(pairs)
    n_test = max(1, int(len(pairs) * 0.15))
    test_pairs, train_pairs = pairs[:n_test], pairs[n_test:]
    print(f"train={len(train_pairs)} test={len(test_pairs)}", flush=True)


    class SmallCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.body = nn.Sequential(
                nn.Conv2d(3, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(inplace=True), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2),
                nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            )
            self.head = nn.Sequential(nn.Flatten(), nn.Linear(64 * 16 * 16, 64), nn.ReLU(), nn.Linear(64, 2))

        def forward(self, x):
            return self.head(self.body(x))


    model = SmallCNN().to(device)
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
        preds = model(test_imgs).argmax(1)
        test_acc = (preds == test_labels).float().mean().item()

    torch.save(model.state_dict(), "/kaggle/working/model.pth")
    info = {
        "media": "image",
        "dataset": DATASET_SLUG,
        "architecture": "SmallCNN",
        "image_size": IMAGE_SIZE,
        "test_accuracy": round(test_acc, 4),
        "train_samples": len(train_pairs),
        "test_samples": len(test_pairs),
        "label_map": {"0": "real", "1": "fake"},
    }
    with open("/kaggle/working/model_info.json", "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    print(json.dumps(info), flush=True)
    print("TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
