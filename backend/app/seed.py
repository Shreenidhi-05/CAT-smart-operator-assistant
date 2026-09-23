"""Seed users, vehicles, assignments, training modules, synthetic sensor logs and task history."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import DATA_DIR
from .models import SensorLog, Task, TrainingModule, User, Vehicle, VehicleAssignment

DEMO_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_scenarios.json"

USERS = [
    ("admin", "admin", "admin123", 3),
    ("maya", "operator", "operator123", 3),   # id 2 — veteran, personal baseline
    ("raj", "operator", "operator123", 2),    # id 3
    ("leo", "operator", "operator123", 1),    # id 4 — new hire, cold start (fleet baseline)
    ("sam", "operator", "operator123", 2),    # id 5
]
VEHICLES = [(1, "Excavator", 2), (2, "Dozer", 3), (3, "Wheel Loader", 4), (4, "Articulated Truck", 5)]
TRAINING = [
    ("Seatbelt: Buckle Up Before You Start", "seatbelt", "https://www.youtube.com/embed/X3KszN-1e8U"),
    ("Proximity Awareness Around Heavy Equipment", "proximity", "https://www.youtube.com/embed/Oxfjvpwn944"),
    ("Reducing Idle Time", "idling", "https://www.youtube.com/embed/H6kRU_2z73Y"),
]


def seed(db: Session) -> None:
    if db.scalar(select(User).limit(1)):
        return
    users = {}
    for name, role, pw, skill in USERS:
        u = User(name=name, role=role, password_hash=hash_password(pw), skill_level=skill)
        db.add(u)
        users[name] = u
    db.flush()
    for vid, mt, op in VEHICLES:
        db.add(Vehicle(id=vid, machine_type=mt, current_operator_id=op))
        db.add(VehicleAssignment(operator_id=op, vehicle_id=vid))
    for title, trig, url in TRAINING:
        db.add(TrainingModule(title=title, trigger_behavior=trig, video_url=url))
    db.flush()

    # historical completed tasks (gives personal baselines / "last time for this task")
    tasks_csv = DATA_DIR / "synthetic_tasks.csv"
    if tasks_csv.exists():
        df = pd.read_csv(tasks_csv)
        # maya/raj/sam get plenty of history; leo (id 4) gets only 2 -> cold start
        per_op = {2: 12, 3: 10, 4: 2, 5: 8}
        t0 = datetime.utcnow() - timedelta(days=30)
        for op, n in per_op.items():
            sub = df[df.operator_id == op].head(n)
            vid = {2: 1, 3: 2, 4: 3, 5: 4}[op]
            for i, r in enumerate(sub.itertuples()):
                start = t0 + timedelta(days=i * 2, hours=8)
                db.add(Task(operator_id=op, vehicle_id=vid, zone="Zone A - Pit", task_type=r.task_type, status="completed",
                            predicted_time_min=round(r.duration_min * 0.98, 1),
                            predicted_range_min=f"{round(r.duration_min*0.85,1)}-{round(r.duration_min*1.2,1)}",
                            actual_start=start, actual_end=start + timedelta(minutes=float(r.duration_min)),
                            total_idle_min=round(r.duration_min * 0.08, 1), ground_condition=r.ground_condition,
                            ground_moisture=r.ground_moisture, obstacle_distance_m=r.obstacle_distance_m,
                            weather_json=json.dumps(dict(temp_c=r.temp_c, wind_kmh=r.wind_kmh, visibility_m=r.visibility_m))))
    logs_csv = DATA_DIR / "synthetic_sensor_logs.csv"
    if logs_csv.exists():
        for r in pd.read_csv(logs_csv).itertuples():
            db.add(SensorLog(task_id=None, machine_id=int(r.machine_id), operator_id=int(r.operator_id),
                             timestamp=datetime.fromisoformat(r.timestamp), engine_hours=r.engine_hours,
                             fuel_used=r.fuel_used, load_cycles=int(r.load_cycles), idling_min=r.idling_min,
                             seatbelt_status=r.seatbelt_status, safety_alert_triggered=bool(r.safety_alert_triggered)))
    db.commit()


def demo_scenarios() -> list[dict]:
    return json.loads(DEMO_PATH.read_text())
