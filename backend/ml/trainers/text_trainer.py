"""AI-vs-human text trainer - runs on the Kaggle GPU cloud.

Self-contained script executed by a Kaggle Notebook. Trains a
TfidfVectorizer + LogisticRegression on an AI vs human text dataset pulled via
kagglehub (on Kaggle's machine - nothing is downloaded to the app server).

Output (in /kaggle/working):
    model.pkl          pickled (vectorizer, classifier) via joblib
    model_info.json    test accuracy, class map, vectorizer params
"""
import json
import os
import sys

try:
    import kagglehub
except ImportError:  # pragma: no cover
    kagglehub = None

try:
    import joblib
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
except ImportError as exc:  # pragma: no cover
    print(f"FATAL: missing dependency: {exc}", file=sys.stderr)
    sys.exit(1)

DATASET_SLUG = os.environ.get("KAGGLE_DATASET", "alitaqishah/ai-vs-human-text-classification-dataset-2026")
MAX_FEATURES = int(os.environ.get("MAX_FEATURES", "20000"))
TEST_SIZE = float(os.environ.get("TEST_SIZE", "0.15"))


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


def find_csv(root):
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.lower().endswith(".csv"):
                path = os.path.join(dirpath, name)
                # Prefer the biggest CSV (usually the main labelled split).
                try:
                    return path, os.path.getsize(path)
                except OSError:
                    return path, 0
    return None, None


def guess_label(values):
    """Return 1 for AI-generated, 0 for human-written from a label series."""
    sample = [str(v).strip().lower() for v in values[:500]]
    counts = {}
    for v in sample:
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return None
    common = max(counts, key=counts.get)
    if common in ("0", "1"):
        return [1 if str(v).strip() == "1" else 0 for v in values]
    if common in ("ai", "gpt", "machine", "fake"):
        return [1 if str(v).strip().lower() in ("ai", "gpt", "machine", "fake", "generated") else 0 for v in values]
    return [0 if str(v).strip().lower() in ("human", "real", "true") else 1 for v in values]


def main():
    print(f"dataset: {DATASET_SLUG}", flush=True)
    root = load_dataset()
    csv_path, _size = find_csv(root)
    if not csv_path:
        raise RuntimeError("No CSV found in the text dataset.")
    print(f"CSV: {csv_path}", flush=True)

    try:
        import pandas as pd
        df = pd.read_csv(csv_path, nrows=int(os.environ.get("MAX_ROWS", "50000")))
    except ImportError:
        import csv as _csv
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as fh:
            rows = list(_csv.reader(fh))
        if not rows:
            raise RuntimeError("Empty CSV.")
        header = rows[0]
        df = [dict(zip(header, r)) for r in rows[1:]]
        df = {k: [r.get(k, "") for r in df] for k in header}

    cols = [str(c) for c in df.columns]
    text_col = max(cols, key=lambda c: float(df[c].astype(str).str.len().mean()) if hasattr(df[c], "astype") else 0.0)
    label_col = next((c for c in cols if any(k in str(c).lower() for k in ("label", "class", "category", "source", "generated"))), None)
    if not label_col or label_col == text_col:
        label_col = next((c for c in cols if c != text_col), None)
    if not label_col:
        raise RuntimeError("Could not detect a label column.")

    X = df[text_col].astype(str).fillna("").tolist()
    y = guess_label(df[label_col].tolist())
    if y is None:
        raise RuntimeError("Could not interpret the label column values.")
    print(f"text_col={text_col} label_col={label_col} rows={len(X)}", flush=True)

    vec = TfidfVectorizer(max_features=MAX_FEATURES, ngram_range=(1, 2),
                          stop_words="english", sublinear_tf=True)
    Xv = vec.fit_transform(X)
    Xtr, Xte, ytr, yte = train_test_split(Xv, np.array(y), test_size=TEST_SIZE,
                                          random_state=42, stratify=np.array(y) if len(set(y)) > 1 else None)

    clf = LogisticRegression(C=1.0, max_iter=500, n_jobs=-1)
    clf.fit(Xtr, ytr)
    test_acc = clf.score(Xte, yte)
    print(f"test_accuracy={test_acc:.4f}", flush=True)

    joblib.dump({"vectorizer": vec, "classifier": clf}, "/kaggle/working/model.pkl")
    info = {
        "media": "text",
        "dataset": DATASET_SLUG,
        "architecture": "TfidfVectorizer + LogisticRegression",
        "max_features": MAX_FEATURES,
        "test_accuracy": round(float(test_acc), 4),
        "train_samples": int(Xtr.shape[0]),
        "test_samples": int(Xte.shape[0]),
        "label_map": {"0": "human", "1": "ai"},
    }
    with open("/kaggle/working/model_info.json", "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2)
    print(json.dumps(info), flush=True)
    print("TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
