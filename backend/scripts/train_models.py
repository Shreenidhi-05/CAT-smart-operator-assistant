"""Train LightGBM quantile model + Isolation Forest / baselines from synthetic CSVs."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA_DIR, MODEL_DIR  # noqa: E402
from app.ml import anomaly, predict  # noqa: E402

if __name__ == "__main__":
    tasks = pd.read_csv(DATA_DIR / "synthetic_tasks.csv")
    logs = pd.read_csv(DATA_DIR / "synthetic_sensor_logs.csv")
    predict.train(tasks)
    anomaly.train(logs)
    sample = predict.predict(dict(machine_type="Excavator", task_type="Excavation", ground_condition="dry",
                                  ground_moisture=0.15, obstacle_distance_m=10, operator_skill=2,
                                  temp_c=22, wind_kmh=10, visibility_m=5000))
    print("models saved to", MODEL_DIR, "| sample prediction:", sample)
