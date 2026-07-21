import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.availability_rule import AvailabilityRule
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.slot import Slot
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def context() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Bulk Doctor",
            slug=f"dr-bulk-{unique}",
            email=f"bulk-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"bulk-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Bulk Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
        },
    ).json()["data"]["id"]

    yield {"headers": headers, "clinic_id": clinic_id}

    with SessionLocal() as db:
        for model in (Slot, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _payload(context: dict, weekdays: list[str]) -> dict:
    return {
        "clinic_id": context["clinic_id"],
        "weekdays": weekdays,
        "start_time": "09:00:00",
        "end_time": "12:00:00",
        "slot_duration_minutes": 30,
        "patients_per_slot": 1,
        "effective_from": "2026-01-01",
    }


def test_bulk_creates_one_rule_per_day(context: dict) -> None:
    response = client.post(
        "/api/v1/availability/bulk",
        headers=context["headers"],
        json=_payload(context, ["MONDAY", "TUESDAY", "WEDNESDAY"]),
    )
    assert response.status_code == 201
    created = response.json()["data"]
    assert len(created) == 3
    assert {r["weekday"] for r in created} == {"MONDAY", "TUESDAY", "WEDNESDAY"}

    rules = client.get("/api/v1/availability", headers=context["headers"]).json()["data"]
    assert len(rules) == 3


def test_bulk_is_atomic_on_overlap(context: dict) -> None:
    # Pre-existing Tuesday rule.
    client.post(
        "/api/v1/availability",
        headers=context["headers"],
        json={
            **_payload(context, []),
            "weekday": "TUESDAY",
        },
    )

    # Mon/Tue/Wed batch conflicts on Tuesday → whole batch rejected, nothing added.
    response = client.post(
        "/api/v1/availability/bulk",
        headers=context["headers"],
        json=_payload(context, ["MONDAY", "TUESDAY", "WEDNESDAY"]),
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "OVERLAPPING_RULE"

    rules = client.get("/api/v1/availability", headers=context["headers"]).json()["data"]
    # Only the original Tuesday rule exists.
    assert len(rules) == 1
