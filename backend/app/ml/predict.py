"""LightGBM quantile regression for task duration (p10 / p50 / p90)."""
import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..config import MODEL_DIR

MACHINE_TYPES = ["Excavator", "Dozer", "Wheel Loader", "Articulated Truck", "Motor Grader"]
TASK_TYPES = ["Excavation", "Hauling", "Grading", "Loading", "Trenching"]
GROUND_CONDITIONS = ["dry", "damp", "wet", "muddy"]
FEATURES = [
    "machine_type", "task_type", "ground_condition", "ground_moisture",
    "obstacle_distance_m", "operator_skill", "temp_c", "wind_kmh", "visibility_m",
]
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
MODEL_PATH = MODEL_DIR / "task_time_lgbm.pkl"

_models: dict[str, lgb.LGBMRegressor] | None = None


def encode(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["machine_type"] = pd.Categorical(out["machine_type"], categories=MACHINE_TYPES).codes
    out["task_type"] = pd.Categorical(out["task_type"], categories=TASK_TYPES).codes
    out["ground_condition"] = pd.Categorical(out["ground_condition"], categories=GROUND_CONDITIONS).codes
    return out[FEATURES].astype(float)


def train(df: pd.DataFrame) -> dict[str, lgb.LGBMRegressor]:
    X = encode(df)
    y = df["duration_min"].values
    models = {}
    for name, q in QUANTILES.items():
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=200,
                              learning_rate=0.05, num_leaves=15, min_child_samples=5, verbose=-1)
        m.fit(X, y)
        models[name] = m
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(models, f)
    return models


def load() -> dict[str, lgb.LGBMRegressor] | None:
    global _models
    if _models is None and MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            _models = pickle.load(f)
    return _models


def predict(params: dict) -> dict:
    models = load()
    if models is None:
        return {"p10": 40.0, "p50": 60.0, "p90": 90.0, "model": "fallback"}
    X = encode(pd.DataFrame([params]))
    preds = {k: float(np.clip(m.predict(X)[0], 5, None)) for k, m in models.items()}
    lo, mid, hi = sorted([preds["p10"], preds["p50"], preds["p90"]])
    return {"p10": round(lo, 1), "p50": round(mid, 1), "p90": round(hi, 1), "model": "lightgbm-quantile"}
