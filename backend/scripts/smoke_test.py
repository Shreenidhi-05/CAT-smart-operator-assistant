"""API smoke test covering the three demo scenarios (run against a live server)."""
import os
import sys
import time

import httpx

BASE = os.getenv("API", "http://localhost:8000/api")


def login(user, pw, vehicle_id=None):
    r = httpx.post(f"{BASE}/auth/login", json=dict(username=user, password=pw, vehicle_id=vehicle_id))
    r.raise_for_status()
    j = r.json()
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {j['access_token']}"}, timeout=20), j


def main():
    # 1. wrong vehicle
    _, j = login("leo", "operator123", vehicle_id=1)
    assert not j["vehicle_check"]["ok"], j
    print("wrong-vehicle block OK:", j["vehicle_check"]["message"])

    # 2. seatbelt block
    c, _ = login("leo", "operator123", vehicle_id=3)
    c.post("/device/state", json=dict(vehicle_id=3, seatbelt_status="unfastened"))
    r = c.post("/tasks/prepare", json=dict(vehicle_id=3, zone="Zone A - Pit", task_type="Loading")).json()
    tid = r["task"]["id"]
    print("prediction:", r["prediction"], "gate:", r["safety_gate"]["ok"])
    assert c.post(f"/tasks/{tid}/start").status_code == 409
    gate = c.get("/safety-gate", params=dict(vehicle_id=3)).json()
    assert gate["training_module"] is not None
    print("seatbelt block OK -> video:", gate["training_module"]["title"])
    c.post("/device/state", json=dict(vehicle_id=3, seatbelt_status="fastened"))

    # 3. risk suspension
    c, _ = login("maya", "operator123", vehicle_id=1)
    r = c.post("/tasks/prepare", json=dict(vehicle_id=1, zone="Zone C - Ridge", task_type="Excavation",
                                          ground_condition="muddy", ground_moisture=0.82)).json()
    assert r["risk"]["risky"] and r["task"]["status"] == "suspended"
    print("risk suspension OK:", r["risk"]["reasons"])

    # 4. escalation via forced anomaly checks
    c, _ = login("raj", "operator123", vehicle_id=2)
    r = c.post("/tasks/prepare", json=dict(vehicle_id=2, zone="Zone B - Haul Road", task_type="Hauling",
                                          demo_scenario="escalation")).json()
    tid = r["task"]["id"]
    assert c.post(f"/tasks/{tid}/start").status_code == 200
    a, _ = login("admin", "admin123")
    print("waiting for telemetry...")
    time.sleep(35)
    for i in range(3):
        res = c.post(f"/tasks/{tid}/anomaly-check").json()
        print(f"check {i+1}: anomaly={res['anomaly']} baseline={res['baseline']} rows={res['window_rows']}")
        print("   ", res["explanation"][:160])
    ov = a.get("/admin/overview").json()
    esc = [x for x in ov["alerts"] if x["type"] == "escalation" and x["task_id"] == tid]
    inc = [x for x in ov["incidents"] if x["type"] == "escalation" and x["task_id"] == tid]
    assert esc and inc, "escalation not created"
    print("escalation OK:", esc[0]["message"])
    done = c.post(f"/tasks/{tid}/complete").json()
    print("completed, total idle:", done["total_idle_min"])


if __name__ == "__main__":
    main()
    print("ALL OK")
