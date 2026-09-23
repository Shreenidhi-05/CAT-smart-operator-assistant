from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String)  # admin | operator
    password_hash: Mapped[str] = mapped_column(String)
    skill_level: Mapped[int] = mapped_column(Integer, default=2)  # 1..3


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    machine_type: Mapped[str] = mapped_column(String)
    current_operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class VehicleAssignment(Base):
    __tablename__ = "vehicle_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    temporary: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    zone: Mapped[str] = mapped_column(String)
    task_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|blocked|suspended|active|completed
    predicted_time_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_range_min: Mapped[str | None] = mapped_column(String, nullable=True)  # "lo-hi"
    actual_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_idle_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    unresolved_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    # Task parameter snapshot
    weather_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ground_condition: Mapped[str | None] = mapped_column(String, nullable=True)
    ground_moisture: Mapped[float | None] = mapped_column(Float, nullable=True)
    obstacle_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    demo_scenario: Mapped[str | None] = mapped_column(String, nullable=True)

    sensor_logs = relationship("SensorLog", back_populates="task")


class SensorLog(Base):
    __tablename__ = "sensor_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    engine_hours: Mapped[float] = mapped_column(Float, default=0)
    fuel_used: Mapped[float] = mapped_column(Float, default=0)
    load_cycles: Mapped[int] = mapped_column(Integer, default=0)
    idling_min: Mapped[float] = mapped_column(Float, default=0)
    seatbelt_status: Mapped[str] = mapped_column(String, default="fastened")  # fastened|unfastened|fault
    zone: Mapped[str | None] = mapped_column(String, nullable=True)
    proximity_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_alert_triggered: Mapped[bool] = mapped_column(Boolean, default=False)

    task = relationship("Task", back_populates="sensor_logs")


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    type: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    details: Mapped[str] = mapped_column(Text, default="")
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    type: Mapped[str] = mapped_column(String)  # seatbelt|proximity|anomaly|escalation|risk|sensor_fault|wrong_vehicle
    severity: Mapped[str] = mapped_column(String, default="warning")
    message: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    target: Mapped[str] = mapped_column(String, default="operator")  # operator|admin


class TrainingModule(Base):
    __tablename__ = "training_modules"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String)
    trigger_behavior: Mapped[str] = mapped_column(String)  # seatbelt|proximity|idling|...
    video_url: Mapped[str] = mapped_column(String)
