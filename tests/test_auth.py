import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.doctor import Doctor, DoctorStatus
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


def _make_doctor(status: DoctorStatus = DoctorStatus.ACTIVE) -> Doctor:
    unique = uuid.uuid4().hex[:10]
    return Doctor(
        full_name="Test Doctor",
        slug=f"dr-test-{unique}",
        email=f"test-{unique}@example.com",
        password_hash=hash_password(PASSWORD),
        phone_number="+91-9999999999",
        specialization="Testing",
        status=status,
    )


def _cleanup_doctor(doctor_id) -> None:
    with SessionLocal() as db:
        db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


@pytest.fixture
def doctor() -> Generator[Doctor, None, None]:
    with SessionLocal() as db:
        record = _make_doctor()
        db.add(record)
        db.commit()
        db.refresh(record)
    yield record
    _cleanup_doctor(record.id)


@pytest.fixture
def suspended_doctor() -> Generator[Doctor, None, None]:
    with SessionLocal() as db:
        record = _make_doctor(status=DoctorStatus.SUSPENDED)
        db.add(record)
        db.commit()
        db.refresh(record)
    yield record
    _cleanup_doctor(record.id)


def test_login_success_returns_token_and_sets_cookie(doctor: Doctor) -> None:
    response = client.post("/api/v1/auth/login", json={"email": doctor.email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["token"]
    assert body["data"]["doctor"]["email"] == doctor.email
    assert "password_hash" not in body["data"]["doctor"]
    assert settings.auth_cookie_name in response.cookies


def test_login_wrong_password_returns_401(doctor: Doctor) -> None:
    response = client.post("/api/v1/auth/login", json={"email": doctor.email, "password": "wrong"})

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "UNAUTHORIZED"


def test_login_suspended_doctor_returns_403(suspended_doctor: Doctor) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": suspended_doctor.email, "password": PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "FORBIDDEN"


def test_login_rate_limited_after_five_attempts(doctor: Doctor) -> None:
    rate_limit_email = f"rate-limit-{uuid.uuid4().hex[:8]}@example.com"
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": rate_limit_email, "password": "wrong"},
        )

    response = client.post(
        "/api/v1/auth/login", json={"email": rate_limit_email, "password": "wrong"}
    )

    assert response.status_code == 429
    assert response.json()["error_code"] == "RATE_LIMITED"


def test_me_with_bearer_token(doctor: Doctor) -> None:
    login = client.post("/api/v1/auth/login", json={"email": doctor.email, "password": PASSWORD})
    token = login.json()["data"]["token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["data"]["email"] == doctor.email


def test_me_without_token_returns_401() -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_logout_clears_cookie(doctor: Doctor) -> None:
    login = client.post("/api/v1/auth/login", json={"email": doctor.email, "password": PASSWORD})
    token = login.json()["data"]["token"]

    response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert settings.auth_cookie_name in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
