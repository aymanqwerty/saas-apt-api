import uuid
import datetime as _dt
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.availability_exception import AvailabilityException
from app.models.availability_rule import AvailabilityRule
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.slot import Slot
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def doctor_clinic() -> Generator[tuple[str, str], None, None]:
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Sched Doctor",
            slug=f"dr-sched-{unique}",
            email=f"sched-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"sched-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Sched Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
        },
    ).json()["data"]["id"]

    yield token, clinic_id

    with SessionLocal() as db:
        for model in (Slot, AvailabilityException, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_rule_generates_slots(doctor_clinic: tuple[str, str]) -> None:
    token, clinic_id = doctor_clinic

    created = client.post(
        "/api/v1/availability",
        headers=_auth(token),
        json={
            "clinic_id": clinic_id,
            "weekday": "MONDAY",
            "start_time": "09:00:00",
            "end_time": "12:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 2,
            "effective_from": "2026-01-01",
        },
    )
    assert created.status_code == 201

    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=_auth(token)).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    assert len(slots) > 0
    # 09:00-12:00 at 30 min = 6 slots per Monday; every slot must be a Monday.
    assert all(s["capacity"] == 2 for s in slots)
    assert all(s["start_time"] >= "09:00:00" and s["end_time"] <= "12:00:00" for s in slots)


def test_overlapping_rule_rejected(doctor_clinic: tuple[str, str]) -> None:
    token, clinic_id = doctor_clinic
    payload = {
        "clinic_id": clinic_id,
        "weekday": "TUESDAY",
        "start_time": "09:00:00",
        "end_time": "12:00:00",
        "slot_duration_minutes": 30,
        "patients_per_slot": 1,
        "effective_from": "2026-01-01",
    }
    assert (
        client.post("/api/v1/availability", headers=_auth(token), json=payload).status_code == 201
    )

    overlap = client.post(
        "/api/v1/availability",
        headers=_auth(token),
        json={**payload, "start_time": "11:00:00", "end_time": "13:00:00"},
    )
    assert overlap.status_code == 409
    assert overlap.json()["error_code"] == "OVERLAPPING_RULE"


def test_blocking_exception_removes_slots(doctor_clinic: tuple[str, str]) -> None:
    token, clinic_id = doctor_clinic
    client.post(
        "/api/v1/availability",
        headers=_auth(token),
        json={
            "clinic_id": clinic_id,
            "weekday": "WEDNESDAY",
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 1,
            "effective_from": "2026-01-01",
        },
    )

    # Find a future Wednesday that has generated slots.
    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=_auth(token)).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    assert slots
    target_date = slots[0]["slot_date"]

    exc = client.post(
        "/api/v1/availability/exceptions",
        headers=_auth(token),
        json={
            "clinic_id": clinic_id,
            "exception_date": target_date,
            "exception_type": "HOLIDAY",
            "is_available": False,
            "reason": "Holiday",
        },
    )
    assert exc.status_code == 201

    remaining = client.get(
        f"/api/v1/slots?clinic_id={clinic_id}&slot_date={target_date}", headers=_auth(token)
    ).json()["data"]["items"]
    assert remaining == []


def test_slot_block_and_capacity(doctor_clinic: tuple[str, str]) -> None:
    token, clinic_id = doctor_clinic
    client.post(
        "/api/v1/availability",
        headers=_auth(token),
        json={
            "clinic_id": clinic_id,
            "weekday": "FRIDAY",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 3,
            "effective_from": "2026-01-01",
        },
    )
    slot_id = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=_auth(token)).json()[
        "data"
    ]["items"][0]["id"]

    blocked = client.patch(
        f"/api/v1/slots/{slot_id}",
        headers=_auth(token),
        json={"is_blocked": True, "block_reason": "Personal"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["data"]["status"] == "BLOCKED"

    capped = client.patch(f"/api/v1/slots/{slot_id}", headers=_auth(token), json={"capacity": 5})
    assert capped.json()["data"]["capacity"] == 5
