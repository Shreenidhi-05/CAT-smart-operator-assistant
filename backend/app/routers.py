import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, services
from .auth import create_token, get_current_user, require_admin, verify_password
from .db import get_db
from .ml import predict
from .models import Alert, Incident, Task, TrainingModule, User, Vehicle, VehicleAssignment
from .schemas import DeviceStateIn, LoginIn, PrepareTaskIn, ReassignIn, TaskActionIn
from .seed import demo_scenarios
from .weather import get_weather
from .ws import hub

router = APIRouter(prefix="/api")


def _user(u: User) -> dict:
    return dict(id=u.id, name=u.name, role=u.role, skill_level=u.skill_level)


def _vehicle(v: Vehicle) -> dict:
    return dict(id=v.id, machine_type=v.machine_type, current_operator_id=v.current_operator_id)


def assigned_vehicle(db: Session, operator_id: int) -> VehicleAssignment | None:
    return db.scalar(select(VehicleAssignment).where(VehicleAssignment.operator_id == operator_id)
                     .order_by(VehicleAssignment.id.desc()))


def vehicle_check(db: Session, user: User, vehicle_id: int | None) -> dict:
    a = assigned_vehicle(db, user.id)
    if vehicle_id is None:
        return dict(ok=a is not None, assigned_vehicle_id=a.vehicle_id if a else None, device_vehicle_id=None)
    ok = a is not None and a.vehicle_id == vehicle_id
    return dict(ok=ok, assigned_vehicle_id=a.vehicle_id if a else None, device_vehicle_id=vehicle_id,
                message=None if ok else f"Wrong vehicle. You are assigned to vehicle #{a.vehicle_id if a else '?'}.")


# ---- auth -------------------------------------------------------------------------------

@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.name == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    out = dict(access_token=create_token(user), token_type="bearer", user=_user(user))
    if user.role == "operator":
        vc = vehicle_check(db, user, body.vehicle_id)
        out["vehicle_check"] = vc
        if body.vehicle_id is not None and not vc["ok"]:
            services.push_alert(db, None, "wrong_vehicle",
                                f"{user.name} attempted login on vehicle #{body.vehicle_id}; assigned vehicle is "
                                f"#{vc['assigned_vehicle_id']}", severity="warning", target="admin", count_unresolved=False)
            db.commit()
    return out


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return _user(user)


@router.get("/auth/vehicle-check")
def vehicle_check_ep(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return vehicle_check(db, user, vehicle_id)


# ---- vehicles / assignments -----------------------------------------------------------------

@router.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_vehicle(v) for v in db.scalars(select(Vehicle))]


@router.get("/vehicles/{vehicle_id}")
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    return _vehicle(v)


@router.get("/assignments")
def list_assignments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(VehicleAssignment)).all()
    latest = {}
    for r in rows:  # last assignment per operator wins
        latest[r.operator_id] = r
    return [dict(operator_id=r.operator_id, vehicle_id=r.vehicle_id, temporary=r.temporary, granted_by=r.granted_by)
            for r in latest.values()]


@router.post("/admin/override-assignment")
def override_assignment(body: ReassignIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Supervisor override: temporarily reassign an operator to a different vehicle."""
    if not db.get(User, body.operator_id) or not db.get(Vehicle, body.vehicle_id):
        raise HTTPException(404, "Operator or vehicle not found")
    a = VehicleAssignment(operator_id=body.operator_id, vehicle_id=body.vehicle_id, temporary=body.temporary,
                          granted_by=admin.id)
    db.add(a)
    v = db.get(Vehicle, body.vehicle_id)
    v.current_operator_id = body.operator_id
    db.commit()
    payload = dict(operator_id=body.operator_id, vehicle_id=body.vehicle_id, temporary=body.temporary, granted_by=admin.id)
    hub.emit_sync("assignment", payload, ["admin", f"operator:{body.operator_id}"])
    return payload


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_user(u) for u in db.scalars(select(User))]


# ---- device state (cockpit sensors) -------------------------------------------------------

@router.get("/device/{vehicle_id}")
def get_device(vehicle_id: int, _: User = Depends(get_current_user)):
    st = services.device_state(vehicle_id)
    return dict(vehicle_id=vehicle_id, seatbelt_status=st["seatbelt_status"], proximity_m=st["proximity_m"])


@router.post("/device/state")
def set_device(body: DeviceStateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    st = services.set_device_state(body.vehicle_id, body.seatbelt_status, body.proximity_m)
    # Safety events during an active task auto-create incidents
    task = db.scalar(select(Task).where(Task.vehicle_id == body.vehicle_id, Task.status == "active"))
    if task:
        if body.seatbelt_status == "unfastened":
            services.safety_incident(db, task, "seatbelt", f"Seatbelt unfastened during active task #{task.id}")
        if body.proximity_m is not None and body.proximity_m < config.PROXIMITY_HAZARD_M:
            services.safety_incident(db, task, "proximity",
                                     f"Proximity hazard: object at {body.proximity_m:.1f} m during task #{task.id}")
        db.commit()
    hub.emit_sync("device_state", dict(vehicle_id=body.vehicle_id, seatbelt_status=st["seatbelt_status"],
                                       proximity_m=st["proximity_m"]), ["admin", f"operator:{user.id}"])
    return dict(vehicle_id=body.vehicle_id, seatbelt_status=st["seatbelt_status"], proximity_m=st["proximity_m"])


# ---- pre-task gate ----------------------------------------------------------------------

@router.get("/safety-gate")
def safety_gate(vehicle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    res = services.check_safety_gate(db, vehicle_id)
    if res["sensor_fault"]:
        st = services.device_state(vehicle_id)
        if not st.get("fault_notified"):
            st["fault_notified"] = True
            services.push_alert(db, None, "sensor_fault",
                                f"Vehicle #{vehicle_id}: seatbelt sensor unchanged >{config.SEATBELT_FAULT_TIMEOUT_S}s after "
                                f"training prompt — probable sensor fault. Operator {user.name} awaiting supervisor.",
                                severity="critical", target="admin", count_unresolved=False)
            services.create_incident(db, None, "sensor_fault", f"Seatbelt sensor fault suspected on vehicle #{vehicle_id}")
            db.commit()
    elif res["seatbelt_ok"]:
        services.device_state(vehicle_id)["fault_notified"] = False
    return res


@router.get("/weather")
async def weather(zone: str | None = None):
    return await get_weather(zone)


@router.get("/config")
def get_config():
    return dict(risk_thresholds=config.RISK_THRESHOLDS, proximity_hazard_m=config.PROXIMITY_HAZARD_M,
                seatbelt_fault_timeout_s=config.SEATBELT_FAULT_TIMEOUT_S, sensor_interval_s=config.SENSOR_INTERVAL_S,
                anomaly_interval_s=config.ANOMALY_INTERVAL_S, escalation_after=config.UNRESOLVED_ALERT_ESCALATION,
                zones=["Zone A - Pit", "Zone B - Haul Road", "Zone C - Ridge", "Zone D - Stockpile"],
                task_types=predict.TASK_TYPES, ground_conditions=predict.GROUND_CONDITIONS)


@router.get("/demo-scenarios")
def list_demo_scenarios():
    return demo_scenarios()


@router.post("/tasks/prepare")
async def prepare_task(body: PrepareTaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Gather task parameters, run LightGBM quantile prediction and risk check. Creates a pending task."""
    vc = vehicle_check(db, user, body.vehicle_id)
    if not vc["ok"]:
        raise HTTPException(403, vc["message"])
    vehicle = db.get(Vehicle, body.vehicle_id)
    w = await get_weather(body.zone)
    params = dict(machine_type=vehicle.machine_type, task_type=body.task_type, ground_condition=body.ground_condition,
                  ground_moisture=body.ground_moisture, obstacle_distance_m=body.obstacle_distance_m,
                  operator_skill=user.skill_level, temp_c=w["temp_c"], wind_kmh=w["wind_kmh"], visibility_m=w["visibility_m"])
    pred = predict.predict(params)
    risk = services.risk_check(w, body.ground_moisture, body.obstacle_distance_m)
    gate = services.check_safety_gate(db, body.vehicle_id)

    existing = db.scalar(select(Task).where(Task.operator_id == user.id, Task.status.in_(["pending", "blocked", "suspended"])))
    task = existing or Task(operator_id=user.id, vehicle_id=body.vehicle_id)
    task.zone, task.task_type = body.zone, body.task_type
    task.vehicle_id = body.vehicle_id
    task.status = "suspended" if risk["risky"] else ("blocked" if not gate["ok"] else "pending")
    task.predicted_time_min = pred["p50"]
    task.predicted_range_min = f"{pred['p10']}-{pred['p90']}"
    task.weather_json = json.dumps(w)
    task.ground_condition, task.ground_moisture = body.ground_condition, body.ground_moisture
    task.obstacle_distance_m, task.demo_scenario = body.obstacle_distance_m, body.demo_scenario
    db.add(task)
    db.flush()
    if risk["risky"]:
        services.push_alert(db, task, "risk", "Risk check failed: " + "; ".join(risk["reasons"]) + ". Suspension suggested.",
                            severity="critical", count_unresolved=False)
    db.commit()
    return dict(task=services.task_snapshot(db, task), prediction=pred, params=params, weather=w, risk=risk, safety_gate=gate,
                last_time_for_task=services.last_time_for_task(db, user.id, body.task_type, task.id))


@router.post("/tasks/{task_id}/start")
def start_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task or task.operator_id != user.id:
        raise HTTPException(404, "Task not found")
    gate = services.check_safety_gate(db, task.vehicle_id)
    if not gate["ok"]:
        task.status = "blocked"
        if not gate["seatbelt_ok"] and not gate["sensor_fault"]:
            services.safety_incident(db, task, "seatbelt", f"Start attempted with seatbelt {gate['seatbelt_status']} on task #{task.id}")
        if not gate["proximity_ok"]:
            services.safety_incident(db, task, "proximity", f"Start attempted with hazard at {gate['proximity_m']} m on task #{task.id}")
        db.commit()
        raise HTTPException(409, dict(message="Safety gate not satisfied", gate=gate))
    task.status = "active"
    task.actual_start = datetime.utcnow()
    task.unresolved_alert_count = 0
    db.commit()
    snap = services.task_snapshot(db, task)
    hub.emit_sync("task_update", snap, services.channels_for(task))
    return snap


@router.post("/tasks/{task_id}/suspend")
def suspend_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task or (task.operator_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Task not found")
    task.status = "suspended"
    db.commit()
    snap = services.task_snapshot(db, task)
    hub.emit_sync("task_update", snap, services.channels_for(task))
    return snap


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: int, body: TaskActionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Planned-pause toggle: anomaly checks are suppressed while paused."""
    task = db.get(Task, task_id)
    if not task or task.operator_id != user.id:
        raise HTTPException(404, "Task not found")
    task.paused = bool(body.paused)
    db.commit()
    snap = services.task_snapshot(db, task)
    hub.emit_sync("task_update", snap, services.channels_for(task))
    return snap


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task or task.operator_id != user.id:
        raise HTTPException(404, "Task not found")
    services.complete_task(db, task)
    db.commit()
    return services.task_snapshot(db, task)


@router.post("/tasks/{task_id}/anomaly-check")
def manual_anomaly_check(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task or task.status != "active":
        raise HTTPException(404, "Active task not found")
    res = services.run_anomaly_check(db, task)
    db.commit()
    return res


@router.get("/tasks/current")
def current_task(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.scalar(select(Task).where(Task.operator_id == user.id, Task.status.in_(["pending", "blocked", "suspended", "active"]))
                     .order_by(Task.id.desc()))
    return services.task_snapshot(db, task) if task else None


@router.get("/tasks")
def list_tasks(status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Task).order_by(Task.id.desc())
    if user.role != "admin":
        q = q.where(Task.operator_id == user.id)
    if status:
        q = q.where(Task.status == status)
    return [services.task_snapshot(db, t) for t in db.scalars(q.limit(50))]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task or (task.operator_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Task not found")
    return services.task_snapshot(db, task)


# ---- alerts / incidents -------------------------------------------------------------------

@router.get("/alerts")
def list_alerts(task_id: int | None = None, unresolved: bool = False, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    q = select(Alert).order_by(Alert.id.desc())
    if user.role != "admin":
        my_tasks = select(Task.id).where(Task.operator_id == user.id)
        q = q.where(Alert.task_id.in_(my_tasks), Alert.target == "operator")
    if task_id is not None:
        q = q.where(Alert.task_id == task_id)
    if unresolved:
        q = q.where(Alert.resolved.is_(False))
    return [services._alert_dict(a) for a in db.scalars(q.limit(100))]


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    if not a.resolved:
        a.resolved = True
        task = db.get(Task, a.task_id) if a.task_id else None
        if task and task.unresolved_alert_count > 0 and a.target == "operator":
            task.unresolved_alert_count -= 1
    db.commit()
    hub.emit_sync("alert", services._alert_dict(a), ["admin", f"operator:{user.id}"])
    return services._alert_dict(a)


@router.get("/incidents")
def list_incidents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Incident).order_by(Incident.id.desc())
    if user.role != "admin":
        q = q.where(Incident.task_id.in_(select(Task.id).where(Task.operator_id == user.id)))
    return [services._incident_dict(i) for i in db.scalars(q.limit(100))]


@router.get("/training-modules")
def training_modules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [services._module_dict(m) for m in db.scalars(select(TrainingModule))]


@router.get("/admin/overview")
def admin_overview(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    active = [services.task_snapshot(db, t) for t in db.scalars(select(Task).where(Task.status.in_(["active", "blocked", "suspended", "pending"])).order_by(Task.id.desc()))]
    alerts = [services._alert_dict(a) for a in db.scalars(select(Alert).order_by(Alert.id.desc()).limit(50))]
    incidents = [services._incident_dict(i) for i in db.scalars(select(Incident).order_by(Incident.id.desc()).limit(50))]
    vehicles = [_vehicle(v) for v in db.scalars(select(Vehicle))]
    users = [_user(u) for u in db.scalars(select(User))]
    devices = {vid: dict(seatbelt_status=s["seatbelt_status"], proximity_m=s["proximity_m"]) for vid, s in services.DEVICE_STATE.items()}
    return dict(tasks=active, alerts=alerts, incidents=incidents, vehicles=vehicles, users=users, devices=devices)
