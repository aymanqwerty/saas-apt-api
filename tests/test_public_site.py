import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.service import Service
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def context() -> Generator[str, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-site-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Site Doctor",
            slug=slug,
            email=f"site-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Cardiology",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"site-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Site Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
        },
    )
    client.post(
        "/api/v1/services",
        headers=headers,
        json={"title": "Angioplasty", "status": "ACTIVE"},
    )
    client.post(
        "/api/v1/services",
        headers=headers,
        json={"title": "Hidden Service", "status": "INACTIVE"},
    )

    yield slug

    with SessionLocal() as db:
        for model in (Service, ActivityLog, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_public_site_aggregate(context: str) -> None:
    response = client.get(f"/api/v1/doctors/public/{context}/site")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["doctor"]["specialization"] == "Cardiology"
    assert len(data["clinics"]) == 1
    # Only the ACTIVE service is public.
    assert len(data["services"]) == 1
    assert data["services"][0]["title"] == "Angioplasty"


def test_public_site_unknown_slug_404() -> None:
    assert client.get("/api/v1/doctors/public/nope-nope/site").status_code == 404
