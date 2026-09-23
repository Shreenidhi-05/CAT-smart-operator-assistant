import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import config, services
from .auth import decode_token
from .db import Base, SessionLocal, engine
from .ml import anomaly, predict
from .models import Task, Vehicle
from .routers import router
from .seed import seed
from .ws import hub

log = logging.getLogger("cat")


async def telemetry_loop():
    """Simulated vehicle telemetry: writes sensor_logs for active tasks and runs periodic anomaly checks."""
    last_check: dict[int, datetime] = {}
    while True:
        try:
            with SessionLocal() as db:
                for task in db.scalars(select(Task).where(Task.status == "active")).all():
                    vehicle = db.get(Vehicle, task.vehicle_id)
                    progress = (datetime.utcnow() - task.actual_start).total_seconds() / 60 / (task.predicted_time_min or 60)
                    services.record_sensor_log(db, task, vehicle, progress)
                    db.commit()
                    hub.emit_sync("task_update", services.task_snapshot(db, task), services.channels_for(task))
                    due = (datetime.utcnow() - last_check.get(task.id, task.actual_start)).total_seconds() >= config.ANOMALY_INTERVAL_S
                    if due and not task.paused:
                        services.run_anomaly_check(db, task)
                        db.commit()
                        last_check[task.id] = datetime.utcnow()
                    elif task.paused:
                        last_check[task.id] = datetime.utcnow()
        except Exception:  # keep the loop alive
            log.exception("telemetry loop error")
        await asyncio.sleep(config.SENSOR_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    predict.load()
    anomaly.load()
    hub.loop = asyncio.get_running_loop()
    task = asyncio.create_task(telemetry_loop())
    yield
    task.cancel()


app = FastAPI(title="CAT Smart Operator Assistant", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/health")
def health():
    return dict(ok=True, models=dict(task_time=predict.load() is not None, isolation_forest=anomaly.load()[0] is not None))


@app.websocket("/ws")
async def websocket(ws: WebSocket, token: str):
    try:
        payload = decode_token(token)
    except Exception:
        await ws.close(code=4401)
        return
    channel = "admin" if payload["role"] == "admin" else f"operator:{payload['sub']}"
    await hub.connect(channel, ws)
    try:
        while True:
            await ws.receive_text()  # keepalive pings from client
    except WebSocketDisconnect:
        hub.disconnect(channel, ws)
