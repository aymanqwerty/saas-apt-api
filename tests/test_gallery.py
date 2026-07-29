import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.blog_category import BlogCategory
from app.models.doctor import Doctor
from app.models.doctor_settings import DoctorSettings
from app.models.gallery_post import GalleryPost
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"
API = "/api/v1"


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
        f"{API}/auth/login", json={"email": f"gal-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]

    yield {"slug": slug, "headers": {"Authorization": f"Bearer {token}"}, "doctor_id": doctor_id}

    with SessionLocal() as db:
        db.query(GalleryPost).filter(GalleryPost.doctor_id == doctor_id).delete()
        db.query(BlogCategory).filter(BlogCategory.doctor_id == doctor_id).delete()
        db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_id).delete()
        # PATCH /settings lazily creates this row; the FK is RESTRICT.
        db.query(DoctorSettings).filter(DoctorSettings.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _post_body(**overrides) -> dict:
    body = {
        "title": "Smile Makeover",
        "introduction": "A full smile makeover case.",
        "media": [{"type": "image", "url": "https://example.com/a.jpg"}],
        "tags": ["dental", "cosmetic"],
        "status": "DRAFT",
    }
    body.update(overrides)
    return body


def test_gallery_crud_and_slug(context: dict) -> None:
    headers = context["headers"]
    created = client.post(f"{API}/gallery", headers=headers, json=_post_body())
    assert created.status_code == 201, created.text
    assert created.json()["data"]["slug"] == "smile-makeover"

    # Same title again → slug de-duplicated.
    second = client.post(f"{API}/gallery", headers=headers, json=_post_body())
    assert second.json()["data"]["slug"] == "smile-makeover-2"

    post_id = created.json()["data"]["id"]
    published = client.patch(
        f"{API}/gallery/{post_id}", headers=headers, json={"status": "PUBLISHED"}
    )
    assert published.json()["data"]["published_at"] is not None
    # Publishing back-fills the card date.
    assert published.json()["data"]["display_date"] is not None

    assert len(client.get(f"{API}/gallery", headers=headers).json()["data"]) == 2

    deleted = client.delete(f"{API}/gallery/{post_id}", headers=headers)
    assert deleted.status_code == 200
    assert len(client.get(f"{API}/gallery", headers=headers).json()["data"]) == 1


def test_slug_frozen_when_title_changes(context: dict) -> None:
    """Renaming a post must not change its URL — links are already shared."""
    headers = context["headers"]
    created = client.post(f"{API}/gallery", headers=headers, json=_post_body())
    post_id = created.json()["data"]["id"]

    renamed = client.patch(
        f"{API}/gallery/{post_id}", headers=headers, json={"title": "Completely New Title"}
    )
    assert renamed.json()["data"]["title"] == "Completely New Title"
    assert renamed.json()["data"]["slug"] == "smile-makeover"


def test_public_gallery_only_published(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]

    client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(title="Public Case", status="PUBLISHED"),
    )
    client.post(
        f"{API}/gallery", headers=headers, json=_post_body(title="Draft Case", status="DRAFT")
    )

    page = client.get(f"{API}/doctors/public/{slug}/gallery").json()["data"]
    assert page["meta"]["total"] == 1
    assert page["items"][0]["title"] == "Public Case"

    detail = client.get(f"{API}/doctors/public/{slug}/gallery/public-case")
    assert detail.status_code == 200
    assert detail.json()["data"]["introduction"]

    # Draft is not reachable publicly.
    assert client.get(f"{API}/doctors/public/{slug}/gallery/draft-case").status_code == 404


# ------------------------------------------------------------------ categories
def test_category_crud_and_reuse(context: dict) -> None:
    headers = context["headers"]
    created = client.post(f"{API}/gallery/categories", headers=headers, json={"name": "Deliveries"})
    assert created.status_code == 201
    assert created.json()["data"]["slug"] == "deliveries"
    category_id = created.json()["data"]["id"]

    # Typing an existing name reuses it instead of making a near-duplicate.
    again = client.post(f"{API}/gallery/categories", headers=headers, json={"name": "deliveries"})
    assert again.json()["data"]["id"] == category_id
    assert len(client.get(f"{API}/gallery/categories", headers=headers).json()["data"]) == 1

    renamed = client.patch(
        f"{API}/gallery/categories/{category_id}", headers=headers, json={"name": "Childbirth"}
    )
    assert renamed.json()["data"]["name"] == "Childbirth"


def test_deleting_category_keeps_posts(context: dict) -> None:
    """A deleted category must orphan its posts, never delete them."""
    headers = context["headers"]
    category_id = client.post(
        f"{API}/gallery/categories", headers=headers, json={"name": "Surgery"}
    ).json()["data"]["id"]

    post_id = client.post(
        f"{API}/gallery", headers=headers, json=_post_body(category_id=category_id)
    ).json()["data"]["id"]

    removed = client.delete(f"{API}/gallery/categories/{category_id}", headers=headers)
    assert removed.status_code == 200

    post = client.get(f"{API}/gallery/{post_id}", headers=headers).json()["data"]
    assert post["category_id"] is None
    assert post["category_name"] is None


def test_public_category_filter_and_counts(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]
    category_id = client.post(
        f"{API}/gallery/categories", headers=headers, json={"name": "Deliveries"}
    ).json()["data"]["id"]

    client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(title="In Category", status="PUBLISHED", category_id=category_id),
    )
    client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(title="No Category", status="PUBLISHED"),
    )

    everything = client.get(f"{API}/doctors/public/{slug}/gallery").json()["data"]
    assert everything["meta"]["total"] == 2

    filtered = client.get(
        f"{API}/doctors/public/{slug}/gallery?category=deliveries"
    ).json()["data"]
    assert filtered["meta"]["total"] == 1
    assert filtered["items"][0]["title"] == "In Category"
    assert filtered["items"][0]["category_name"] == "Deliveries"

    categories = client.get(f"{API}/doctors/public/{slug}/gallery/categories").json()["data"]
    assert categories == [{"name": "Deliveries", "slug": "deliveries", "post_count": 1}]


def test_categories_with_no_published_posts_are_hidden(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]
    category_id = client.post(
        f"{API}/gallery/categories", headers=headers, json={"name": "Empty"}
    ).json()["data"]["id"]
    # Draft only — the chip would filter to nothing, so it must not appear.
    client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(status="DRAFT", category_id=category_id),
    )

    assert client.get(f"{API}/doctors/public/{slug}/gallery/categories").json()["data"] == []


# --------------------------------------------------------------------- content
def test_body_html_is_sanitised(context: dict) -> None:
    """Script must never survive into a patient-facing page."""
    headers = context["headers"]
    created = client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(
            body="<p>Safe <strong>text</strong></p><script>alert(1)</script>"
            '<a href="javascript:alert(2)">bad link</a>'
        ),
    )
    body = created.json()["data"]["body"]
    assert "<script>" not in body
    assert "javascript:" not in body
    assert "<strong>text</strong>" in body


def test_youtube_urls_are_normalised(context: dict) -> None:
    headers = context["headers"]
    created = client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(
            media=[
                {"type": "youtube", "url": "https://youtu.be/dQw4w9WgXcQ"},
                {"type": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghijk&t=30"},
                {"type": "image", "url": "https://example.com/x.jpg", "description": "An x-ray"},
            ]
        ),
    )
    media = created.json()["data"]["media"]
    assert media[0]["youtube_id"] == "dQw4w9WgXcQ"
    assert media[1]["youtube_id"] == "abcdefghijk"
    assert media[2]["youtube_id"] is None
    assert media[2]["description"] == "An x-ray"


def test_rejects_unparseable_youtube_and_bad_scheme(context: dict) -> None:
    headers = context["headers"]
    bad_video = client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(media=[{"type": "youtube", "url": "https://example.com/not-a-video"}]),
    )
    assert bad_video.status_code == 422

    bad_scheme = client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(media=[{"type": "image", "url": "javascript:alert(1)"}]),
    )
    assert bad_scheme.status_code == 422


def test_display_order_controls_public_ordering(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]
    for title, order in (("Third", 3), ("First", 1), ("Second", 2)):
        client.post(
            f"{API}/gallery",
            headers=headers,
            json=_post_body(title=title, status="PUBLISHED", display_order=order),
        )
    # No order set — must sort after everything that has one.
    client.post(
        f"{API}/gallery", headers=headers, json=_post_body(title="Unordered", status="PUBLISHED")
    )

    items = client.get(f"{API}/doctors/public/{slug}/gallery").json()["data"]["items"]
    assert [i["title"] for i in items] == ["First", "Second", "Third", "Unordered"]


def test_public_gallery_pagination(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]
    for index in range(5):
        client.post(
            f"{API}/gallery",
            headers=headers,
            json=_post_body(title=f"Post {index}", status="PUBLISHED", display_order=index),
        )

    first = client.get(f"{API}/doctors/public/{slug}/gallery?page=1&limit=2").json()["data"]
    assert len(first["items"]) == 2
    assert first["meta"]["total"] == 5
    assert first["meta"]["total_pages"] == 3

    last = client.get(f"{API}/doctors/public/{slug}/gallery?page=3&limit=2").json()["data"]
    assert len(last["items"]) == 1


def test_cover_image_falls_back_to_first_image(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]
    client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(
            title="No Cover",
            status="PUBLISHED",
            media=[{"type": "image", "url": "https://example.com/fallback.jpg"}],
        ),
    )
    items = client.get(f"{API}/doctors/public/{slug}/gallery").json()["data"]["items"]
    assert items[0]["cover_image"] == "https://example.com/fallback.jpg"


def test_section_label_defaults_and_updates(context: dict) -> None:
    headers = context["headers"]
    slug = context["slug"]

    public = client.get(f"{API}/doctors/public/{slug}/settings").json()["data"]
    assert public["section_label"] == "Success Stories"

    client.patch(f"{API}/settings", headers=headers, json={"section_label": "Achievements"})
    public = client.get(f"{API}/doctors/public/{slug}/settings").json()["data"]
    assert public["section_label"] == "Achievements"

    # Clearing it falls back rather than rendering an empty heading.
    client.patch(f"{API}/settings", headers=headers, json={"section_label": "  "})
    public = client.get(f"{API}/doctors/public/{slug}/settings").json()["data"]
    assert public["section_label"] == "Success Stories"


def test_tenant_isolation_on_categories(context: dict) -> None:
    """Doctor A must not be able to attach doctor B's category."""
    headers = context["headers"]
    other = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        intruder = Doctor(
            full_name="Other Doctor",
            slug=f"dr-other-{other}",
            email=f"other-{other}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9888888888",
            specialization="Testing",
        )
        db.add(intruder)
        db.commit()
        db.refresh(intruder)
        intruder_id = intruder.id

    try:
        intruder_headers = {
            "Authorization": "Bearer "
            + client.post(
                f"{API}/auth/login",
                json={"email": f"other-{other}@example.com", "password": PASSWORD},
            ).json()["data"]["token"]
        }
        foreign_category = client.post(
            f"{API}/gallery/categories", headers=intruder_headers, json={"name": "Theirs"}
        ).json()["data"]["id"]

        attempt = client.post(
            f"{API}/gallery", headers=headers, json=_post_body(category_id=foreign_category)
        )
        assert attempt.status_code == 404
    finally:
        with SessionLocal() as db:
            db.query(BlogCategory).filter(BlogCategory.doctor_id == intruder_id).delete()
            db.query(ActivityLog).filter(ActivityLog.doctor_id == intruder_id).delete()
            db.delete(db.get(Doctor, intruder_id))
            db.commit()


def test_instagram_urls_are_parsed_for_embedding(context: dict) -> None:
    """Embeddable posts get a shortcode; profile links deliberately do not."""
    headers = context["headers"]
    created = client.post(
        f"{API}/gallery",
        headers=headers,
        json=_post_body(
            media=[
                {"type": "instagram", "url": "https://www.instagram.com/p/CxYz123AbCd/"},
                {"type": "instagram", "url": "https://instagram.com/reel/AbC-dEf_123"},
                {"type": "instagram", "url": "https://www.instagram.com/drsurbhi/"},
            ]
        ),
    )
    media = created.json()["data"]["media"]
    assert (media[0]["instagram_kind"], media[0]["instagram_id"]) == ("p", "CxYz123AbCd")
    assert (media[1]["instagram_kind"], media[1]["instagram_id"]) == ("reel", "AbC-dEf_123")
    # A profile link has no shortcode — the client falls back to a plain link.
    assert media[2]["instagram_id"] is None
