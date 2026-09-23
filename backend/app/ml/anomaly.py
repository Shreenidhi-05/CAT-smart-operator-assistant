"""Rolling-window anomaly detection: per-metric z-score vs baseline + Isolation Forest."""
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ..config import ANOMALY_Z_THRESHOLD, MODEL_DIR, SENSOR_METRICS

IFOREST_PATH = MODEL_DIR / "isolation_forest.pkl"
BASELINES_PATH = MODEL_DIR / "baselines.pkl"

_iforest: IsolationForest | None = None
_baselines: dict | None = None

METRIC_LABELS = {
    "fuel_used": "fuel consumption",
    "load_cycles": "load cycles",
    "idling_min": "idling time",
    "engine_hours": "engine hours",
}


def compute_baselines(df: pd.DataFrame) -> dict:
    """Return {'fleet': {metric: (mean, std)}, 'operators': {op_id: {metric: (mean,std)}}}."""
    def stats(sub: pd.DataFrame) -> dict:
        return {m: (float(sub[m].mean()), float(sub[m].std(ddof=0)) or 1e-6) for m in SENSOR_METRICS}

    ops = {int(op): stats(g) for op, g in df.groupby("operator_id")}
    return {"fleet": stats(df), "operators": ops}


def train(df: pd.DataFrame) -> None:
    global _iforest, _baselines
    normal = df[~df["safety_alert_triggered"].astype(bool)] if "safety_alert_triggered" in df else df
    model = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
    model.fit(normal[SENSOR_METRICS].values)
    _iforest = model
    _baselines = compute_baselines(normal)
    with open(IFOREST_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(BASELINES_PATH, "wb") as f:
        pickle.dump(_baselines, f)


def load():
    global _iforest, _baselines
    if _iforest is None and IFOREST_PATH.exists():
        with open(IFOREST_PATH, "rb") as f:
            _iforest = pickle.load(f)
    if _baselines is None and BASELINES_PATH.exists():
        with open(BASELINES_PATH, "rb") as f:
            _baselines = pickle.load(f)
    return _iforest, _baselines


def analyze_window(rows: list[dict], operator_id: int, completed_tasks: int, cold_start_min: int) -> dict:
    """rows: recent sensor_logs dicts. Returns anomaly verdict + interpretable explanation."""
    iforest, baselines = load()
    if not rows or baselines is None:
        return {"anomaly": False, "reasons": [], "explanation": "", "baseline": "none"}

    window = pd.DataFrame(rows)
    means = window[SENSOR_METRICS].mean()

    use_personal = completed_tasks >= cold_start_min and operator_id in baselines["operators"]
    base = baselines["operators"][operator_id] if use_personal else baselines["fleet"]
    baseline_name = "personal" if use_personal else "fleet-wide (cold start)"

    reasons = []
    zscores = {}
    for m in SENSOR_METRICS:
        mu, sd = base[m]
        z = float((means[m] - mu) / sd) if sd else 0.0
        zscores[m] = round(z, 2)
        if abs(z) >= ANOMALY_Z_THRESHOLD:
            direction = "above" if z > 0 else "below"
            reasons.append({
                "metric": m, "z": round(z, 2), "observed": round(float(means[m]), 2),
                "baseline_mean": round(mu, 2),
                "text": f"{METRIC_LABELS[m]} is {abs(z):.1f}σ {direction} your {baseline_name} baseline "
                        f"({means[m]:.1f} vs {mu:.1f})",
            })

    iso_flag = False
    iso_score = None
    if iforest is not None:
        X = window[SENSOR_METRICS].values
        preds = iforest.predict(X)
        iso_score = float(np.mean(iforest.decision_function(X)))
        iso_flag = bool((preds == -1).mean() >= 0.5)

    anomaly = bool(reasons) or iso_flag
    explanation = ""
    if anomaly:
        if reasons:
            ranked = sorted(reasons, key=lambda r: -abs(r["z"]))
            top = ranked[0]
            explanation = f"Anomaly detected: {top['text']}."
            if len(ranked) > 1:
                explanation += " Also: " + "; ".join(r["text"] for r in ranked[1:]) + "."
            if "idling_min" in [r["metric"] for r in reasons] and top["z"] > 0:
                explanation += " Extended idling often means waiting on a truck or a blocked path — log a planned pause if this is expected."
            if "fuel_used" in [r["metric"] for r in reasons] and top["z"] > 0:
                explanation += " High fuel burn with normal cycles can indicate excessive throttle or a mechanical issue."
        else:
            explanation = ("Isolation Forest flagged the combination of recent readings as unusual "
                           "(multivariate pattern outside normal operating envelope), even though no single metric is extreme.")
    return {
        "anomaly": anomaly, "reasons": reasons, "zscores": zscores, "isolation_forest_flag": iso_flag,
        "isolation_forest_score": iso_score, "explanation": explanation, "baseline": baseline_name,
    }
