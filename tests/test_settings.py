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
from app.models.doctor_settings import DoctorSettings
from app.models.gallery_post import GalleryPost
from app.models.patient import Patient
from app.models.slot import Slot
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def context() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-set-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Settings Doctor",
            slug=slug,
            email=f"set-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"set-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Set Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
            "phone_number": "+91-1112223334",
            "consultation_fee": "500.00",
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
    yield {"slug": slug, "headers": headers, "clinic_id": clinic_id, "slots": slots}

    with SessionLocal() as db:
        for model in (
            Appointment,
            Patient,
            Slot,
            AvailabilityRule,
            GalleryPost,
            ActivityLog,
            Clinic,
            DoctorSettings,
        ):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_get_and_update_settings(context: dict) -> None:
    got = client.get("/api/v1/settings", headers=context["headers"]).json()["data"]
    assert got["booking_enabled"] is True

    updated = client.patch(
        "/api/v1/settings",
        headers=context["headers"],
        json={"booking_enabled": False, "show_consultation_fee": False},
    ).json()["data"]
    assert updated["booking_enabled"] is False
    assert updated["show_consultation_fee"] is False


def test_booking_disabled_blocks_public_booking(context: dict) -> None:
    client.patch("/api/v1/settings", headers=context["headers"], json={"booking_enabled": False})
    response = client.post(
        "/api/v1/public/bookings",
        json={
            "doctor_slug": context["slug"],
            "slot_id": context["slots"][0]["id"],
            "name": "Test",
            "phone_number": "+91-8000000090",
        },
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "BOOKING_DISABLED"


def test_fee_and_contact_hidden_on_public_site(context: dict) -> None:
    client.patch(
        "/api/v1/settings",
        headers=context["headers"],
        json={"show_consultation_fee": False, "show_contact_information": False},
    )
    site = client.get(f"/api/v1/doctors/public/{context['slug']}/site").json()["data"]
    clinic = site["clinics"][0]
    assert clinic["consultation_fee"] is None
    assert clinic["phone_number"] is None


def test_gallery_disabled_hides_public_gallery(context: dict) -> None:
    client.post(
        "/api/v1/gallery",
        headers=context["headers"],
        json={"title": "Case", "description": "d", "status": "PUBLISHED"},
    )
    client.patch("/api/v1/settings", headers=context["headers"], json={"gallery_enabled": False})
    assert client.get(f"/api/v1/doctors/public/{context['slug']}/gallery").status_code == 404
    site = client.get(f"/api/v1/doctors/public/{context['slug']}/site").json()["data"]
    assert site["gallery"] == []
