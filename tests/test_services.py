import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.doctor import Doctor
from app.models.service import Service
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def doctor_token() -> Generator[tuple[Doctor, str], None, None]:
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        record = Doctor(
            full_name="Service Test Doctor",
            slug=f"dr-service-{unique}",
            email=f"service-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    login = client.post("/api/v1/auth/login", json={"email": record.email, "password": PASSWORD})
    token = login.json()["data"]["token"]

    yield record, token

    with SessionLocal() as db:
        db.query(ActivityLog).filter(ActivityLog.doctor_id == record.id).delete()
        db.query(Service).filter(Service.doctor_id == record.id).delete()
        db.delete(db.get(Doctor, record.id))
        db.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_service_crud_flow(doctor_token: tuple[Doctor, str]) -> None:
    _, token = doctor_token

    created = client.post(
        "/api/v1/services",
        headers=_auth(token),
        json={"title": "Root Canal Treatment", "description": "Painless RCT", "sort_order": 1},
    )
    assert created.status_code == 201
    service_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/services", headers=_auth(token))
    assert len(listed.json()["data"]) == 1

    updated = client.patch(
        f"/api/v1/services/{service_id}",
        headers=_auth(token),
        json={"status": "INACTIVE"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "INACTIVE"

    deleted = client.delete(f"/api/v1/services/{service_id}", headers=_auth(token))
    assert deleted.status_code == 200

    after_delete = client.get("/api/v1/services", headers=_auth(token))
    assert after_delete.json()["data"] == []


def test_service_title_required(doctor_token: tuple[Doctor, str]) -> None:
    _, token = doctor_token

    response = client.post("/api/v1/services", headers=_auth(token), json={"title": ""})
    assert response.status_code == 422
