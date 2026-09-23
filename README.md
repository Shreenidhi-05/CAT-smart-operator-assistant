# CAT Command Center — Smart Operator Assistant (hackathon MVP)

Operator cockpit + supervisor dashboard for CAT machinery: JWT auth with vehicle verification, a pre-task
safety gate (seatbelt / proximity / weather risk check), LightGBM quantile task-time prediction, live
telemetry monitoring with z-score + Isolation Forest anomaly detection, auto-escalation and auto-incidents.

## Stack
FastAPI + SQLAlchemy (SQLite) · scikit-learn Isolation Forest · LightGBM quantile regression ·
native WebSockets · React + Vite + Tailwind v4 · Docker Compose · OpenWeatherMap (optional key).

## Run with Docker Compose
```bash
docker compose up --build
# operator terminal (device configured as vehicle #1):  http://localhost:5173
# admin dashboard (separate build):                      http://localhost:5174
# API docs:                                              http://localhost:8000/docs
```
Env knobs (see `docker-compose.yml`): `OPERATOR_VEHICLE_ID` (per-device vehicle id baked into the operator
build), `OPENWEATHER_API_KEY`, `SITE_LAT/SITE_LON`, `SENSOR_INTERVAL_S` (default 10s for demos; 60-120s in
production), `ANOMALY_INTERVAL_S` (default 30s; 300s in production), risk thresholds `RISK_*`.

Synthetic data is generated and both models are trained during the backend image build
(`scripts/generate_synthetic.py`, `scripts/train_models.py`); models are loaded at API startup and the DB is
seeded on first boot.

## Run locally (dev)
```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python scripts/generate_synthetic.py && python scripts/train_models.py
uvicorn app.main:app --reload --port 8000
# in another shell
cd frontend && npm install && npm run dev        # http://localhost:5173 (vite proxies /api and /ws)
```
In dev the login form lets you type the device vehicle id; in a real build it is fixed via `VITE_VEHICLE_ID`.

## Demo accounts
| user  | password    | role     | assigned vehicle | notes |
|-------|-------------|----------|------------------|-------|
| admin | admin123    | admin    | —                | |
| maya  | operator123 | operator | #1 Excavator     | veteran, personal baseline |
| raj   | operator123 | operator | #2 Dozer         | |
| leo   | operator123 | operator | #3 Wheel Loader  | 2 completed tasks → cold start (fleet baseline) |
| sam   | operator123 | operator | #4 Art. Truck    | |

## Live demo script (`backend/data/demo_scenarios.json`)
1. **Wrong vehicle** — log in as `leo` with vehicle id 1 → blocked, "correct vehicle is #3". Admin grants a
   temporary override from the dashboard → operator screen unblocks live.
2. **Seatbelt block → sensor fault** — cockpit panel: Unfasten, then *Prepare task* / *Start* → blocked, training
   video plays. After 60 s with no change the gate flips to *sensor fault* and the admin gets an alert + incident.
3. **Risk suspension** — pick demo scenario "Risk check" (Zone C - Ridge: 58 km/h wind, 40 m visibility, muddy) →
   suspension suggested, start disabled.
4. **3-alert escalation** — pick demo scenario "escalation" as `raj`, start. Telemetry drifts (high idle/fuel, low
   cycles); each anomaly check pushes an explained alert. Leave 3 unresolved → admin escalation + incident.
   "Log planned pause" suppresses checks; "Mark complete" stores actual_end and total idle time.

Smoke test the API flows against a running backend: `python backend/scripts/smoke_test.py`.
