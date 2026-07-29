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
def booking_context() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-book-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Booking Doctor",
            slug=slug,
            email=f"book-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"book-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Book Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
            "consultation_fee": "500.00",
        },
    ).json()["data"]["id"]

    # A rule generates slots; pick one to book against.
    client.post(
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
    )
    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    yield {"slug": slug, "clinic_id": clinic_id, "slots": slots}

    with SessionLocal() as db:
        for model in (Appointment, Patient, Slot, AvailabilityRule, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _booking_body(context: dict, slot_id: str, phone: str = "+91-8000000001") -> dict:
    return {
        "doctor_slug": context["slug"],
        "slot_id": slot_id,
        "name": "Test Patient",
        "phone_number": phone,
        "email": "patient@example.com",
        "age": 30,
        "gender": "MALE",
        "reason": "Checkup",
    }


def test_public_doctor_and_slots(booking_context: dict) -> None:
    profile = client.get(f"/api/v1/doctors/public/{booking_context['slug']}")
    assert profile.status_code == 200
    assert len(profile.json()["data"]["clinics"]) == 1

    slot = booking_context["slots"][0]
    public_slots = client.get(
        f"/api/v1/public/slots?doctor_slug={booking_context['slug']}"
        f"&clinic_id={booking_context['clinic_id']}&slot_date={slot['slot_date']}"
    )
    assert public_slots.status_code == 200
    assert any(s["id"] == slot["id"] for s in public_slots.json()["data"])


def test_successful_booking(booking_context: dict) -> None:
    slot = booking_context["slots"][0]
    response = client.post(
        "/api/v1/public/bookings", json=_booking_body(booking_context, slot["id"])
    )
    assert response.status_code == 201
    # Free booking (no advance payment) is confirmed immediately.
    body = response.json()["data"]
    assert body["status"] == "confirmed"
    data = body["appointment"]
    assert data["appointment_number"].startswith("APT-")
    assert data["token_number"] == 1
    assert data["appointment_status"] == "CONFIRMED"
    assert data["consultation_fee"] == "500.00"


def test_capacity_blocks_when_full(booking_context: dict) -> None:
    slot = booking_context["slots"][0]
    # Capacity is 2 — two different patients succeed, the third is rejected.
    for phone in ("+91-8000000010", "+91-8000000011"):
        assert (
            client.post(
                "/api/v1/public/bookings", json=_booking_body(booking_context, slot["id"], phone)
            ).status_code
            == 201
        )

    third = client.post(
        "/api/v1/public/bookings",
        json=_booking_body(booking_context, slot["id"], "+91-8000000012"),
    )
    assert third.status_code == 409
    assert third.json()["error_code"] == "SLOT_FULL"


def test_duplicate_same_patient_rejected(booking_context: dict) -> None:
    slot = booking_context["slots"][1]
    body = _booking_body(booking_context, slot["id"], "+91-8000000020")
    assert client.post("/api/v1/public/bookings", json=body).status_code == 201

    # Same phone → same patient; capacity 2 leaves a seat, but they can't double-book.
    duplicate = client.post("/api/v1/public/bookings", json=body)
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "DUPLICATE_BOOKING"


def test_website_booking_sends_confirmation(booking_context: dict, monkeypatch) -> None:
    """A free website booking must notify the patient, exactly as an agent booking does.

    This path created the appointment and returned silently until 2026-07-28, so
    only voice-agent bookings ever produced a WhatsApp confirmation.
    """
    sent: list = []

    class _Recorder:
        name = "recorder"

        def send(self, to_phone, message, *, channel="whatsapp"):
            sent.append((to_phone, message))

    monkeypatch.setattr("app.services.booking_service.get_notifier", lambda: _Recorder())

    slot = booking_context["slots"][2]
    body = _booking_body(booking_context, slot["id"], "+91-8000000030")
    response = client.post("/api/v1/public/bookings", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "confirmed"

    assert len(sent) == 1, "expected exactly one confirmation"
    to_phone, message = sent[0]
    # Stored normalised (bare local); the notifier re-adds the country code.
    assert to_phone == "8000000030"
    assert message.template == "appointment_confirmed"
    # Six positional values, in the order the approved template expects.
    assert len(message.variables) == 6
    assert message.variables[0] == "Booking Doctor"
    assert message.variables[1] == "Book Clinic"
    assert message.variables[5] == response.json()["data"]["appointment"]["appointment_number"]
