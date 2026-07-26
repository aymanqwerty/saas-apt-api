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
    slug = f"dr-appt-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Appt Doctor",
            slug=slug,
            email=f"appt-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"appt-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Appt Clinic",
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
    book = client.post(
        "/api/v1/public/bookings",
        json={
            "doctor_slug": slug,
            "slot_id": slots[0]["id"],
            "name": "Jane Doe",
            "phone_number": "+91-8000000050",
        },
    ).json()["data"]["appointment"]

    yield {
        "headers": headers,
        "slug": slug,
        "clinic_id": clinic_id,
        "slots": slots,
        "appointment_id": book["id"],
    }

    with SessionLocal() as db:
        for model in (Appointment, Patient, Slot, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_list_and_get(context: dict) -> None:
    listing = client.get("/api/v1/appointments", headers=context["headers"]).json()["data"]
    assert listing["meta"]["total"] == 1
    assert listing["items"][0]["patient_name"] == "Jane Doe"

    detail = client.get(
        f"/api/v1/appointments/{context['appointment_id']}", headers=context["headers"]
    ).json()["data"]
    # Phone is canonicalised on booking (country code / punctuation stripped).
    assert detail["patient_phone"] == "8000000050"


def test_invalid_status_transition_rejected(context: dict) -> None:
    # Booking starts CONFIRMED; PENDING is not a valid target.
    response = client.patch(
        f"/api/v1/appointments/{context['appointment_id']}",
        headers=context["headers"],
        json={"status": "PENDING"},
    )
    assert response.status_code == 422


def test_cancel_releases_slot_capacity(context: dict) -> None:
    slot_id = context["slots"][0]["id"]
    before = client.get(
        f"/api/v1/slots?clinic_id={context['clinic_id']}", headers=context["headers"]
    ).json()["data"]["items"]
    booked_slot = next(s for s in before if s["id"] == slot_id)
    assert booked_slot["booked_count"] == 1

    cancel = client.patch(
        f"/api/v1/appointments/{context['appointment_id']}",
        headers=context["headers"],
        json={"status": "CANCELLED", "cancellation_reason": "Patient request"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["data"]["appointment_status"] == "CANCELLED"

    after = client.get(
        f"/api/v1/slots?clinic_id={context['clinic_id']}", headers=context["headers"]
    ).json()["data"]["items"]
    released = next(s for s in after if s["id"] == slot_id)
    assert released["booked_count"] == 0
    assert released["status"] == "AVAILABLE"


def test_reschedule_moves_capacity(context: dict) -> None:
    old_slot_id = context["slots"][0]["id"]
    new_slot_id = context["slots"][1]["id"]

    resched = client.patch(
        f"/api/v1/appointments/{context['appointment_id']}",
        headers=context["headers"],
        json={"reschedule_slot_id": new_slot_id},
    )
    assert resched.status_code == 200

    slots = client.get(
        f"/api/v1/slots?clinic_id={context['clinic_id']}", headers=context["headers"]
    ).json()["data"]["items"]
    old_slot = next(s for s in slots if s["id"] == old_slot_id)
    new_slot = next(s for s in slots if s["id"] == new_slot_id)
    assert old_slot["booked_count"] == 0
    assert new_slot["booked_count"] == 1


def test_completed_cannot_be_rescheduled(context: dict) -> None:
    client.patch(
        f"/api/v1/appointments/{context['appointment_id']}",
        headers=context["headers"],
        json={"status": "COMPLETED"},
    )
    resched = client.patch(
        f"/api/v1/appointments/{context['appointment_id']}",
        headers=context["headers"],
        json={"reschedule_slot_id": context["slots"][1]["id"]},
    )
    assert resched.status_code == 422
