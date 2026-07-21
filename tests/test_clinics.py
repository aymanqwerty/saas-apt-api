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

CLINIC_PAYLOAD = {
    "clinic_name": "City Care Clinic",
    "address_line_1": "12 MG Road",
    "city": "Pune",
    "state": "Maharashtra",
    "consultation_fee": "500.00",
}


def _create_doctor(db, tag: str) -> Doctor:
    unique = uuid.uuid4().hex[:10]
    doctor = Doctor(
        full_name=f"Clinic Test Doctor {tag}",
        slug=f"dr-clinic-{tag}-{unique}",
        email=f"clinic-{tag}-{unique}@example.com",
        password_hash=hash_password(PASSWORD),
        phone_number="+91-9999999999",
        specialization="Testing",
    )
    db.add(doctor)
    return doctor


@pytest.fixture
def two_doctors() -> Generator[tuple[dict, dict], None, None]:
    with SessionLocal() as db:
        doctor_a = _create_doctor(db, "a")
        doctor_b = _create_doctor(db, "b")
        db.commit()
        db.refresh(doctor_a)
        db.refresh(doctor_b)

    def login(email: str) -> str:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        return response.json()["data"]["token"]

    yield (
        {"id": doctor_a.id, "token": login(doctor_a.email)},
        {"id": doctor_b.id, "token": login(doctor_b.email)},
    )

    with SessionLocal() as db:
        for doctor_id in (doctor_a.id, doctor_b.id):
            db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_id).delete()
            db.query(Clinic).filter(Clinic.doctor_id == doctor_id).delete()
            db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_clinic_crud_flow(two_doctors: tuple[dict, dict]) -> None:
    doctor_a, _ = two_doctors

    created = client.post("/api/v1/clinics", headers=_auth(doctor_a["token"]), json=CLINIC_PAYLOAD)
    assert created.status_code == 201
    clinic_id = created.json()["data"]["id"]
    assert created.json()["data"]["timezone"] == "Asia/Kolkata"

    listed = client.get("/api/v1/clinics", headers=_auth(doctor_a["token"]))
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    updated = client.patch(
        f"/api/v1/clinics/{clinic_id}",
        headers=_auth(doctor_a["token"]),
        json={"status": "INACTIVE", "consultation_fee": "750.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "INACTIVE"

    deleted = client.delete(f"/api/v1/clinics/{clinic_id}", headers=_auth(doctor_a["token"]))
    assert deleted.status_code == 200

    after_delete = client.get("/api/v1/clinics", headers=_auth(doctor_a["token"]))
    assert after_delete.json()["data"] == []


def test_clinic_tenant_isolation(two_doctors: tuple[dict, dict]) -> None:
    doctor_a, doctor_b = two_doctors

    created = client.post("/api/v1/clinics", headers=_auth(doctor_a["token"]), json=CLINIC_PAYLOAD)
    clinic_id = created.json()["data"]["id"]

    forbidden_read = client.get(f"/api/v1/clinics/{clinic_id}", headers=_auth(doctor_b["token"]))
    assert forbidden_read.status_code == 404

    forbidden_update = client.patch(
        f"/api/v1/clinics/{clinic_id}",
        headers=_auth(doctor_b["token"]),
        json={"clinic_name": "Hijacked"},
    )
    assert forbidden_update.status_code == 404

    listed_by_b = client.get("/api/v1/clinics", headers=_auth(doctor_b["token"]))
    assert listed_by_b.json()["data"] == []


def test_clinic_invalid_timezone_rejected(two_doctors: tuple[dict, dict]) -> None:
    doctor_a, _ = two_doctors

    response = client.post(
        "/api/v1/clinics",
        headers=_auth(doctor_a["token"]),
        json={**CLINIC_PAYLOAD, "timezone": "Not/AZone"},
    )
    assert response.status_code == 422


def test_clinic_create_records_activity(two_doctors: tuple[dict, dict]) -> None:
    doctor_a, _ = two_doctors

    client.post("/api/v1/clinics", headers=_auth(doctor_a["token"]), json=CLINIC_PAYLOAD)

    with SessionLocal() as db:
        actions = [
            log.action
            for log in db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_a["id"]).all()
        ]
    assert "CREATE_CLINIC" in actions
    assert "LOGIN" in actions
