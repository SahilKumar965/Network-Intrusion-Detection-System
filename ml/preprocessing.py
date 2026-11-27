"""Shared preprocessing for CICIDS2017 flow records.

Used by training (ml/train.py) AND by the backend at prediction time, so both
clean data in exactly the same way. The saved pipeline refers to `to_finite`
by its import path (ml.preprocessing.to_finite), so this module must stay importable.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

LABEL_COLUMN = "Label"

# CICIDS2017 repeats "Fwd Header Length"; pandas reads the copy as "Fwd Header Length.1".
# The GeneratedLabelledFlows version also has identifiers. They are dropped to prevent leakage:
# attacks in this dataset come from a few known IPs at known times, so a model could memorise
# "attacker IP / time window" instead of learning traffic behaviour.
DROP_COLUMNS = ["Fwd Header Length.1", "Flow ID", "Source IP", "Source Port", "Destination IP", "Timestamp"]

# Raw label -> grouped class. Labels not listed here (Heartbleed, Infiltration) are dropped:
# 11 and 36 rows are too few to train on or to test honestly.
LABEL_MAP = {
    "BENIGN": "BENIGN",
    "DoS Hulk": "DoS",
    "DoS GoldenEye": "DoS",
    "DoS slowloris": "DoS",
    "DoS Slowhttptest": "DoS",
    "DDoS": "DDoS",
    "PortScan": "PortScan",
    "FTP-Patator": "BruteForce",
    "SSH-Patator": "BruteForce",
    "Bot": "Bot",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip the leading/trailing spaces CICIDS2017 puts in column names; drop duplicate and identifier columns."""
    df = df.rename(columns=lambda c: str(c).strip())
    return df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns])


def map_label(raw: str) -> str | None:
    """Map a raw CICIDS2017 label to its class, or None if the row should be dropped."""
    raw = str(raw).strip()
    # Web attack labels contain a broken dash character ("Web Attack � XSS"), so match by prefix.
    if raw.startswith("Web Attack"):
        return "WebAttack"
    return LABEL_MAP.get(raw)


def load_csvs(data_dir: Path, sample_frac: float = 1.0, seed: int = 42) -> pd.DataFrame:
    """Read every CSV in data_dir into one DataFrame (optionally a random sample of each file)."""
    files = sorted(Path(data_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")
    frames = []
    for f in files:
        # latin-1 never fails to decode; the only non-ASCII bytes are in the web attack labels.
        df = normalize_columns(pd.read_csv(f, encoding="latin-1", low_memory=False))
        if sample_frac < 1.0:
            df = df.sample(frac=sample_frac, random_state=seed)
        # float32 per file halves memory for the full ~3M rows; the model uses float32 anyway (see to_finite).
        feats = [c for c in df.columns if c != LABEL_COLUMN]
        df[feats] = df[feats].apply(pd.to_numeric, errors="coerce").astype(np.float32)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def to_finite(X) -> np.ndarray:
    """Convert to float32 and turn +/-inf (from divide-by-zero in Flow Bytes/s etc.) into NaN for the imputer."""
    arr = np.asarray(X, dtype=np.float32)
    arr[~np.isfinite(arr)] = np.nan
    return arr


def build_pipeline(model) -> Pipeline:
    """Cleaning + median imputation + model. Fitting it on training data only prevents leakage."""
    return Pipeline([
        ("clean", FunctionTransformer(to_finite)),
        # keep_empty_features: an all-NaN column in a batch must not change the column count.
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("model", model),
    ])


def prepare_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, dict]:
    """Map labels, drop unusable rows and duplicates. Returns features, labels and cleaning stats."""
    if LABEL_COLUMN not in df.columns:
        raise ValueError(f"Label column '{LABEL_COLUMN}' not found")
    stats = {"rows_loaded": len(df)}

    y = df[LABEL_COLUMN].map(map_label)
    # fillna: blank rows (288k in the Thursday WebAttacks file) have no label and must show up in the count too.
    dropped = df.loc[y.isna(), LABEL_COLUMN].fillna("<missing>").astype(str).str.strip()
    stats["dropped_labels"] = {k: int(v) for k, v in dropped.value_counts().items()}
    df = df[y.notna()].copy()
    df[LABEL_COLUMN] = y[y.notna()]

    feature_cols = [c for c in df.columns if c != LABEL_COLUMN]
    # Non-numeric junk in a feature cell becomes NaN and is imputed later.
    df[feature_cols] = df[feature_cols].apply(pd.to_numeric, errors="coerce")

    # Dedupe BEFORE splitting, otherwise identical rows land in both train and test.
    before = len(df)
    df = df.drop_duplicates()
    stats["duplicates_removed"] = before - len(df)

    # The same features with two different labels cannot be learned; drop all copies.
    conflicting = df.duplicated(subset=feature_cols, keep=False)
    stats["conflicting_rows_removed"] = int(conflicting.sum())
    df = df[~conflicting]

    stats["rows_used"] = len(df)
    stats["class_counts"] = df[LABEL_COLUMN].value_counts().to_dict()
    return df[feature_cols], df[LABEL_COLUMN], stats
