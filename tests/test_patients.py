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
    slug = f"dr-pat-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Patient Doctor",
            slug=slug,
            email=f"pat-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"pat-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={"clinic_name": "Pat Clinic", "address_line_1": "1 St", "city": "Pune", "state": "MH"},
    ).json()["data"]["id"]
    client.post(
        "/api/v1/availability",
        headers=headers,
        json={
            "clinic_id": clinic_id,
            "weekday": "MONDAY",
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 1,
            "effective_from": "2026-01-01",
        },
    )
    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    # Same patient (same phone) books two different slots → one patient, 2 appointments.
    for slot in slots[:2]:
        client.post(
            "/api/v1/public/bookings",
            json={
                "doctor_slug": slug,
                "slot_id": slot["id"],
                "name": "Ravi Kumar",
                "phone_number": "+91-8000000077",
            },
        )

    yield {"headers": headers}

    with SessionLocal() as db:
        for model in (Appointment, Patient, Slot, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_list_patients_with_stats(context: dict) -> None:
    listing = client.get("/api/v1/patients", headers=context["headers"]).json()["data"]
    assert listing["meta"]["total"] == 1
    patient = listing["items"][0]
    assert patient["full_name"] == "Ravi Kumar"
    assert patient["total_appointments"] == 2
    assert patient["last_visit"] is not None


def test_search_and_detail_and_history(context: dict) -> None:
    found = client.get("/api/v1/patients?search=Ravi", headers=context["headers"]).json()["data"]
    assert len(found["items"]) == 1
    patient_id = found["items"][0]["id"]

    detail = client.get(f"/api/v1/patients/{patient_id}", headers=context["headers"]).json()["data"]
    assert detail["total_appointments"] == 2

    history = client.get(
        f"/api/v1/patients/{patient_id}/appointments", headers=context["headers"]
    ).json()["data"]
    assert len(history) == 2

    missing = client.get("/api/v1/patients?search=Nobody", headers=context["headers"]).json()[
        "data"
    ]
    assert missing["items"] == []
