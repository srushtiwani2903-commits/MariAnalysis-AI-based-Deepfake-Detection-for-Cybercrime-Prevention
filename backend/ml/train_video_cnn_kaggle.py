# %% [markdown]
# # MariAnalysis — Real vs Fake Video Frame CNN (Kaggle training pipeline)
#
# Trains an **accurate + efficient** PyTorch CNN on *video frames* extracted
# from the multi-source video pipeline (`ml/video_pipeline.py`), which pulls a
# labelled real + fake corpus from **Kaggle, Hugging Face and Google Drive**.
#
# **How to use on Kaggle:**
# 1. Create a Kaggle Notebook → Settings → GPU "T4x2".
# 2. Upload this .py file via **File → Import Notebook** (the `# %%` lines become cells).
# 3. Run all cells. The trained model is saved as `marianalysis_video_cnn.pt`
#    in the notebook **Output** tab.
# 4. Download it and copy it to
#    `backend/models/video_real_vs_fake_cnn.pt` (create the folder).
# 5. Set `VIDEO_MODEL_ENABLED=true` in `backend/.env` — every video scan now
#    blends this real frame-CNN into the verdict (see `services/video_detector.py`).
#
# **Input data layout** (built by `python -m ml.video_pipeline --keep`):
# ```
# <DATA_ROOT>/
#   train/{real,fake}/*.jpg
#   val/{real,fake}/*.jpg
#   test/{real,fake}/*.jpg
# ```
# Flat `real/ + fake/` layouts are auto-detected too (frames split to a random
# training/validation fold).

# %% [markdown]
# ## 1. CONFIG — edit to taste (env vars override each value)

# %%
import os
_IS_KAGGLE = os.getenv("KAGGLE_KERNEL_RUN_TYPE") is not None

DATASET_ROOT = os.getenv("DATA_ROOT") or None  # None = auto (kagglehub video frames)
VAL_RATIO = float(os.getenv("VAL_RATIO", "0.15"))
SEED = int(os.getenv("SEED", "42"))

BACKBONE = os.getenv("BACKBONE", "efficientnet_b0")
IMAGE_SIZE = int(os.getenv("IMAGE_SIZE", "224"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
EPOCHS = int(os.getenv("EPOCHS", "30"))
LR = float(os.getenv("LR", "1e-3"))
WEIGHT_DECAY = float(os.getenv("WEIGHT_DECAY", "1e-4"))
EARLY_STOP_PATIENCE = int(os.getenv("EARLY_STOP_PATIENCE", "6"))
USE_AMP = os.getenv("USE_AMP", "true").lower() == "true"
LABEL_SMOOTHING = float(os.getenv("LABEL_SMOOTHING", "0.05"))
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "4"))
RESUME = os.getenv("RESUME", "false").lower() == "true"
FREEZE_BACKBONE = os.getenv("FREEZE_BACKBONE", "false").lower() == "true"
UNFREEZE_LAST_BLOCKS = int(os.getenv("UNFREEZE_LAST_BLOCKS", "0"))

MODEL_OUTPUT = os.getenv("MODEL_OUTPUT", "marianalysis_video_cnn.pt")
PLOT_DIR = os.getenv("PLOT_DIR", "/kaggle/working" if _IS_KAGGLE else "outputs")

# %% [markdown]
# ## 2. Imports + helpers (safe at import time)

# %%
import glob
import json
import random
import re
import shutil

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, precision_recall_fscore_support)

MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
FAKE_LABEL = 1
REAL_LABEL = 0


def _class_role(name):
    n = name.lower()
    if any(k in n for k in ("fake", "ai_", "ai-", "generated", "synthetic")):
        return "fake"
    if any(k in n for k in ("real", "genuine", "authentic")):
        return "real"
    return None


def _is_img_dir(path):
    try:
        return any(os.path.splitext(f)[1].lower() in IMAGE_EXTS for f in os.listdir(path))
    except OSError:
        return False


def find_splits(root):
    """Classic layout: dirs named train/valid/val/test containing class folders."""
    splits = {}
    for dirpath, dirnames, _ in os.walk(root):
        role = {"train": "train", "valid": "val", "val": "val", "test": "test"}.get(
            os.path.basename(dirpath).lower())
        if role and role not in splits:
            subs = [d for d in dirnames if _is_img_dir(os.path.join(dirpath, d))]
            if len(subs) >= 2 and any(_class_role(s) for s in subs):
                splits[role] = dirpath
    return splits


def find_class_root(root):
    """Flat layout: parent dir directly containing real/ + fake/ class folders."""
    best = None
    for dirpath, dirnames, _ in os.walk(root):
        roles = {}
        for d in dirnames:
            r = _class_role(d)
            if r and _is_img_dir(os.path.join(dirpath, d)):
                roles.setdefault(r, []).append(os.path.join(dirpath, d))
        if "real" in roles and "fake" in roles:
            cand = (dirpath, roles["real"][0], roles["fake"][0])
            if best is None or len(dirpath) < len(best[0]):
                best = cand
    return best


class ClassPairDataset(torch.utils.data.Dataset):
    """Real/fake frame folders joined into one dataset. real=0, fake=1."""

    def __init__(self, real_paths, fake_paths, transform):
        self.files = [(p, REAL_LABEL) for p in real_paths] + [(p, FAKE_LABEL) for p in fake_paths]
        self.transform = transform

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        path, label = self.files[idx]
        img = datasets.folder.default_loader(path)
        if self.transform:
            img = self.transform(img)
        return img, label


def build_classpair(real_dir, fake_dir, transform):
    return ClassPairDataset(
        sorted(os.path.join(real_dir, f) for f in os.listdir(real_dir)
               if os.path.splitext(f)[1].lower() in IMAGE_EXTS),
        sorted(os.path.join(fake_dir, f) for f in os.listdir(fake_dir)
               if os.path.splitext(f)[1].lower() in IMAGE_EXTS),
        transform)


def remap_imagefolder(ds, real_name, fake_name):
    """ImageFolder -> remap classes so real=0, fake=1 (stable fake output)."""
    mapper = {ds.classes.index(real_name): REAL_LABEL, ds.classes.index(fake_name): FAKE_LABEL}
    ds.samples = [(p, mapper[l]) for p, l in ds.samples]
    ds.targets = [mapper[l] for l in ds.targets]
    ds.classes = [real_name, fake_name]
    ds.class_to_idx = {real_name: REAL_LABEL, fake_name: FAKE_LABEL}
    return ds


def build_model(backbone=BACKBONE, num_classes=2):
    factory = getattr(models, backbone, None)
    if factory is None:
        raise ValueError(f"Unknown backbone '{backbone}'.")
    try:
        model = factory(weights="IMAGENET1K_V2")
    except Exception:
        model = factory(weights="IMAGENET1K_V1")
    if hasattr(model, "fc"):                       # ResNet
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif hasattr(model, "classifier"):             # EfficientNet / MobileNet
        if isinstance(model.classifier, nn.Sequential):
            model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, num_classes)
        else:
            model.classifier = nn.Linear(model.classifier.in_features, num_classes)
    elif hasattr(model, "heads"):                  # ViT
        model.heads.head = nn.Linear(model.heads.head.in_features, num_classes)
    return model


def _head_modules(model):
    if hasattr(model, "classifier"):
        return [model.classifier]
    if hasattr(model, "fc"):
        return [model.fc]
    if hasattr(model, "heads"):
        return [model.heads]
    return []


def apply_freeze(model):
    if not FREEZE_BACKBONE:
        return
    for p in model.parameters():
        p.requires_grad = False
    if UNFREEZE_LAST_BLOCKS > 0 and hasattr(model, "features"):
        for p in model.features[-UNFREEZE_LAST_BLOCKS:].parameters():
            p.requires_grad = True
    for module in _head_modules(model):
        for p in module.parameters():
            p.requires_grad = True
    trainable = [n for n, p in model.named_parameters() if p.requires_grad]
    print(f"Freezing backbone. Trainable params: {len(trainable)} layers "
          f"({sum(p.numel() for p in model.parameters() if p.requires_grad)/1e3:.1f}k)")


def predict_loader(model, loader, device, use_amp):
    model.eval()
    preds, labels = [], []
    with torch.no_grad():
        for images, labels_b in loader:
            images = images.to(device)
            with torch.amp.autocast("cuda", enabled=use_amp):
                outputs = model(images)
            preds.extend(torch.argmax(outputs, 1).cpu().tolist())
            labels.extend(labels_b.tolist())
    return np.array(preds), np.array(labels)


def report(y_true, y_pred, name, real_name, fake_name):
    acc = accuracy_score(y_true, y_pred)
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="binary",
                                                 pos_label=FAKE_LABEL, zero_division=0)
    print(f"\n===== {name} ===== Accuracy: {acc:.4f} "
          f"| Fake-Precision: {p:.4f} | Fake-Recall: {r:.4f} | F1: {f:.4f}")
    print(classification_report(y_true, y_pred, target_names=[real_name, fake_name],
                                digits=3, zero_division=0))
    return acc


def _frame_metrics(y_true, y_pred, label):
    """Condensed per-frame metric set (accuracy / P / R / F1 / conf-matrix)."""
    acc = accuracy_score(y_true, y_pred)
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="binary",
                                                 pos_label=FAKE_LABEL, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[REAL_LABEL, FAKE_LABEL]).tolist()
    return {"frames": int(len(y_true)), "accuracy": float(acc),
            "precision": float(p), "recall": float(r), "f1": float(f),
            "confusion_matrix": cm, "label": label}


def _ds_paths(ds):
    """Ordered file paths matching a non-shuffled DataLoader's iteration."""
    if hasattr(ds, "samples"):        # torchvision ImageFolder
        return [p for p, _ in ds.samples]
    if hasattr(ds, "files"):          # ClassPairDataset
        return [p for p, _ in ds.files]
    return []


def _video_key(frame_path):
    """Source-video id of a pipeline frame named <video_id>_<frame_idx>.jpg."""
    return re.sub(r"_\d+$", "", os.path.splitext(os.path.basename(frame_path))[0])


def _json_safe(obj):
    """Recursively convert numpy types so json.dump never chokes."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def video_report(y_true, y_pred, frame_paths, name, real_name, fake_name):
    """Video-level metrics: majority-vote the per-frame predictions.

    Each source video contributes exactly one vote (fake if >= half of its
    frames are flagged), which is the metric the live detector user sees.
    Returns the metric dict; also prints a full report.
    """
    votes = {}
    for path, t, p in zip(frame_paths, y_true, y_pred):
        vid = _video_key(path)
        votes.setdefault(vid, {"true": t, "preds": []})["preds"].append(p)
    v_true = [v["true"] for v in votes.values()]
    v_pred = [1 if (sum(v["preds"]) / len(v["preds"])) >= 0.5 else 0
              for v in votes.values()]
    acc = report(v_true, v_pred, f"{name} VIDEO-LEVEL (majority vote)",
                 real_name, fake_name)
    p, r, f, _ = precision_recall_fscore_support(v_true, v_pred, average="binary",
                                                 pos_label=FAKE_LABEL, zero_division=0)
    cm = confusion_matrix(v_true, v_pred, labels=[REAL_LABEL, FAKE_LABEL]).tolist()
    return {"videos": len(v_true),
            "frames_per_video": round(len(frame_paths) / max(1, len(votes)), 2),
            "accuracy": float(acc), "precision": float(p), "recall": float(r),
            "f1": float(f), "confusion_matrix": cm, "label": name}


# %% [markdown]
# ## 3. main() — load frames, train, evaluate, export

# %%
def main():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    os.makedirs(PLOT_DIR, exist_ok=True)

    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True
        torch.set_float32_matmul_precision("high")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        device = torch.device("cuda")
    else:
        print("Device: CPU (training the frozen feature extractor - fast).")
        device = torch.device("cpu")

    # ------------------------------- data --------------------------------- #
    if not DATASET_ROOT:
        raise RuntimeError(
            "DATA_ROOT is required: run `python -m ml.video_pipeline --keep` "
            "first (or set DATA_ROOT to the extracted frame-set).")
    root = DATASET_ROOT
    print("Frame root:", root)

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(IMAGE_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])

    splits = find_splits(root)
    print("Found classic splits:", {k: v for k, v in splits.items()})
    real_name, fake_name = None, None

    if splits.get("train"):
        train_path = splits["train"]
        classes = sorted(d for d in os.listdir(train_path) if _is_img_dir(os.path.join(train_path, d)))
        real_name = next((c for c in classes if _class_role(c) == "real"), None)
        fake_name = next((c for c in classes if _class_role(c) == "fake"), None)
        if not real_name or not fake_name:
            raise RuntimeError(f"Could not find real/fake class folders in {train_path} "
                               f"(found {classes}).")
        train_ds = remap_imagefolder(datasets.ImageFolder(root=train_path, transform=train_tf),
                                     real_name, fake_name)
        val_ds = (remap_imagefolder(datasets.ImageFolder(root=splits["val"], transform=eval_tf),
                                    real_name, fake_name) if splits.get("val") else None)
        test_ds = (remap_imagefolder(datasets.ImageFolder(root=splits["test"], transform=eval_tf),
                                     real_name, fake_name) if splits.get("test") else None)
    else:
        found = find_class_root(root)
        if found is None:
            raise RuntimeError(
                f"No train split or real/fake class folders found under {root}.")
        _, real_dir, fake_dir = found
        real_name, fake_name = os.path.basename(real_dir), os.path.basename(fake_dir)
        print(f"Flat layout: real='{real_name}', fake='{fake_name}'")
        train_ds = build_classpair(real_dir, fake_dir, train_tf)
        val_ds = test_ds = None

    if val_ds is None:
        n_val = int(VAL_RATIO * len(train_ds))
        n_train = len(train_ds) - n_val
        train_ds, val_ds = torch.utils.data.random_split(
            train_ds, [n_train, n_val], generator=torch.Generator().manual_seed(SEED))
        val_ds.dataset.transform = eval_tf

    print(f"Train: {len(train_ds)} | Val: {len(val_ds)}" +
          (f" | Test: {len(test_ds)}" if test_ds else ""))
    fake_count = sum(1 for _, l in train_ds if l == FAKE_LABEL)
    print(f"Train class counts: fake={fake_count}, real={len(train_ds) - fake_count}")

    def dl(ds, shuffle):
        n_w = NUM_WORKERS if not _IS_KAGGLE else min(4, os.cpu_count() or 1)
        return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=shuffle, num_workers=n_w,
                          pin_memory=True, persistent_workers=(n_w > 0 and len(ds) > 0))

    train_loader = dl(train_ds, shuffle=True)
    val_loader = dl(val_ds, shuffle=False)
    test_loader = dl(test_ds, shuffle=False) if test_ds else None

    # ------------------------------- model -------------------------------- #
    model = build_model().to(device)
    apply_freeze(model)
    n_par = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Backbone: {BACKBONE} | trainable params: {n_par/1e6:.2f}M")

    criterion = nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    optimizer = optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max",
                                                     factor=0.5, patience=2, min_lr=1e-6)
    scaler = torch.amp.GradScaler("cuda", enabled=USE_AMP)

    def run_epoch(loader, training):
        model.train(training)
        loss_sum = correct = total = 0
        with torch.set_grad_enabled(training):
            for images, labels in loader:
                images, labels = images.to(device), labels.to(device)
                optimizer.zero_grad()
                with torch.amp.autocast("cuda", enabled=USE_AMP):
                    outputs = model(images)
                    loss = criterion(outputs, labels)
                if training:
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                preds = torch.argmax(outputs, 1)
                loss_sum += loss.item() * images.size(0)
                correct += (preds == labels).sum().item()
                total += images.size(0)
        return loss_sum / max(total, 1), correct / max(total, 1)

    # ------------------------------ training ------------------------------ #
    best_acc, no_improve = 0.0, 0
    history = []
    start_epoch = 1

    if RESUME and os.path.isfile(MODEL_OUTPUT):
        ckpt = torch.load(MODEL_OUTPUT, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        if ckpt.get("optimizer_state"):
            try:
                optimizer.load_state_dict(ckpt["optimizer_state"])
                scheduler.load_state_dict(ckpt["scheduler_state"])
            except Exception:  # noqa: BLE001
                print("Optimizer state mismatch - continuing with fresh optimizer.")
        start_epoch = int(ckpt.get("epoch", 0)) + 1
        best_acc = float(ckpt.get("best_acc", 0.0))
        no_improve = int(ckpt.get("no_improve", 0))
        history = list(ckpt.get("history", []))
        print(f"RESUME: continuing from epoch {start_epoch} (best_acc={best_acc:.3f})")

    print(f"\n{'Epoch':>5} | {'TrainLoss':>9} {'TrainAcc':>8} | {'ValLoss':>8} {'ValAcc':>7} | {'LR':>8}")
    print("-" * 58)

    for epoch in range(start_epoch, EPOCHS + 1):
        tr_loss, tr_acc = run_epoch(train_loader, True)
        va_loss, va_acc = run_epoch(val_loader, False)
        scheduler.step(va_acc)
        print(f"{epoch:>5} | {tr_loss:>9.4f} {tr_acc:>8.3f} | {va_loss:>8.4f} {va_acc:>7.3f} "
              f"| {optimizer.param_groups[0]['lr']:.2e}", flush=True)
        history.append((tr_loss, tr_acc, va_loss, va_acc))

        if va_acc > best_acc:
            best_acc = va_acc
            no_improve = 0
            torch.save({
                "model": model.state_dict(),
                "backbone": BACKBONE,
                "classes": [real_name, fake_name],   # [real, fake]
                "fake_label": FAKE_LABEL,            # 1
                "image_size": IMAGE_SIZE,
                "transform": {"mean": MEAN, "std": STD},
                "val_accuracy": round(float(best_acc), 4),
                "train_frames": len(train_ds),
                "epoch": epoch,
                "best_acc": float(best_acc),
                "no_improve": no_improve,
                "history": history,
                "optimizer_state": optimizer.state_dict(),
                "scheduler_state": scheduler.state_dict(),
            }, MODEL_OUTPUT)
            print(f"   -> best model saved ({best_acc:.3f})")
        else:
            no_improve += 1
            if no_improve >= EARLY_STOP_PATIENCE:
                print(f"Early stopping after {epoch} epochs.")
                break

    print(f"\nBest validation accuracy: {best_acc:.4f} -> {MODEL_OUTPUT}")

    # ------------------------------- curves ------------------------------- #
    ep = np.arange(1, len(history) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(ep, [h[0] for h in history], label="train")
    axes[0].plot(ep, [h[2] for h in history], label="val")
    axes[0].set(title="Loss", xlabel="epoch"); axes[0].legend()
    axes[1].plot(ep, [h[1] for h in history], label="train")
    axes[1].plot(ep, [h[3] for h in history], label="val")
    axes[1].set(title="Accuracy", xlabel="epoch"); axes[1].legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "video_training_curves.png"), dpi=120)
    plt.show()

    # ---------------------------- evaluation ------------------------------ #
    metrics = {
        "backbone": BACKBONE,
        "image_size": IMAGE_SIZE,
        "batch_size": BATCH_SIZE,
        "epochs": epoch,
        "best_val_accuracy": round(float(best_acc), 4),
        "classes": [real_name, fake_name],
        "train_frames": len(train_ds),
        "val_frames": len(val_ds),
        "test_frames": len(test_ds) if test_ds else 0,
        "dataset_root": root,
        "label_map": {str(REAL_LABEL): real_name, str(FAKE_LABEL): fake_name},
        "history": {"epoch": ep, "train_loss": [h[0] for h in history],
                    "train_acc": [h[1] for h in history],
                    "val_loss": [h[2] for h in history],
                    "val_acc": [h[3] for h in history]},
        "frame_accuracy": {},
        "video_accuracy": {},
    }

    y_val, y_val_true = predict_loader(model, val_loader, device, USE_AMP)
    frame_val = _frame_metrics(y_val_true, y_val, "validation")
    metrics["frame_accuracy"]["val"] = frame_val
    report(y_val_true, y_val, "VALIDATION (video frames)", real_name, fake_name)

    y_test, y_test_true = None, None
    if test_loader:
        y_test, y_test_true = predict_loader(model, test_loader, device, USE_AMP)
        metrics["frame_accuracy"]["test"] = _frame_metrics(y_test_true, y_test, "test")
        report(y_test_true, y_test, "TEST (video frames)", real_name, fake_name)

    # Per-video (majority-vote) accuracy: the metric that matches what live
    # detection reports for a whole uploaded video, one vote per source clip.
    val_paths = _ds_paths(val_ds)
    if val_paths:
        metrics["video_accuracy"]["val"] = video_report(
            y_val_true, y_val, val_paths, "VALIDATION", real_name, fake_name)
    if test_loader and test_ds is not None:
        test_paths = _ds_paths(test_ds)
        if test_paths and y_test is not None:
            metrics["video_accuracy"]["test"] = video_report(
                y_test_true, y_test, test_paths, "TEST", real_name, fake_name)

    metrics_path = os.path.join(PLOT_DIR, "video_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as fh:
        json.dump(_json_safe(metrics), fh, indent=2, ensure_ascii=False)
    print(f"\nMetrics JSON (frame + per-video majority-vote): "
          f"{os.path.abspath(metrics_path)}")

    cm = confusion_matrix(y_val_true, y_val, labels=[REAL_LABEL, FAKE_LABEL])
    plt.figure(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=[real_name, fake_name], yticklabels=[real_name, fake_name])
    plt.title(f"Confusion Matrix — Validation (acc {accuracy_score(y_val_true, y_val):.3f})")
    plt.ylabel("True"); plt.xlabel("Predicted")
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "video_confusion_matrix.png"), dpi=120)
    plt.show()

    # --------------------------- export summary --------------------------- #
    ckpt = torch.load(MODEL_OUTPUT, map_location="cpu", weights_only=True)
    print("\nCheckpoint keys:", list(ckpt.keys()))
    print(f"backbone={ckpt['backbone']} | classes={ckpt['classes']} | "
          f"fake_label={ckpt['fake_label']} | image_size={ckpt['image_size']} | "
          f"val_accuracy={ckpt['val_accuracy']}")

    if _IS_KAGGLE:
        print("\nDONE. Download marianalysis_video_cnn.pt from the Output tab and copy")
        print("it to backend/models/video_real_vs_fake_cnn.pt, then set")
        print("VIDEO_MODEL_ENABLED=true in backend/.env.")
    else:
        print(f"\nModel ready locally at {os.path.abspath(MODEL_OUTPUT)}. Copy it to")
        print("backend/models/video_real_vs_fake_cnn.pt and set VIDEO_MODEL_ENABLED=true.")


# %%
if __name__ == "__main__":
    main()