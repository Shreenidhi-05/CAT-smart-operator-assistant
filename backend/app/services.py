"""Core domain logic: alerts, incidents, escalation, device state, anomaly runs, task simulation."""
import json
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .ml import anomaly
from .models import Alert, Incident, SensorLog, Task, TrainingModule, User, Vehicle
from .ws import hub

# ---- per-vehicle device (cockpit sensor) state, fed by the vehicle device / simulator ----
DEVICE_STATE: dict[int, dict] = {}


def device_state(vehicle_id: int) -> dict:
    return DEVICE_STATE.setdefault(vehicle_id, {
        "seatbelt_status": "fastened", "proximity_m": 25.0,
        "seatbelt_last_change": datetime.utcnow(), "seatbelt_video_shown_at": None,
    })


def set_device_state(vehicle_id: int, seatbelt_status: str | None = None, proximity_m: float | None = None) -> dict:
    st = device_state(vehicle_id)
    if seatbelt_status is not None and seatbelt_status != st["seatbelt_status"]:
        st["seatbelt_status"] = seatbelt_status
        st["seatbelt_last_change"] = datetime.utcnow()
        st["seatbelt_video_shown_at"] = None
    if proximity_m is not None:
        st["proximity_m"] = proximity_m
    return st


def _alert_dict(a: Alert) -> dict:
    return dict(id=a.id, task_id=a.task_id, type=a.type, severity=a.severity, message=a.message,
                timestamp=a.timestamp, resolved=a.resolved, escalated=a.escalated, target=a.target)


def _incident_dict(i: Incident) -> dict:
    return dict(id=i.id, task_id=i.task_id, type=i.type, timestamp=i.timestamp, details=i.details,
                auto_generated=i.auto_generated)


def channels_for(task: Task | None, include_admin: bool = True) -> list[str]:
    ch = ["admin"] if include_admin else []
    if task:
        ch.append(f"operator:{task.operator_id}")
    return ch


def create_incident(db: Session, task: Task | None, type_: str, details: str) -> Incident:
    inc = Incident(task_id=task.id if task else None, type=type_, details=details, auto_generated=True)
    db.add(inc)
    db.flush()
    hub.emit_sync("incident", _incident_dict(inc), channels_for(task))
    return inc


def push_alert(db: Session, task: Task | None, type_: str, message: str, severity: str = "warning",
               target: str = "operator", count_unresolved: bool = True, extra: dict | None = None) -> Alert:
    a = Alert(task_id=task.id if task else None, type=type_, message=message, severity=severity, target=target)
    db.add(a)
    db.flush()
    payload = _alert_dict(a)
    if extra:
        payload.update(extra)
    hub.emit_sync("alert", payload, channels_for(task))

    if task and count_unresolved:
        task.unresolved_alert_count += 1
        if task.unresolved_alert_count >= config.UNRESOLVED_ALERT_ESCALATION:
            escalate(db, task)
    return a


def escalate(db: Session, task: Task) -> None:
    n = task.unresolved_alert_count
    for a in db.scalars(select(Alert).where(Alert.task_id == task.id, Alert.resolved.is_(False))):
        a.escalated = True
    msg = (f"Task #{task.id} has {n} unresolved alerts. Operator #{task.operator_id} on vehicle #{task.vehicle_id} "
           f"in {task.zone} needs supervisor attention.")
    esc = Alert(task_id=task.id, type="escalation", severity="critical", message=msg, target="admin", escalated=True)
    db.add(esc)
    db.flush()
    hub.emit_sync("alert", _alert_dict(esc), channels_for(task))
    create_incident(db, task, "escalation", msg)
    task.unresolved_alert_count = 0  # counter resets after escalation


def safety_incident(db: Session, task: Task | None, kind: str, details: str) -> Alert:
    """Safety alerts (seatbelt, proximity) always create an incident automatically."""
    a = push_alert(db, task, kind, details, severity="critical", count_unresolved=task is not None)
    create_incident(db, task, kind, details)
    return a


# ---- pre-task gate ----------------------------------------------------------------------

def check_safety_gate(db: Session, vehicle_id: int) -> dict:
    st = device_state(vehicle_id)
    module = db.scalar(select(TrainingModule).where(TrainingModule.trigger_behavior == "seatbelt"))
    prox_module = db.scalar(select(TrainingModule).where(TrainingModule.trigger_behavior == "proximity"))
    seatbelt_ok = st["seatbelt_status"] == "fastened"
    proximity_ok = st["proximity_m"] is None or st["proximity_m"] >= config.PROXIMITY_HAZARD_M
    result = dict(ok=seatbelt_ok and proximity_ok, seatbelt_status=st["seatbelt_status"],
                  proximity_m=st["proximity_m"], seatbelt_ok=seatbelt_ok, proximity_ok=proximity_ok,
                  sensor_fault=False, training_module=None)
    if not seatbelt_ok:
        if st["seatbelt_video_shown_at"] is None:
            st["seatbelt_video_shown_at"] = datetime.utcnow()
        unchanged_for = (datetime.utcnow() - max(st["seatbelt_last_change"], st["seatbelt_video_shown_at"])).total_seconds()
        result["seconds_since_video"] = int(unchanged_for)
        if unchanged_for > config.SEATBELT_FAULT_TIMEOUT_S:
            result["sensor_fault"] = True
        else:
            result["training_module"] = _module_dict(module)
    elif not proximity_ok:
        result["training_module"] = _module_dict(prox_module)
    return result


def _module_dict(m: TrainingModule | None) -> dict | None:
    return None if m is None else dict(id=m.id, title=m.title, trigger_behavior=m.trigger_behavior, video_url=m.video_url)


def risk_check(weather: dict, ground_moisture: float, obstacle_distance_m: float) -> dict:
    t = config.RISK_THRESHOLDS
    reasons = []
    if weather.get("wind_kmh", 0) > t["wind_kmh_max"]:
        reasons.append(f"Wind {weather['wind_kmh']:.0f} km/h exceeds {t['wind_kmh_max']:.0f} km/h limit")
    if weather.get("visibility_m", 10000) < t["visibility_m_min"]:
        reasons.append(f"Visibility {weather['visibility_m']:.0f} m below {t['visibility_m_min']:.0f} m minimum")
    if ground_moisture > t["ground_moisture_max"]:
        reasons.append(f"Ground moisture {ground_moisture:.2f} above {t['ground_moisture_max']:.2f} limit")
    if obstacle_distance_m < t["obstacle_distance_m_min"]:
        reasons.append(f"Obstacle at {obstacle_distance_m:.1f} m inside {t['obstacle_distance_m_min']:.0f} m clearance")
    return dict(risky=bool(reasons), reasons=reasons, thresholds=t)


# ---- live monitoring -------------------------------------------------------------------

def completed_task_count(db: Session, operator_id: int) -> int:
    return len(db.scalars(select(Task.id).where(Task.operator_id == operator_id, Task.status == "completed")).all())


def last_time_for_task(db: Session, operator_id: int, task_type: str, exclude_id: int) -> float | None:
    t = db.scalar(select(Task).where(Task.operator_id == operator_id, Task.task_type == task_type,
                                     Task.status == "completed", Task.id != exclude_id)
                  .order_by(Task.actual_end.desc()))
    if t and t.actual_start and t.actual_end:
        return round((t.actual_end - t.actual_start).total_seconds() / 60, 1)
    return None


def record_sensor_log(db: Session, task: Task, vehicle: Vehicle, scenario_progress: float) -> SensorLog:
    """Simulated telemetry row for the task. Scenario 'escalation' drives anomalous readings."""
    st = device_state(vehicle.id)
    last = db.scalar(select(SensorLog).where(SensorLog.machine_id == vehicle.id).order_by(SensorLog.timestamp.desc()))
    eh = (last.engine_hours if last else 1500.0) + config.SENSOR_INTERVAL_S / 3600
    fuel, cycles, idle = random.gauss(2.4, 0.3), random.gauss(6, 1), max(0, random.gauss(0.4, 0.15))
    if task.demo_scenario == "escalation":
        idle += random.uniform(1.5, 2.2)
        fuel *= random.uniform(1.7, 2.1)
        cycles *= random.uniform(0.2, 0.35)
    if task.paused:
        idle += 1.0
        cycles = 0
    row = SensorLog(task_id=task.id, machine_id=vehicle.id, operator_id=task.operator_id,
                    engine_hours=round(eh, 3), fuel_used=round(max(0.1, fuel), 2), load_cycles=int(max(0, round(cycles))),
                    idling_min=round(idle, 2), seatbelt_status=st["seatbelt_status"], zone=task.zone,
                    proximity_m=st["proximity_m"], safety_alert_triggered=False)
    db.add(row)
    db.flush()
    return row


def run_anomaly_check(db: Session, task: Task) -> dict:
    since = datetime.utcnow() - timedelta(minutes=config.ANOMALY_WINDOW_MIN)
    rows = db.scalars(select(SensorLog).where(SensorLog.task_id == task.id, SensorLog.timestamp >= since)).all()
    window = [dict(fuel_used=r.fuel_used, load_cycles=r.load_cycles, idling_min=r.idling_min) for r in rows]
    completed = completed_task_count(db, task.operator_id)
    result = anomaly.analyze_window(window, task.operator_id, completed, config.COLD_START_MIN_TASKS)
    result["window_rows"] = len(rows)
    result["checked_at"] = datetime.utcnow()
    if result["anomaly"]:
        for r in rows:
            r.safety_alert_triggered = True
        push_alert(db, task, "anomaly", result["explanation"], severity="warning",
                   extra={"reasons": result["reasons"], "zscores": result["zscores"], "baseline": result["baseline"]})
    hub.emit_sync("anomaly_check", {"task_id": task.id, **result}, channels_for(task))
    return result


def task_snapshot(db: Session, task: Task) -> dict:
    now = datetime.utcnow()
    end = task.actual_end or now
    elapsed = (end - task.actual_start).total_seconds() / 60 if task.actual_start else 0
    predicted = task.predicted_time_min or 60
    lo, hi = (task.predicted_range_min or f"{predicted}-{predicted}").split("-")
    pct = min(99, elapsed / predicted * 100) if task.status == "active" else (100 if task.status == "completed" else 0)
    weather = json.loads(task.weather_json) if task.weather_json else {}
    logs = db.scalars(select(SensorLog).where(SensorLog.task_id == task.id).order_by(SensorLog.timestamp.desc()).limit(30)).all()
    operator = db.get(User, task.operator_id)
    return dict(
        id=task.id, operator_id=task.operator_id, operator_name=operator.name if operator else None,
        vehicle_id=task.vehicle_id, zone=task.zone, task_type=task.task_type, status=task.status,
        predicted_time_min=task.predicted_time_min, predicted_range_min=task.predicted_range_min,
        actual_start=task.actual_start, actual_end=task.actual_end, total_idle_min=task.total_idle_min,
        paused=task.paused, unresolved_alert_count=task.unresolved_alert_count, demo_scenario=task.demo_scenario,
        elapsed_min=round(elapsed, 1), percent_complete=round(pct, 1),
        expected_finish=(task.actual_start + timedelta(minutes=float(lo))).isoformat() + " - " +
                        (task.actual_start + timedelta(minutes=float(hi))).isoformat() if task.actual_start else None,
        weather=weather, ground_condition=task.ground_condition, ground_moisture=task.ground_moisture,
        last_time_for_task=last_time_for_task(db, task.operator_id, task.task_type, task.id),
        recent_logs=[dict(timestamp=l.timestamp, fuel_used=l.fuel_used, load_cycles=l.load_cycles, idling_min=l.idling_min,
                          engine_hours=l.engine_hours, seatbelt_status=l.seatbelt_status, proximity_m=l.proximity_m,
                          safety_alert_triggered=l.safety_alert_triggered) for l in reversed(logs)],
    )


def complete_task(db: Session, task: Task) -> Task:
    task.status = "completed"
    task.actual_end = datetime.utcnow()
    # each telemetry row reports idle minutes for one sampling interval; scale to real interval and cap at task duration
    idle_sum = sum(r.idling_min for r in db.scalars(select(SensorLog).where(SensorLog.task_id == task.id)))
    elapsed_min = (task.actual_end - task.actual_start).total_seconds() / 60 if task.actual_start else 0
    task.total_idle_min = round(min(idle_sum * config.SENSOR_INTERVAL_S / 60, elapsed_min), 2)
    task.paused = False
    db.flush()
    hub.emit_sync("task_update", task_snapshot(db, task), channels_for(task))
    return task
