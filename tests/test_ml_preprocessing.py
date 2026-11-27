"""Tests for ml/preprocessing.py and a smoke test of the full training script.

The data here is tiny and synthetic: it only checks the code works, it says nothing about model quality.
"""
import json
import sys

import joblib
import numpy as np
import pandas as pd
import pytest

from ml import train
from ml.preprocessing import build_pipeline, load_csvs, map_label, normalize_columns, prepare_dataset, to_finite


def raw_frame(n_per_class: int = 40, seed: int = 0) -> pd.DataFrame:
    """A CICIDS2017-shaped frame: leading spaces in names, duplicate column, inf values, broken dash."""
    rng = np.random.default_rng(seed)
    labels = ["BENIGN", "DDoS", "Web Attack \x96 XSS"]
    rows = []
    for i, label in enumerate(labels):
        for _ in range(n_per_class):
            rows.append([rng.normal(i * 10, 1), rng.normal(i * 5, 1), rng.normal(0, 1), label])
    df = pd.DataFrame(rows, columns=[" Flow Duration", " Flow Bytes/s", "Fwd Header Length.1", " Label"])
    df.loc[0, " Flow Bytes/s"] = np.inf
    return df


def test_normalize_columns_strips_names_and_drops_duplicate():
    df = normalize_columns(raw_frame())
    assert list(df.columns) == ["Flow Duration", "Flow Bytes/s", "Label"]


def test_normalize_columns_drops_identifier_columns():
    df = pd.DataFrame(columns=["Flow ID", " Source IP", " Source Port", " Destination IP", " Timestamp", " Protocol", " Label"])
    assert list(normalize_columns(df).columns) == ["Protocol", "Label"]


@pytest.mark.parametrize("raw,expected", [
    ("BENIGN", "BENIGN"),
    (" DoS Hulk ", "DoS"),
    ("SSH-Patator", "BruteForce"),
    ("Web Attack � Sql Injection", "WebAttack"),
    ("Heartbleed", None),
    ("Infiltration", None),
])
def test_map_label(raw, expected):
    assert map_label(raw) == expected


def test_to_finite_replaces_inf_with_nan():
    out = to_finite(np.array([[1.0, np.inf], [-np.inf, 2.0]]))
    assert out.dtype == np.float32
    assert np.isnan(out[0, 1]) and np.isnan(out[1, 0]) and out[1, 1] == 2.0


def test_prepare_dataset_drops_unknown_labels_duplicates_and_conflicts():
    df = normalize_columns(raw_frame())
    extra = pd.DataFrame([
        df.iloc[1].to_dict(),                                                 # exact duplicate
        {**df.iloc[2].to_dict(), "Label": "DDoS"},                            # same features, other label
        {"Flow Duration": 1.0, "Flow Bytes/s": 1.0, "Label": "Heartbleed"},   # dropped class
        {"Flow Duration": "oops", "Flow Bytes/s": 3.0, "Label": "BENIGN"},    # junk cell -> NaN
        {"Flow Duration": np.nan, "Flow Bytes/s": np.nan, "Label": np.nan},   # blank row
    ])
    X, y, stats = prepare_dataset(pd.concat([df, extra], ignore_index=True))

    assert stats["dropped_labels"] == {"Heartbleed": 1, "<missing>": 1}
    assert stats["duplicates_removed"] == 1
    assert stats["conflicting_rows_removed"] == 2
    assert set(y) == {"BENIGN", "DDoS", "WebAttack"}
    assert not X.duplicated().any()
    assert X["Flow Duration"].isna().sum() == 1


def test_prepare_dataset_requires_label_column():
    with pytest.raises(ValueError):
        prepare_dataset(pd.DataFrame({"a": [1]}))


def test_pipeline_handles_inf_and_all_nan_column():
    from sklearn.tree import DecisionTreeClassifier
    X = pd.DataFrame({"a": [0.0, 1.0, 10.0, 11.0], "b": [np.nan] * 4})
    pipe = build_pipeline(DecisionTreeClassifier(random_state=0)).fit(X, [0, 0, 1, 1])
    assert list(pipe.predict(pd.DataFrame({"a": [np.inf, 10.5], "b": [np.nan, np.nan]}))) in ([0, 1], [1, 1])


def test_load_csvs_errors_on_empty_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_csvs(tmp_path)


def test_train_script_end_to_end(tmp_path, monkeypatch):
    data_dir, out = tmp_path / "raw", tmp_path / "artifacts"
    data_dir.mkdir()
    raw_frame(seed=1).to_csv(data_dir / "a.csv", index=False, encoding="latin-1")
    raw_frame(seed=2).to_csv(data_dir / "b.csv", index=False, encoding="latin-1")
    monkeypatch.setattr(sys, "argv", ["train", "--data-dir", str(data_dir), "--out", str(out)])

    train.main()

    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["selected_model"] in {"random_forest", "xgboost"}
    assert metrics["classes"] == ["BENIGN", "DDoS", "WebAttack"]
    for m in metrics["models"].values():
        assert m["test"]["confusion_matrix"]["labels"] == metrics["classes"]

    # The saved bundle must predict on new raw-style rows without retraining.
    bundle = joblib.load(out / "model.joblib")
    X_new = normalize_columns(raw_frame(n_per_class=2, seed=3))[bundle["feature_columns"]]
    assert len(bundle["pipeline"].predict(X_new)) == 6
