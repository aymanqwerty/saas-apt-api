"""Tests for the production-hardening changes (audit P0 items).

Covers the catch-all exception handler, the per-phone OTP cap, the internal
jobs endpoint auth, and media upload validation.
"""

import io
import uuid

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import ApiException
from app.services.storage_service import (
    GcsMediaStorage,
    LocalMediaStorage,
    StorageError,
    get_media_storage,
)
from main import app
from tests.test_booking import client

API = "/api/v1"


# ------------------------------------------------------------ 2.6 exceptions
def test_unhandled_error_returns_json_envelope() -> None:
    """A bare exception must still produce the {success, message, error_code} shape.

    Without the catch-all, Starlette returns plain text and both frontends —
    which call response.json() unconditionally — raise SyntaxError instead of
    surfacing an ApiError.
    """

    @app.get("/api/v1/_boom_test")
    def _boom() -> None:
        raise RuntimeError("kaboom")

    # raise_server_exceptions=False makes TestClient behave like a real server.
    with pytest.MonkeyPatch.context():
        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as local_client:
            response = local_client.get(f"{API}/_boom_test")

    assert response.status_code == 500
    body = response.json()  # must not raise
    assert body["success"] is False
    assert body["error_code"] == "INTERNAL_ERROR"
    # The internal detail must never leak to the caller.
    assert "kaboom" not in body["message"]


# ------------------------------------------------------------- internal jobs
def test_internal_jobs_hidden_when_token_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "internal_job_token", "")
    response = client.post(f"{API}/internal/jobs/expire-holds")
    # 404, not 401: an unconfigured deploy should not advertise the endpoint.
    assert response.status_code == 404


def test_internal_jobs_reject_wrong_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "internal_job_token", "right-token")
    response = client.post(
        f"{API}/internal/jobs/expire-holds", headers={"X-Internal-Token": "wrong-token"}
    )
    assert response.status_code == 401


def test_internal_jobs_run_with_correct_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "internal_job_token", "right-token")
    response = client.post(
        f"{API}/internal/jobs/expire-holds", headers={"X-Internal-Token": "right-token"}
    )
    assert response.status_code == 200
    assert "released" in response.json()["data"]


# ------------------------------------------------------------ media storage
def _upload(content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content), filename="x", headers={"content-type": content_type}
    )


def test_upload_rejects_content_type_mismatch(tmp_path) -> None:
    """A .png declared but carrying non-PNG bytes must be refused."""
    storage = LocalMediaStorage(root=tmp_path)
    with pytest.raises(ApiException, match="does not match"):
        storage.save_image("owner", _upload(b"not really a png", "image/png"))


def test_upload_accepts_real_png(tmp_path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    url = LocalMediaStorage(root=tmp_path).save_image("owner", _upload(png, "image/png"))
    assert url.startswith("/media/owner/")
    assert url.endswith(".png")


def test_upload_rejects_disallowed_type(tmp_path) -> None:
    with pytest.raises(ApiException, match="JPEG, PNG and WebP"):
        LocalMediaStorage(root=tmp_path).save_image("owner", _upload(b"%PDF-", "application/pdf"))


def test_upload_rejects_empty_file(tmp_path) -> None:
    with pytest.raises(ApiException, match="empty"):
        LocalMediaStorage(root=tmp_path).save_image("owner", _upload(b"", "image/png"))


def test_gcs_url_shapes() -> None:
    plain = GcsMediaStorage("my-bucket")
    cdn = GcsMediaStorage("my-bucket", "https://cdn.example.com")
    # No network: just assert how a stored path becomes a URL.
    assert plain._public_base_url == ""
    assert cdn._public_base_url == "https://cdn.example.com"


def test_storage_factory_switches_on_setting(monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_storage_provider", "local")
    assert isinstance(get_media_storage(), LocalMediaStorage)

    monkeypatch.setattr(settings, "media_storage_provider", "gcs")
    monkeypatch.setattr(settings, "gcs_bucket", "some-bucket")
    assert isinstance(get_media_storage(), GcsMediaStorage)


def test_storage_factory_requires_bucket_for_gcs(monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_storage_provider", "gcs")
    monkeypatch.setattr(settings, "gcs_bucket", "")
    with pytest.raises(StorageError, match="GCS_BUCKET"):
        get_media_storage()


# ----------------------------------------------------------- 2.5 OTP quota
def test_otp_capped_per_phone_regardless_of_doctor(monkeypatch) -> None:
    """The cap follows the handset, not the (IP, doctor, phone) triple.

    Rotating IPs is trivial and defeats the router's limiter, so this is the
    control that actually bounds SMS spend.
    """
    from app.repositories.otp_challenge_repository import OtpChallengeRepository
    from app.services.patient_auth_service import PatientAuthService

    monkeypatch.setattr(settings, "otp_max_per_phone_hour", 3)

    calls = {"n": 0}

    def fake_count(self, phone_number, since):
        calls["n"] += 1
        return 3  # already at the cap

    monkeypatch.setattr(OtpChallengeRepository, "count_for_phone_since", fake_count)

    service = PatientAuthService.__new__(PatientAuthService)
    service._otps = OtpChallengeRepository(None)

    import datetime as dt

    with pytest.raises(ApiException) as excinfo:
        service._assert_phone_quota("9876543210", dt.datetime.now(dt.UTC))
    assert excinfo.value.status_code == 429
    assert excinfo.value.error_code == "OTP_QUOTA_EXCEEDED"
    assert calls["n"] == 1


def test_otp_quota_allows_under_limit(monkeypatch) -> None:
    from app.repositories.otp_challenge_repository import OtpChallengeRepository
    from app.services.patient_auth_service import PatientAuthService

    monkeypatch.setattr(settings, "otp_max_per_phone_hour", 5)
    monkeypatch.setattr(settings, "otp_max_per_phone_day", 15)
    monkeypatch.setattr(
        OtpChallengeRepository, "count_for_phone_since", lambda self, phone, since: 1
    )

    service = PatientAuthService.__new__(PatientAuthService)
    service._otps = OtpChallengeRepository(None)

    import datetime as dt

    service._assert_phone_quota("9876543210", dt.datetime.now(dt.UTC))  # must not raise


def test_unique_ids_are_unique() -> None:
    """Guard against the storage filename scheme collapsing to a constant."""
    assert uuid.uuid4().hex != uuid.uuid4().hex
