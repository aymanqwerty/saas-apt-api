import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def headers() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Dash Doctor",
            slug=f"dr-dash-{unique}",
            email=f"dash-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"dash-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    auth = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/v1/clinics",
        headers=auth,
        json={
            "clinic_name": "Dash Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
        },
    )

    yield auth

    with SessionLocal() as db:
        db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_id).delete()
        db.query(Clinic).filter(Clinic.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_dashboard_summary(headers: dict) -> None:
    data = client.get("/api/v1/dashboard", headers=headers).json()["data"]
    assert data["total_clinics"] == 1
    assert data["total_patients"] == 0
    assert data["today_count"] == 0
    assert data["today_appointments"] == []
    # LOGIN + CREATE_CLINIC were recorded.
    actions = [entry["action"] for entry in data["recent_activity"]]
    assert "CREATE_CLINIC" in actions
