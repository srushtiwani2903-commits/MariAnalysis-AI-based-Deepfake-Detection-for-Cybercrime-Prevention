"""Train the real-vs-AI image CNN straight from a dataset ZIP (no extraction).

CIFAKE and similar Kaggle archives ship hundreds of thousands of tiny files;
expanding them to disk is slow and fragile. This reads images directly from the
zip and writes a checkpoint in the exact format ``services/cnn_detector.py``
expects (``model`` state_dict + backbone/classes/fake_label/image_size/transform).

Usage (run with the app venv so torch+CUDA are available):
    python -m ml.train_image_cnn_zip --zip <path.zip> --out models/faces_real_vs_fake_cnn.pt
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import time
import zipfile

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
REAL_LABEL, FAKE_LABEL = 0, 1
REAL_TOKENS = {"real", "reals", "real_image", "real_images", "training_real",
               "real_faces", "original", "0"}
FAKE_TOKENS = {"fake", "fakes", "fake_image", "fake_images", "training_fake",
               "fake_faces", "ai", "ai_generated", "generated", "deepfake", "1"}


def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def classify(name):
    parts = [p for p in name.split("/") if p]
    for part in reversed(parts[:-1]):
        n = _norm(part)
        if n in FAKE_TOKENS:
            return FAKE_LABEL
        if n in REAL_TOKENS:
            return REAL_LABEL
    return None


def _is_split(name, want):
    parts = [p.lower() for p in name.split("/")]
    return want in parts


def build_model(backbone, num_classes=2):
    factory = getattr(models, backbone, None)
    if factory is None:
        raise ValueError(f"Unknown backbone '{backbone}'.")
    try:
        model = factory(weights="IMAGENET1K_V2")
    except Exception:
        model = factory(weights="IMAGENET1K_V1")
    if hasattr(model, "fc"):
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif hasattr(model, "classifier"):
        if isinstance(model.classifier, nn.Sequential):
            model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, num_classes)
        else:
            model.classifier = nn.Linear(model.classifier.in_features, num_classes)
    return model


class ZipImageDataset(Dataset):
    def __init__(self, zip_path, items, transform):
        self.zip_path = zip_path
        self.items = items
        self.transform = transform
        self._zf = None

    def _zip(self):
        if self._zf is None:
            self._zf = zipfile.ZipFile(self.zip_path)
        return self._zf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        name, label = self.items[idx]
        data = self._zip().read(name)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, label


def collect(zip_path, max_per_class):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist()
                 if os.path.splitext(n)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")]
    train = {"real": [], "fake": []}
    test = {"real": [], "fake": []}
    for n in names:
        label = classify(n)
        if label is None:
            continue
        key = "fake" if label == FAKE_LABEL else "real"
        bucket = test if _is_split(n, "test") else train
        bucket[key].append((n, label))
    rnd = random.Random(42)
    for split in (train, test):
        for key in split:
            rnd.shuffle(split[key])
            if max_per_class:
                split[key] = split[key][:max_per_class]
    return train, test


def make_loader(ds, batch, shuffle, workers):
    return DataLoader(ds, batch_size=batch, shuffle=shuffle, num_workers=workers,
                      pin_memory=True, persistent_workers=(workers > 0),
                      drop_last=False)


def run_epoch(model, loader, opt, crit, scaler, device, training, amp):
    model.train(training)
    loss_sum = correct = total = 0
    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        if training:
            opt.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(training):
            with torch.amp.autocast("cuda", enabled=amp):
                out = model(images)
                loss = crit(out, labels)
            if training:
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()
        loss_sum += loss.item() * images.size(0)
        correct += (out.argmax(1) == labels).sum().item()
        total += images.size(0)
    return loss_sum / max(total, 1), correct / max(total, 1)


def evaluate(model, loader, device, amp):
    model.eval()
    preds, trues = [], []
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            with torch.amp.autocast("cuda", enabled=amp):
                out = model(images)
            preds.extend(out.argmax(1).cpu().tolist())
            trues.extend(labels.tolist())
    return np.array(preds), np.array(trues)


def report(y_true, y_pred, name):
    from sklearn.metrics import (accuracy_score, classification_report,
                                 confusion_matrix)
    acc = accuracy_score(y_true, y_pred)
    print(f"\n===== {name} ===== accuracy={acc:.4f}")
    print(confusion_matrix(y_true, y_pred, labels=[REAL_LABEL, FAKE_LABEL]))
    print(classification_report(y_true, y_pred, target_names=["real", "fake"],
                                digits=3, zero_division=0))
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", default="models/faces_real_vs_fake_cnn.pt")
    ap.add_argument("--backbone", default="efficientnet_b0")
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--max-per-class", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = device.type == "cuda"
    if amp:
        torch.backends.cudnn.benchmark = True
        print("GPU:", torch.cuda.get_device_name(0))

    train_items, test_items = collect(args.zip, args.max_per_class)
    print("train:", {k: len(v) for k, v in train_items.items()},
          "| test:", {k: len(v) for k, v in test_items.items()})

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(args.image_size, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(int(args.image_size * 256 / 224)),
        transforms.CenterCrop(args.image_size),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])

    train_ds = ZipImageDataset(args.zip, train_items["real"] + train_items["fake"], train_tf)
    test_ds = ZipImageDataset(args.zip, test_items["real"] + test_items["fake"], eval_tf)
    tr = make_loader(train_ds, args.batch, True, args.workers)
    te = make_loader(test_ds, args.batch, False, args.workers)

    model = build_model(args.backbone).to(device)
    crit = nn.CrossEntropyLoss(label_smoothing=0.05)
    opt = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)

    best = 0.0
    for ep in range(1, args.epochs + 1):
        t = time.time()
        trl, tra = run_epoch(model, tr, opt, crit, scaler, device, True, amp)
        val_loss, val_acc = run_epoch(model, te, opt, crit, scaler, device, False, amp)
        sched.step()
        print(f"epoch {ep}/{args.epochs} | train {trl:.4f}/{tra:.3f} | "
              f"test {val_loss:.4f}/{val_acc:.3f} | {time.time()-t:.0f}s", flush=True)
        if val_acc >= best:
            best = val_acc
            torch.save({
                "model": model.state_dict(),
                "backbone": args.backbone,
                "classes": ["real", "fake"],
                "fake_label": FAKE_LABEL,
                "image_size": args.image_size,
                "transform": {"mean": MEAN, "std": STD},
                "val_accuracy": round(float(best), 4),
                "train_samples": len(train_ds),
                "dataset": os.path.basename(args.zip),
            }, args.out)
            print(f"  -> saved (test_acc={best:.3f})", flush=True)

    model.eval()
    y_pred, y_true = evaluate(model, te, device, amp)
    acc = report(y_true, y_pred, "CIFAKE TEST")
    print(f"\nFinal test accuracy: {acc:.4f} | best checkpoint acc: {best:.4f}")
    print(f"Deployed checkpoint: {os.path.abspath(args.out)}")
    with open(os.path.splitext(args.out)[0] + "_meta.json", "w", encoding="utf-8") as fh:
        json.dump({"test_accuracy": round(float(acc), 4), "best_test_accuracy": best,
                   "backbone": args.backbone, "image_size": args.image_size,
                   "train_samples": len(train_ds), "test_samples": len(test_ds)}, fh, indent=2)


if __name__ == "__main__":
    main()
