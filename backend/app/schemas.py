from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str
    vehicle_id: int | None = None  # supplied by the operator device from its own config


class ReassignIn(BaseModel):
    operator_id: int
    vehicle_id: int
    temporary: bool = True


class DeviceStateIn(BaseModel):
    vehicle_id: int
    seatbelt_status: str | None = None
    proximity_m: float | None = None


class PrepareTaskIn(BaseModel):
    vehicle_id: int
    zone: str
    task_type: str
    ground_condition: str = "dry"
    ground_moisture: float = 0.2
    obstacle_distance_m: float = 10.0
    demo_scenario: str | None = None


class TaskActionIn(BaseModel):
    paused: bool | None = None
