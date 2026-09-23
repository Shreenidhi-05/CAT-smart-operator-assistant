import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'cat.db'}")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "480"))

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
DEFAULT_LAT = float(os.getenv("SITE_LAT", "41.88"))
DEFAULT_LON = float(os.getenv("SITE_LON", "-87.63"))

# Risk thresholds (task suspension is suggested if any is exceeded)
RISK_THRESHOLDS = {
    "wind_kmh_max": float(os.getenv("RISK_WIND_KMH_MAX", "40")),
    "visibility_m_min": float(os.getenv("RISK_VISIBILITY_M_MIN", "50")),
    "ground_moisture_max": float(os.getenv("RISK_GROUND_MOISTURE_MAX", "0.7")),  # 0..1
    "obstacle_distance_m_min": float(os.getenv("RISK_OBSTACLE_M_MIN", "3")),
}

# Safety / monitoring
PROXIMITY_HAZARD_M = float(os.getenv("PROXIMITY_HAZARD_M", "3"))
SEATBELT_FAULT_TIMEOUT_S = int(os.getenv("SEATBELT_FAULT_TIMEOUT_S", "60"))
ANOMALY_WINDOW_MIN = int(os.getenv("ANOMALY_WINDOW_MIN", "5"))
# Production cadence is 60-120s logs / 300s anomaly checks; defaults are shortened for live demos.
SENSOR_INTERVAL_S = int(os.getenv("SENSOR_INTERVAL_S", "10"))
ANOMALY_INTERVAL_S = int(os.getenv("ANOMALY_INTERVAL_S", "30"))
ANOMALY_Z_THRESHOLD = float(os.getenv("ANOMALY_Z_THRESHOLD", "2.5"))
UNRESOLVED_ALERT_ESCALATION = int(os.getenv("UNRESOLVED_ALERT_ESCALATION", "3"))
COLD_START_MIN_TASKS = int(os.getenv("COLD_START_MIN_TASKS", "5"))

# engine_hours is cumulative so it is excluded from anomaly metrics
SENSOR_METRICS = ["fuel_used", "load_cycles", "idling_min"]
