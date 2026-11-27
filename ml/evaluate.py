"""Model evaluation: the metrics function used by train.py, plus a CLI that
re-scores the saved model on the saved held-out test split.

    python -m ml.evaluate
"""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support

ARTIFACTS = Path(__file__).parent / "artifacts"


def evaluate_model(pipeline, X: pd.DataFrame, y: np.ndarray, classes: list[str]) -> dict:
    """All metrics for one model on one dataset split. y holds integer class ids."""
    pred = pipeline.predict(X)
    labels = list(range(len(classes)))
    p, r, f1, _ = precision_recall_fscore_support(y, pred, average="macro", labels=labels, zero_division=0)
    pw, rw, f1w, _ = precision_recall_fscore_support(y, pred, average="weighted", labels=labels, zero_division=0)
    report = classification_report(y, pred, labels=labels, target_names=classes, output_dict=True, zero_division=0)
    return {
        "rows": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "macro": {"precision": float(p), "recall": float(r), "f1": float(f1)},
        "weighted": {"precision": float(pw), "recall": float(rw), "f1": float(f1w)},
        "per_class": {
            c: {k: float(report[c][k]) for k in ("precision", "recall", "f1-score")} | {"support": int(report[c]["support"])}
            for c in classes
        },
        "confusion_matrix": {"labels": classes, "matrix": confusion_matrix(y, pred, labels=labels).tolist()},
    }


def print_summary(name: str, m: dict) -> None:
    print(f"\n== {name} ({m['rows']} rows) ==")
    print(f"accuracy {m['accuracy']:.4f} | macro P {m['macro']['precision']:.4f} R {m['macro']['recall']:.4f} F1 {m['macro']['f1']:.4f}")
    for c, v in m["per_class"].items():
        print(f"  {c:<11} P {v['precision']:.4f} R {v['recall']:.4f} F1 {v['f1-score']:.4f} n={v['support']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-evaluate the saved model on the saved test split")
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    args = ap.parse_args()

    bundle = joblib.load(args.artifacts / "model.joblib")
    test = pd.read_pickle(args.artifacts / "test_split.pkl.gz")
    classes = bundle["classes"]
    y = test.pop("Label").map({c: i for i, c in enumerate(classes)}).to_numpy()
    m = evaluate_model(bundle["pipeline"], test[bundle["feature_columns"]], y, classes)
    print_summary(f"{bundle['model_name']} on test split", m)

    saved = json.loads((args.artifacts / "metrics.json").read_text())["models"][bundle["model_name"]]["test"]
    if not np.isclose(saved["macro"]["f1"], m["macro"]["f1"]):
        raise SystemExit(f"Mismatch: metrics.json says macro F1 {saved['macro']['f1']:.4f}, re-evaluation gives {m['macro']['f1']:.4f}")
    print("\nMatches metrics.json.")


if __name__ == "__main__":
    main()
