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
    slug = f"dr-avail-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Avail Doctor",
            slug=slug,
            email=f"avail-{unique}@example.com",
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
        json={"email": f"avail-{unique}@example.com", "password": PASSWORD},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Avail Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
        },
    ).json()["data"]["id"]
    client.post(
        "/api/v1/availability",
        headers=headers,
        json={
            "clinic_id": clinic_id,
            "weekday": "MONDAY",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 1,
            "effective_from": "2026-01-01",
        },
    )
    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    yield {"headers": headers, "slug": slug, "clinic_id": clinic_id, "slots": slots}

    with SessionLocal() as db:
        for model in (Appointment, Patient, Slot, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_available_dates_excludes_fully_booked(context: dict) -> None:
    slug = context["slug"]
    clinic_id = context["clinic_id"]
    all_slots = context["slots"]
    target_date = all_slots[0]["slot_date"]

    url = (
        f"/api/v1/public/availability-dates?doctor_slug={slug}"
        f"&clinic_id={clinic_id}&date_from=2026-01-01&date_to=2027-01-01"
    )
    before = client.get(url).json()["data"]
    assert target_date in before

    # Book every slot on the target date (capacity 1 each) → date becomes full.
    same_day = [s for s in all_slots if s["slot_date"] == target_date]
    for index, slot in enumerate(same_day):
        resp = client.post(
            "/api/v1/public/bookings",
            json={
                "doctor_slug": slug,
                "slot_id": slot["id"],
                "name": "Filler",
                "phone_number": f"+91-70000000{index:02d}",
            },
        )
        assert resp.status_code == 201

    after = client.get(url).json()["data"]
    assert target_date not in after
    # Other future Mondays are still available.
    assert len(after) >= 1
