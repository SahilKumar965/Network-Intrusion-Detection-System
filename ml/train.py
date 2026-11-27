"""Train Random Forest and XGBoost on CICIDS2017, pick the best by validation macro F1,
and save the pipeline + real metrics for the backend.

    python -m ml.train --sample-frac 0.05   # quick check of the whole pipeline
    python -m ml.train                      # full dataset
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from ml.evaluate import evaluate_model, print_summary
from ml.preprocessing import LABEL_COLUMN, build_pipeline, load_csvs, prepare_dataset

ROOT = Path(__file__).parent
SEED = 42


def cap_class(X: pd.DataFrame, y: pd.Series, label: str, cap: int) -> tuple[pd.DataFrame, pd.Series]:
    """Randomly keep at most `cap` rows of one class (training set only)."""
    idx = y.index[y == label]
    if len(idx) <= cap:
        return X, y
    drop = idx.difference(pd.Index(np.random.default_rng(SEED).choice(idx, cap, replace=False)))
    return X.drop(drop), y.drop(drop)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts")
    ap.add_argument("--sample-frac", type=float, default=1.0)
    ap.add_argument("--benign-cap", type=int, default=400_000, help="max BENIGN rows in the training set")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    X, y, stats = prepare_dataset(load_csvs(args.data_dir, args.sample_frac, SEED))
    print(f"Loaded in {time.time() - t0:.0f}s: {json.dumps(stats, indent=1)}")

    # 70 / 15 / 15 stratified split. The test set is only used once, after model selection.
    X_train, X_tmp, y_train, y_tmp = train_test_split(X, y, test_size=0.30, stratify=y, random_state=SEED)
    X_val, X_test, y_val, y_test = train_test_split(X_tmp, y_tmp, test_size=0.50, stratify=y_tmp, random_state=SEED)
    X_train, y_train = cap_class(X_train, y_train, "BENIGN", args.benign_cap)

    classes = sorted(y.unique())
    to_id = {c: i for i, c in enumerate(classes)}
    yt, yv, ys = (s.map(to_id).to_numpy() for s in (y_train, y_val, y_test))
    split_sizes = {"train": len(yt), "validation": len(yv), "test": len(ys)}
    print(f"Split sizes: {split_sizes}")

    candidates = {
        "random_forest": (
            RandomForestClassifier(n_estimators=100, class_weight="balanced_subsample", n_jobs=-1, random_state=SEED),
            {},
        ),
        "xgboost": (
            XGBClassifier(n_estimators=300, max_depth=8, learning_rate=0.1, tree_method="hist", n_jobs=-1, random_state=SEED),
            # XGBoost has no class_weight; balanced sample weights do the same job.
            {"model__sample_weight": compute_sample_weight("balanced", yt)},
        ),
    }

    fitted, results = {}, {}
    for name, (model, fit_kwargs) in candidates.items():
        t = time.time()
        pipe = build_pipeline(model).fit(X_train, yt, **fit_kwargs)
        results[name] = {"train_seconds": round(time.time() - t, 1), "validation": evaluate_model(pipe, X_val, yv, classes)}
        fitted[name] = pipe
        print_summary(f"{name} validation", results[name]["validation"])

    # Macro F1 treats every class equally, so rare attacks count as much as BENIGN.
    best = max(results, key=lambda n: results[n]["validation"]["macro"]["f1"])
    print(f"\nSelected: {best}")

    # Test metrics for every model (for the comparison page); selection above used validation only.
    for name, pipe in fitted.items():
        results[name]["test"] = evaluate_model(pipe, X_test, ys, classes)
        print_summary(f"{name} TEST", results[name]["test"])

    feature_columns = list(X.columns)
    joblib.dump(
        {"pipeline": fitted[best], "classes": classes, "feature_columns": feature_columns, "model_name": best},
        args.out / "model.joblib",
        compress=3,
    )
    pd.concat([X_test, y_test.rename(LABEL_COLUMN)], axis=1).to_pickle(args.out / "test_split.pkl.gz")
    metrics = {
        "selected_model": best,
        "selection_metric": "validation macro F1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "CICIDS2017",
        "source_files": sorted(p.name for p in args.data_dir.glob("*.csv")),
        "sample_frac": args.sample_frac,
        "benign_cap": args.benign_cap,
        "cleaning": stats,
        "split_sizes": split_sizes,
        "classes": classes,
        "feature_columns": feature_columns,
        "versions": {"scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__, "pandas": pd.__version__},
        "models": results,
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nSaved model.joblib and metrics.json to {args.out} (total {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
