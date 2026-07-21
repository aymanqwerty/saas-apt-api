import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.doctor import Doctor
from app.models.gallery_post import GalleryPost
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


@pytest.fixture
def context() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-gal-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Gallery Doctor",
            slug=slug,
            email=f"gal-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Dermatology",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"gal-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]

    yield {"slug": slug, "headers": {"Authorization": f"Bearer {token}"}}

    with SessionLocal() as db:
        db.query(GalleryPost).filter(GalleryPost.doctor_id == doctor_id).delete()
        db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_gallery_crud_and_slug(context: dict) -> None:
    headers = context["headers"]
    payload = {
        "title": "Smile Makeover",
        "description": "A full smile makeover case.",
        "category": "Case Study",
        "media": [{"type": "image", "url": "https://example.com/a.jpg"}],
        "tags": ["dental", "cosmetic"],
        "status": "DRAFT",
    }
    created = client.post("/api/v1/gallery", headers=headers, json=payload)
    assert created.status_code == 201
    assert created.json()["data"]["slug"] == "smile-makeover"

    # Same title again → slug de-duplicated.
    second = client.post("/api/v1/gallery", headers=headers, json=payload)
    assert second.json()["data"]["slug"] == "smile-makeover-2"

    post_id = created.json()["data"]["id"]
    published = client.patch(
        f"/api/v1/gallery/{post_id}", headers=headers, json={"status": "PUBLISHED"}
    )
    assert published.json()["data"]["published_at"] is not None

    assert len(client.get("/api/v1/gallery", headers=headers).json()["data"]) == 2

    deleted = client.delete(f"/api/v1/gallery/{post_id}", headers=headers)
    assert deleted.status_code == 200
    assert len(client.get("/api/v1/gallery", headers=headers).json()["data"]) == 1


def test_public_gallery_only_published(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]

    client.post(
        "/api/v1/gallery",
        headers=headers,
        json={"title": "Public Case", "description": "d", "status": "PUBLISHED"},
    )
    client.post(
        "/api/v1/gallery",
        headers=headers,
        json={"title": "Draft Case", "description": "d", "status": "DRAFT"},
    )

    public_list = client.get(f"/api/v1/doctors/public/{slug}/gallery").json()["data"]
    assert len(public_list) == 1
    assert public_list[0]["title"] == "Public Case"

    detail = client.get(f"/api/v1/doctors/public/{slug}/gallery/public-case")
    assert detail.status_code == 200

    # Draft is not reachable publicly.
    assert client.get(f"/api/v1/doctors/public/{slug}/gallery/draft-case").status_code == 404
