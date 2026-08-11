"""Audio deepfake (voice-clone) trainer - runs on the Kaggle GPU cloud.

Self-contained script executed by a Kaggle Notebook. Uses only stdlib ``wave``
+ numpy + torch (all preinstalled on Kaggle), so no extra audio deps needed.
Real speech vs AI-cloned speech clips are pulled via kagglehub on Kaggle's
machine and turned into FFT-based features, then an MLP classifies them.

Output (in /kaggle/working):
    model.pth          trained MLP weights (torch)
    model_info.json    feature list, test accuracy, feature mean/std
"""
import json
import math
import os
import random
import struct
import sys
import wave

try:
    import kagglehub
except ImportError:  # pragma: no cover
    kagglehub = None

try:
    import numpy as np
    import torch
    import torch.nn as nn
except ImportError as exc:  # pragma: no cover
    print(f"FATAL: missing dependency: {exc}", file=sys.stderr)
    sys.exit(1)

DATASET_SLUG = os.environ.get("KAGGLE_DATASET", "adarshsingh0903/audio-deepfake-detection-dataset")
SAMPLE_PER_CLASS = int(os.environ.get("SAMPLE_PER_CLASS", "1200"))
EPOCHS = int(os.environ.get("KAGGLE_EPOCHS", "8"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "64"))
SEED = int(os.environ.get("KAGGLE_SEED", "42"))

random.seed(SEED)
AUDIO_EXTS = {".wav", ".flac", ".m4a", ".ogg", ".mp3"}
FRAME_N = 1024
FRAME_HOP = 512
MEL_BANDS = 13
N_FEATURES = 5 + 2 * MEL_BANDS


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


def collect_audio(root):
    samples = {0: [], 1: []}
    for dirpath, _dirs, files in os.walk(root):
        # Match exact path components: the dataset root folder itself (e.g.
        # "audio-deepfake-detection-dataset") contains "deepfake"/"fake".
        rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
        parts = set(rel.split("/"))
        if any(k in parts for k in ("fake", "forged", "spoofed", "synthetic", "ai", "deepfake", "gpt")):
            label = 1
        elif any(k in parts for k in ("real", "original", "genuine", "authentic", "human", "bona-fide")):
            label = 0
        else:
            continue
        for name in files:
            if os.path.splitext(name)[1].lower() not in AUDIO_EXTS:
                continue
            samples[label].append(os.path.join(dirpath, name))
    return samples


def read_wav(path):
    """Return (samples float32, sample_rate) using the stdlib wave module."""
    try:
        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            n = wf.getnframes()
            raw = wf.readframes(min(n, sr * 10))  # cap at 10s
    except Exception:  # noqa: BLE001 - not a PCM wav (mp3/ogg/etc.)
        return None, 0
    if sw == 1:
        fmt = "B" if nch == 1 else None
    elif sw == 2:
        fmt = "<h" if nch == 1 else None
    else:
        fmt = None
    if fmt is None:
        try:
            fmt = f"<{'h' if sw == 2 else 'i'}{nch}"
            vals = struct.unpack(fmt * (len(raw) // (sw * nch)), raw)
        except Exception:  # noqa: BLE001
            return None, 0
    else:
        vals = struct.unpack(fmt * len(raw), raw)
    data = np.frombuffer(np.asarray(vals, dtype=np.float32), dtype=np.float32)
    data = data[::nch] if nch > 1 else data
    return data, sr


def mel_filterbank(n_fft, sr):
    """Simple triangular mel filterbank (numpy only)."""
    mel = lambda f: 2595.0 * math.log10(1.0 + f / 700.0)  # noqa: E731
    imel = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)  # noqa: E731
    lo, hi = imel(mel(20.0)), imel(mel(sr / 2.0))
    points = np.linspace(lo, hi, MEL_BANDS + 2)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    bank = np.zeros((MEL_BANDS, len(freqs)))
    for i in range(MEL_BANDS):
        l, c, r = points[i], points[i + 1], points[i + 2]
        for j, f in enumerate(freqs):
            if l <= f <= c:
                bank[i, j] = (f - l) / max(c - l, 1e-9)
            elif c < f <= r:
                bank[i, j] = (r - f) / max(r - c, 1e-9)
    return bank


def features_from_audio(data, sr):
    if data is None or len(data) < sr:  # need at least ~1s
        return None
    if len(data) % 2 == 1:
        data = data[:-1]
    n_frames = max(1, (len(data) - FRAME_N) // FRAME_HOP)
    mel = mel_filterbank(FRAME_N, sr)

    band_means = np.zeros(MEL_BANDS)
    band_stds = np.zeros(MEL_BANDS)
    flatness_sum = 0.0
    centroid_sum = 0.0
    zcr_sum = 0.0
    rolloff_sum = 0.0
    rms_sum = 0.0
    window = np.hanning(FRAME_N)

    for i in range(n_frames):
        start = i * FRAME_HOP
        frame = data[start:start + FRAME_N]
        spec = np.abs(np.fft.rfft(frame * window))
        power = spec ** 2
        total_power = power.sum() + 1e-12
        band_means += mel.dot(power)
        log_spec = np.log(spec + 1e-12)
        flatness_sum += np.exp(log_spec.mean()) / max(total_power / len(spec), 1e-12)
        freqs = np.fft.rfftfreq(FRAME_N, d=1.0 / sr)
        centroid_sum += (freqs * power).sum() / total_power
        cum = np.cumsum(power) / total_power
        rolloff_sum += freqs[np.searchsorted(cum, 0.85)]
        zcr_sum += np.mean(np.abs(np.diff(frame > 0)))
        rms_sum += float(np.sqrt((frame ** 2).mean()))

    if n_frames == 0:
        return None
    band_means /= n_frames
    # std computed on the per-frame band energies accumulated above
    for i in range(n_frames):
        start = i * FRAME_HOP
        frame = data[start:start + FRAME_N]
        power = (np.abs(np.fft.rfft(frame * window)) ** 2)
        band_stds += (mel.dot(power) - band_means) ** 2
    band_stds = np.sqrt(band_stds / n_frames)

    feats = np.concatenate([
        np.array([rms_sum / n_frames, zcr_sum / n_frames,
                  centroid_sum / n_frames, flatness_sum / n_frames,
                  rolloff_sum / n_frames]),
        band_means, band_stds,
    ]).astype(np.float32)
    feats[np.isnan(feats)] = 0.0
    feats[np.isinf(feats)] = 0.0
    return feats


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  dataset: {DATASET_SLUG}", flush=True)

    root = load_dataset()
    samples = collect_audio(root)
    print(f"Found real={len(samples[0])} fake={len(samples[1])}", flush=True)

    cap = min(SAMPLE_PER_CLASS, min(len(samples[0]), len(samples[1])))
    if cap == 0:
        raise RuntimeError("No labeled real/fake audio found - check the dataset structure.")
    chosen = {0: random.sample(samples[0], cap), 1: random.sample(samples[1], cap)}

    pairs = []
    for label, paths in chosen.items():
        for p in paths:
            data, sr = read_wav(p)
            feats = features_from_audio(data, sr)
            if feats is not None:
                pairs.append((feats, label))
    if len(pairs) < 50:
        raise RuntimeError("Too few usable audio clips (need PCM .wav files).")
    print(f"usable_clips={len(pairs)}", flush=True)

    random.shuffle(pairs)
    n_test = max(1, int(len(pairs) * 0.15))
    test_pairs, train_pairs = pairs[:n_test], pairs[n_test:]

    train_x = torch.tensor([x for x, _ in train_pairs])
    train_y = torch.tensor([y for _, y in train_pairs])
    mean = train_x.mean(0, keepdim=True)
    std = train_x.std(0, keepdim=True) + 1e-6
    train_x = (train_x - mean) / std

    test_x = torch.tensor([x for x, _ in test_pairs])
    test_x = (test_x - mean) / std
    test_y = torch.tensor([y for _, y in test_pairs])


    class MLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(N_FEATURES, 64), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(64, 64), nn.ReLU(),
                nn.Linear(64, 2),
            )

        def forward(self, x):
            return self.net(x)


    model = MLP().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    dataset = torch.utils.data.TensorDataset(train_x, train_y)
    loader = torch.utils.data.DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    for epoch in range(1, EPOCHS + 1):
        model.train()
        total, correct = 0, 0
        for xb, yb in loader:
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
        test_acc = (model(test_x.to(device)).argmax(1) == test_y.to(device)).float().mean().item()

    torch.save(model.state_dict(), "/kaggle/working/model.pth")
    info = {
        "media": "audio",
        "dataset": DATASET_SLUG,
        "architecture": "MLP (FFT features)",
        "n_features": N_FEATURES,
        "test_accuracy": round(test_acc, 4),
        "train_clips": len(train_pairs),
        "test_clips": len(test_pairs),
        "feature_mean": mean.flatten().tolist(),
        "feature_std": std.flatten().tolist(),
        "label_map": {"0": "real", "1": "fake"},
    }
    with open("/kaggle/working/model_info.json", "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    print(json.dumps(info), flush=True)
    print("TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
