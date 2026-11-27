"""Loads the trained pipeline once and runs predictions. The backend never trains.

joblib.load unpickles Python objects, so MODEL_PATH must only ever point at our own
training output, never at a user-supplied file.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BENIGN = "BENIGN"


class Predictor:
    def __init__(self, model_path: Path, metrics_path: Path):
        bundle = joblib.load(model_path)
        self.pipeline = bundle["pipeline"]
        self.classes: list[str] = bundle["classes"]
        self.feature_columns: list[str] = bundle["feature_columns"]
        self.model_name: str = bundle["model_name"]
        self.metrics: dict = json.loads(Path(metrics_path).read_text())

    def missing_columns(self, columns) -> list[str]:
        present = set(columns)
        return [c for c in self.feature_columns if c not in present]

    def predict(self, X: pd.DataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
        """X must contain every feature column (numeric, NaN allowed). Returns labels, confidences, probabilities."""
        proba = self.pipeline.predict_proba(X[self.feature_columns])
        best = proba.argmax(axis=1)
        return [self.classes[i] for i in best], proba[np.arange(len(best)), best], proba
