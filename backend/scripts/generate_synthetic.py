"""Generate synthetic sensor logs + historical task durations for model training.

Outputs (in backend/data):
  synthetic_sensor_logs.csv  — 500-1000 rows: timestamp, machine_id, operator_id, engine_hours,
                               fuel_used, load_cycles, idling_min, seatbelt_status, safety_alert_triggered
  synthetic_tasks.csv        — historical tasks with parameters + duration_min (LightGBM training)
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA_DIR  # noqa: E402
from app.ml.predict import GROUND_CONDITIONS, MACHINE_TYPES, TASK_TYPES  # noqa: E402

rng = np.random.default_rng(7)

# operator_id -> (skill, fuel_factor, idle_factor, cycles_factor)
OPERATORS = {
    2: dict(skill=3, fuel=0.9, idle=0.8, cycles=1.15),   # Maya — veteran
    3: dict(skill=2, fuel=1.0, idle=1.0, cycles=1.0),    # Raj — mid
    4: dict(skill=1, fuel=1.15, idle=1.4, cycles=0.85),  # Leo — new (cold start: few tasks)
    5: dict(skill=2, fuel=1.05, idle=1.1, cycles=0.95),  # Sam
}
MACHINES = {1: "Excavator", 2: "Dozer", 3: "Wheel Loader", 4: "Articulated Truck"}
BASE_DURATION = {"Excavation": 75, "Hauling": 50, "Grading": 65, "Loading": 40, "Trenching": 90}
MACHINE_FACTOR = {"Excavator": 1.0, "Dozer": 1.05, "Wheel Loader": 0.95, "Articulated Truck": 1.1, "Motor Grader": 1.0}


def gen_sensor_logs(n_rows: int = 800) -> pd.DataFrame:
    rows = []
    start = datetime(2026, 9, 1, 6, 0)
    engine_hours = {m: 1200.0 + 300 * i for i, m in enumerate(MACHINES)}
    for i in range(n_rows):
        op = int(rng.choice(list(OPERATORS)))
        p = OPERATORS[op]
        machine = int(rng.choice(list(MACHINES)))
        ts = start + timedelta(minutes=2 * i)
        engine_hours[machine] += 2 / 60
        anomalous = rng.random() < 0.05
        fuel = rng.normal(2.4 * p["fuel"], 0.35)
        cycles = rng.normal(6 * p["cycles"], 1.2)
        idle = max(0, rng.normal(0.4 * p["idle"], 0.2))
        if anomalous:
            kind = rng.choice(["idle", "fuel", "cycles"])
            if kind == "idle":
                idle += rng.uniform(1.2, 2.0)
            elif kind == "fuel":
                fuel *= rng.uniform(1.6, 2.2)
            else:
                cycles *= rng.uniform(0.2, 0.4)
        seatbelt = "fastened" if rng.random() > 0.03 else "unfastened"
        rows.append(dict(
            timestamp=ts.isoformat(), machine_id=machine, operator_id=op,
            engine_hours=round(engine_hours[machine], 2), fuel_used=round(max(0.2, fuel), 2),
            load_cycles=int(max(0, round(cycles))), idling_min=round(idle, 2),
            seatbelt_status=seatbelt, safety_alert_triggered=bool(anomalous or seatbelt != "fastened"),
        ))
    return pd.DataFrame(rows)


def gen_tasks(n: int = 600) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        op = int(rng.choice(list(OPERATORS)))
        skill = OPERATORS[op]["skill"]
        mt = str(rng.choice(MACHINE_TYPES[:4]))
        tt = str(rng.choice(TASK_TYPES))
        gc_idx = int(rng.choice(4, p=[0.45, 0.3, 0.15, 0.1]))
        gc = GROUND_CONDITIONS[gc_idx]
        moisture = float(np.clip(rng.normal([0.15, 0.35, 0.6, 0.8][gc_idx], 0.07), 0, 1))
        obstacle = float(np.clip(rng.exponential(8) + 1, 1, 40))
        temp = float(rng.normal(22, 8))
        wind = float(np.clip(rng.gamma(2, 8), 0, 70))
        vis = float(np.clip(rng.normal(3000, 1500), 30, 8000))
        d = BASE_DURATION[tt] * MACHINE_FACTOR[mt]
        d *= 1 + 0.35 * gc_idx / 3          # worse ground -> slower
        d *= 1.25 - 0.1 * skill              # skill 3 -> 0.95, skill 1 -> 1.15
        d *= 1 + max(0, (wind - 30)) / 100   # strong wind slows
        d *= 1 + max(0, (200 - vis)) / 400   # low visibility slows
        d *= 1 + max(0, (5 - obstacle)) / 20 # tight obstacles slow
        d *= rng.lognormal(0, 0.12)
        rows.append(dict(
            operator_id=op, operator_skill=skill, machine_type=mt, task_type=tt,
            ground_condition=gc, ground_moisture=round(moisture, 2), obstacle_distance_m=round(obstacle, 1),
            temp_c=round(temp, 1), wind_kmh=round(wind, 1), visibility_m=round(vis), duration_min=round(d, 1),
        ))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    logs = gen_sensor_logs()
    tasks = gen_tasks()
    logs.to_csv(DATA_DIR / "synthetic_sensor_logs.csv", index=False)
    tasks.to_csv(DATA_DIR / "synthetic_tasks.csv", index=False)
    print(f"wrote {len(logs)} sensor logs, {len(tasks)} tasks to {DATA_DIR}")
