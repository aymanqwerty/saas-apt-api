import uuid
import datetime as _dt
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.appointment import Appointment
from app.models.availability_rule import AvailabilityRule
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.slot import Slot
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def context() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-retire-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Retire Doctor",
            slug=slug,
            email=f"retire-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login",
        json={"email": f"retire-{unique}@example.com", "password": PASSWORD},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Retire Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
        },
    ).json()["data"]["id"]
    rule = client.post(
        "/api/v1/availability",
        headers=headers,
        json={
            "clinic_id": clinic_id,
            "weekday": "MONDAY",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 2,
            "effective_from": "2026-01-01",
        },
    ).json()["data"]
    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    # Book one seat of the first slot (capacity 2 → partially booked).
    client.post(
        "/api/v1/public/bookings",
        json={
            "doctor_slug": slug,
            "slot_id": slots[0]["id"],
            "name": "Booked Patient",
            "phone_number": "+91-8000000200",
        },
    )

    yield {
        "headers": headers,
        "slug": slug,
        "clinic_id": clinic_id,
        "rule_id": rule["id"],
        "booked_slot_id": slots[0]["id"],
    }

    with SessionLocal() as db:
        for model in (Appointment, Patient, Slot, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_list_reports_upcoming_booked_count(context: dict) -> None:
    rules = client.get("/api/v1/availability", headers=context["headers"]).json()["data"]
    assert rules[0]["upcoming_booked_count"] == 1


def test_delete_blocks_booked_slot_and_removes_empty(context: dict) -> None:
    booked_slot_id = context["booked_slot_id"]

    before = client.get(
        f"/api/v1/slots?clinic_id={context['clinic_id']}", headers=context["headers"]
    ).json()["data"]["items"]
    assert len(before) > 1  # rule generated many slots

    resp = client.delete(f"/api/v1/availability/{context['rule_id']}", headers=context["headers"])
    assert resp.status_code == 200

    after = client.get(
        f"/api/v1/slots?clinic_id={context['clinic_id']}", headers=context["headers"]
    ).json()["data"]["items"]

    # Only the booked slot survives, now BLOCKED.
    assert len(after) == 1
    survivor = after[0]
    assert survivor["id"] == booked_slot_id
    assert survivor["status"] == "BLOCKED"

    # Existing appointment is preserved.
    appts = client.get("/api/v1/appointments", headers=context["headers"]).json()["data"]
    assert appts["meta"]["total"] == 1

    # No new booking can be taken on the retired slot.
    rebook = client.post(
        "/api/v1/public/bookings",
        json={
            "doctor_slug": context["slug"],
            "slot_id": booked_slot_id,
            "name": "Late Patient",
            "phone_number": "+91-8000000201",
        },
    )
    assert rebook.status_code == 409
    assert rebook.json()["error_code"] in ("SLOT_UNAVAILABLE", "SLOT_FULL")
