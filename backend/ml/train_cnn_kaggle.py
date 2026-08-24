# %% [markdown]
# # MariAnalysis — Real vs Fake Face CNN (Kaggle training pipeline)
#
# Trains an **accurate + efficient** PyTorch CNN to distinguish real photos from
# AI-generated/manipulated faces, using the dataset already registered in
# `backend/ml/data_config.py`:
#
#     ciplab/real-and-fake-face-detection  (CelebA real faces vs AI fake faces)
#
# **How to use on Kaggle:**
# 1. Create a Kaggle Notebook → Settings → GPU "T4x2".
# 2. Upload this .py file via **File → Import Notebook** (the `# %%` lines become cells).
# 3. Run all cells. The trained model is saved as `marianalysis_cnn.pt`
#    in the notebook **Output** tab.
# 4. Download `marianalysis_cnn.pt` and copy it to
#    `backend/models/faces_real_vs_fake_cnn.pt` (create the folder).
# 5. Set `MODEL_ENABLED=true` in `backend/.env` — the image detector now blends
#    this real CNN into every image verdict.
#
# **How to run locally (CPU):** every CONFIG value can be overridden with an
# environment variable, e.g.:
# ```
# python ml/train_cnn_kaggle.py                 # on Kaggle GPU defaults
# FREEZE_BACKBONE=1 EPOCHS=20 NUM_WORKERS=4 python ml/train_cnn_kaggle.py
# ```
# The script auto-detects both the classic `train/valid/{real,fake}` layout and
# this dataset's flat `training_real/ + training_fake/` layout (its nested
# duplicate copy is ignored automatically).

# %% [markdown]
# ## 1. CONFIG — edit to taste (env vars override each value)

# %%
import os
_IS_KAGGLE = os.getenv("KAGGLE_KERNEL_RUN_TYPE") is not None

# ----------------------------------------------------------------------------
# DATA
# ----------------------------------------------------------------------------
DATASET_HANDLE = "ciplab/real-and-fake-face-detection"   # registered in data_config.py
DATA_ROOT = os.getenv("DATA_ROOT") or None   # None = auto (kagglehub). Or set a folder path.
VAL_RATIO = float(os.getenv("VAL_RATIO", "0.15"))        # held-out validation
SEED = int(os.getenv("SEED", "42"))

# ----------------------------------------------------------------------------
# MODEL / TRAINING
# ----------------------------------------------------------------------------
BACKBONE = os.getenv("BACKBONE", "efficientnet_b0")  # efficientnet_b0 | resnet18 | resnet50 | mobilenet_v3_large
IMAGE_SIZE = int(os.getenv("IMAGE_SIZE", "224"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
EPOCHS = int(os.getenv("EPOCHS", "30"))
LR = float(os.getenv("LR", "1e-3"))
WEIGHT_DECAY = float(os.getenv("WEIGHT_DECAY", "1e-4"))
EARLY_STOP_PATIENCE = int(os.getenv("EARLY_STOP_PATIENCE", "6"))
USE_AMP = os.getenv("USE_AMP", "true").lower() == "true"
LABEL_SMOOTHING = float(os.getenv("LABEL_SMOOTHING", "0.05"))
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "4"))
# Continue training from the checkpoint at MODEL_OUTPUT (skips already-done epochs).
RESUME = os.getenv("RESUME", "false").lower() == "true"
# CPU-friendly: freeze all backbone weights and train only the new head.
FREEZE_BACKBONE = os.getenv("FREEZE_BACKBONE", "false").lower() == "true"
# When FREEZE_BACKBONE, optionally unfreeze the last N feature blocks too.
UNFREEZE_LAST_BLOCKS = int(os.getenv("UNFREEZE_LAST_BLOCKS", "0"))

# ----------------------------------------------------------------------------
# OUTPUT
# ----------------------------------------------------------------------------
MODEL_OUTPUT = os.getenv("MODEL_OUTPUT", "marianalysis_cnn.pt")
PLOT_DIR = os.getenv("PLOT_DIR", "/kaggle/working" if _IS_KAGGLE else "outputs")

# %% [markdown]
# ## 2. Imports + helpers (safe at import time)

# %%
import glob
import random
import shutil
import sys

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
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
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
    """Flat layout: parent dir directly containing real/ + fake/ class folders.

    Picks the SHORTEST matching parent path so the dataset's nested duplicate
    copy (identical images) is ignored.
    """
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


def _images_in(folder):
    return sorted(os.path.join(folder, f) for f in os.listdir(folder)
                  if os.path.splitext(f)[1].lower() in IMAGE_EXTS)


class ClassPairDataset(torch.utils.data.Dataset):
    """Real/fake image folders joined into one dataset. real=0, fake=1."""

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
    return ClassPairDataset(_images_in(real_dir), _images_in(fake_dir), transform)


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
    if hasattr(model, "classifier"):      # EfficientNet / MobileNet
        return [model.classifier]
    if hasattr(model, "fc"):              # ResNet
        return [model.fc]
    if hasattr(model, "heads"):           # ViT
        return [model.heads]
    return []


def apply_freeze(model):
    """Optionally freeze the backbone and train only the head (CPU-friendly)."""
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


# %% [markdown]
# ## 3. main() — download, data, train, evaluate, export

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
    if DATA_ROOT:
        root = DATA_ROOT
    else:
        try:
            import kagglehub
            print(f"Downloading dataset {DATASET_HANDLE} via kagglehub ...")
            root = kagglehub.dataset_download(DATASET_HANDLE)
        except Exception as exc:  # noqa: BLE001
            print(f"kagglehub failed ({exc}); trying kaggle CLI ...")
            tmp = "/kaggle/working/dl" if _IS_KAGGLE else os.path.join(PLOT_DIR, "dl")
            shutil.rmtree(tmp, ignore_errors=True)
            import subprocess
            subprocess.run(["kaggle", "datasets", "download", "-d", DATASET_HANDLE,
                            "-p", tmp, "--unzip"], check=True)
            root = tmp
    print("Dataset root:", root)

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
        if splits.get("val"):
            val_ds = remap_imagefolder(datasets.ImageFolder(root=splits["val"], transform=eval_tf),
                                       real_name, fake_name)
        else:
            val_ds = None
        test_ds = (remap_imagefolder(datasets.ImageFolder(root=splits["test"], transform=eval_tf),
                                     real_name, fake_name)
                   if splits.get("test") else None)
    else:
        found = find_class_root(root)
        if found is None:
            raise RuntimeError(
                f"No train split or real/fake class folders found under {root}. "
                "Set DATA_ROOT to a folder containing train/{real,fake} or "
                "training_real/ + training_fake/.")
        _, real_dir, fake_dir = found
        real_name = os.path.basename(real_dir)
        fake_name = os.path.basename(fake_dir)
        print(f"Flat layout: real='{real_name}' ({len(_images_in(real_dir))} img), "
              f"fake='{fake_name}' ({len(_images_in(fake_dir))} img)")
        train_ds = build_classpair(real_dir, fake_dir, train_tf)
        val_ds = None
        test_ds = None

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
                "train_samples": len(train_ds),
                "epoch": epoch,                      # resume support
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
    plt.savefig(os.path.join(PLOT_DIR, "training_curves.png"), dpi=120)
    plt.show()

    # ---------------------------- evaluation ------------------------------ #
    y_val, y_val_true = predict_loader(model, val_loader, device, USE_AMP)
    report(y_val_true, y_val, "VALIDATION", real_name, fake_name)
    if test_loader:
        y_test, y_test_true = predict_loader(model, test_loader, device, USE_AMP)
        report(y_test_true, y_test, "TEST", real_name, fake_name)

    cm = confusion_matrix(y_val_true, y_val, labels=[REAL_LABEL, FAKE_LABEL])
    plt.figure(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=[real_name, fake_name], yticklabels=[real_name, fake_name])
    plt.title(f"Confusion Matrix — Validation (acc {accuracy_score(y_val_true, y_val):.3f})")
    plt.ylabel("True"); plt.xlabel("Predicted")
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "confusion_matrix.png"), dpi=120)
    plt.show()

    # --------------------------- export summary --------------------------- #
    ckpt = torch.load(MODEL_OUTPUT, map_location="cpu", weights_only=True)
    print("\nCheckpoint keys:", list(ckpt.keys()))
    print(f"backbone={ckpt['backbone']} | classes={ckpt['classes']} | "
          f"fake_label={ckpt['fake_label']} | image_size={ckpt['image_size']} | "
          f"val_accuracy={ckpt['val_accuracy']}")

    if _IS_KAGGLE:
        print("\nDONE. Download marianalysis_cnn.pt from the notebook Output tab and")
        print("copy it to backend/models/faces_real_vs_fake_cnn.pt, then set")
        print("MODEL_ENABLED=true in backend/.env.")
    else:
        print(f"\nModel ready locally at {os.path.abspath(MODEL_OUTPUT)}. Copy it to")
        print("backend/models/faces_real_vs_fake_cnn.pt and set MODEL_ENABLED=true.")


# %%
if __name__ == "__main__":
    main()
