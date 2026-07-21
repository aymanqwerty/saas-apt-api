import io
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.doctor import Doctor
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def doctor_token() -> Generator[tuple[Doctor, str], None, None]:
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        record = Doctor(
            full_name="Profile Test Doctor",
            slug=f"dr-profile-{unique}",
            email=f"profile-{unique}@example.com",
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
        db.delete(db.get(Doctor, record.id))
        db.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_profile(doctor_token: tuple[Doctor, str]) -> None:
    doctor, token = doctor_token

    response = client.get("/api/v1/doctors/profile", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["email"] == doctor.email


def test_update_profile_fields(doctor_token: tuple[Doctor, str]) -> None:
    _, token = doctor_token

    response = client.patch(
        "/api/v1/doctors/profile",
        headers=_auth(token),
        json={
            "full_name": "Dr. Updated Name",
            "experience_years": 15,
            "languages": ["English", "Hindi"],
            "about": "Updated biography.",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["full_name"] == "Dr. Updated Name"
    assert data["experience_years"] == 15
    assert data["languages"] == ["English", "Hindi"]


def test_slug_is_immutable(doctor_token: tuple[Doctor, str]) -> None:
    doctor, token = doctor_token

    response = client.patch(
        "/api/v1/doctors/profile",
        headers=_auth(token),
        json={"slug": "dr-hijacked", "full_name": "Dr. Slug Test"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["slug"] == doctor.slug


def test_email_conflict_returns_409(doctor_token: tuple[Doctor, str]) -> None:
    _, token = doctor_token
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        other = Doctor(
            full_name="Other Doctor",
            slug=f"dr-other-{unique}",
            email=f"other-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-8888888888",
            specialization="Testing",
        )
        db.add(other)
        db.commit()
        other_email = other.email
        other_id = other.id

    try:
        response = client.patch(
            "/api/v1/doctors/profile",
            headers=_auth(token),
            json={"email": other_email},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "CONFLICT"
    finally:
        with SessionLocal() as db:
            db.delete(db.get(Doctor, other_id))
            db.commit()


def test_invalid_experience_years_returns_422(
    doctor_token: tuple[Doctor, str],
) -> None:
    _, token = doctor_token

    response = client.patch(
        "/api/v1/doctors/profile",
        headers=_auth(token),
        json={"experience_years": -1},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_media_upload_png(doctor_token: tuple[Doctor, str]) -> None:
    _, token = doctor_token
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    response = client.post(
        "/api/v1/media/upload",
        headers=_auth(token),
        files={"file": ("photo.png", io.BytesIO(png_bytes), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["url"].startswith("/media/")


def test_media_upload_rejects_non_image(doctor_token: tuple[Doctor, str]) -> None:
    _, token = doctor_token

    response = client.post(
        "/api/v1/media/upload",
        headers=_auth(token),
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"
