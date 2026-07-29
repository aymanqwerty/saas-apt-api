import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.clinic import Clinic, ClinicStatus
from app.models.doctor import Doctor, DoctorStatus
from app.models.doctor_settings import DoctorSettings
from app.models.gallery_post import GalleryPost
from app.repositories.blog_category_repository import BlogCategoryRepository
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.doctor_repository import DoctorRepository
from app.repositories.gallery_repository import GalleryRepository
from app.repositories.service_repository import ServiceRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.slot_repository import SlotRepository
from app.schemas.gallery import PublicBlogCategory, PublicGalleryItem
from app.schemas.pagination import Page
from app.schemas.public import PublicClinic, PublicDoctor, PublicSite, PublicSlot
from app.schemas.public import PublicService as PublicServiceSchema
from app.schemas.settings import DEFAULT_SECTION_LABEL, PublicSettings

# Defaults when a doctor has no settings row yet (all features on).
_DEFAULT_SETTINGS = PublicSettings(
    booking_enabled=True,
    gallery_enabled=True,
    show_consultation_fee=True,
    show_contact_information=True,
    payment_required=False,
)


def _cover_image(post: GalleryPost) -> str | None:
    """Explicit cover, else fall back to the first image in the post."""
    if post.cover_image:
        return post.cover_image
    for item in post.media or []:
        if isinstance(item, dict) and item.get("type") == "image":
            return item.get("url")
    return None


def _gallery_item(post: GalleryPost) -> PublicGalleryItem:
    item = PublicGalleryItem.from_post(post)
    item.cover_image = _cover_image(post)
    return item


def _public_clinic(clinic: Clinic, settings: PublicSettings) -> PublicClinic:
    return PublicClinic(
        id=clinic.id,
        clinic_name=clinic.clinic_name,
        address_line_1=clinic.address_line_1,
        address_line_2=clinic.address_line_2,
        city=clinic.city,
        state=clinic.state,
        country=clinic.country,
        google_maps_url=clinic.google_maps_url,
        # Gated by the doctor's website settings.
        phone_number=clinic.phone_number if settings.show_contact_information else None,
        consultation_fee=clinic.consultation_fee if settings.show_consultation_fee else None,
    )


class PublicService:
    """Read-only public website + booking data, gated by the doctor's settings."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._doctors = DoctorRepository(db)
        self._clinics = ClinicRepository(db)
        self._services = ServiceRepository(db)
        self._gallery = GalleryRepository(db)
        self._categories = BlogCategoryRepository(db)
        self._settings = SettingsRepository(db)
        self._slots = SlotRepository(db)

    def _require_active_doctor(self, slug: str) -> Doctor:
        doctor = self._doctors.get_by_slug(slug)
        if doctor is None or doctor.status != DoctorStatus.ACTIVE:
            raise ApiException(404, "Doctor not found", "NOT_FOUND")
        return doctor

    def _settings_for(self, doctor_id: uuid.UUID) -> PublicSettings:
        row: DoctorSettings | None = self._settings.get_for_doctor(doctor_id)
        if row is None:
            return _DEFAULT_SETTINGS
        return PublicSettings(
            booking_enabled=row.booking_enabled,
            gallery_enabled=row.gallery_enabled,
            show_consultation_fee=row.show_consultation_fee,
            show_contact_information=row.show_contact_information,
            payment_required=row.payment_required,
            # Resolve the fallback here so the public site never renders an
            # empty heading if the doctor clears the field.
            section_label=(row.section_label or "").strip() or DEFAULT_SECTION_LABEL,
        )

    def get_public_settings(self, slug: str) -> PublicSettings:
        doctor = self._require_active_doctor(slug)
        return self._settings_for(doctor.id)

    def get_doctor_profile(self, slug: str) -> tuple[PublicDoctor, list[PublicClinic]]:
        doctor = self._require_active_doctor(slug)
        settings = self._settings_for(doctor.id)
        clinics = self._clinics.list_for_doctor(doctor.id, status=ClinicStatus.ACTIVE)
        return (
            PublicDoctor.model_validate(doctor),
            [_public_clinic(c, settings) for c in clinics],
        )

    def get_site(self, slug: str) -> PublicSite:
        doctor = self._require_active_doctor(slug)
        settings = self._settings_for(doctor.id)
        clinics = self._clinics.list_for_doctor(doctor.id, status=ClinicStatus.ACTIVE)
        services = self._services.list_active_for_doctor(doctor.id)
        gallery = (
            [_gallery_item(p) for p in self._gallery.list_published(doctor.id, limit=6)]
            if settings.gallery_enabled
            else []
        )
        return PublicSite(
            doctor=PublicDoctor.model_validate(doctor),
            clinics=[_public_clinic(c, settings) for c in clinics],
            services=[PublicServiceSchema.model_validate(s) for s in services],
            gallery=gallery,
        )

    def list_services(self, slug: str):
        doctor = self._require_active_doctor(slug)
        return self._services.list_active_for_doctor(doctor.id)

    def list_gallery(
        self,
        slug: str,
        *,
        category: str | None = None,
        page: int = 1,
        limit: int = 12,
    ) -> Page[PublicGalleryItem]:
        doctor = self._require_active_doctor(slug)
        if not self._settings_for(doctor.id).gallery_enabled:
            raise ApiException(404, "This section is not available", "NOT_FOUND")
        posts, total = self._gallery.list_published_page(
            doctor.id, category_slug=category, page=page, limit=limit
        )
        return Page.build([_gallery_item(p) for p in posts], total, page, limit)

    def list_gallery_categories(self, slug: str) -> list[PublicBlogCategory]:
        """Categories that actually have published posts — empty chips are noise."""
        doctor = self._require_active_doctor(slug)
        if not self._settings_for(doctor.id).gallery_enabled:
            raise ApiException(404, "This section is not available", "NOT_FOUND")
        counts = self._categories.published_counts(doctor.id)
        return [
            PublicBlogCategory(name=c.name, slug=c.slug, post_count=counts.get(c.id, 0))
            for c in self._categories.list_for_doctor(doctor.id)
            if counts.get(c.id, 0) > 0
        ]

    def get_gallery_post(self, slug: str, post_slug: str) -> GalleryPost:
        doctor = self._require_active_doctor(slug)
        if not self._settings_for(doctor.id).gallery_enabled:
            raise ApiException(404, "Gallery is not available", "NOT_FOUND")
        post = self._gallery.get_published_by_slug(doctor.id, post_slug)
        if post is None:
            raise ApiException(404, "Post not found", "NOT_FOUND")
        return post

    def list_available_dates(
        self, doctor_slug: str, clinic_id: uuid.UUID, from_date: date, to_date: date
    ) -> list[date]:
        doctor = self._require_active_doctor(doctor_slug)
        if not self._settings_for(doctor.id).booking_enabled:
            return []

        clinic = self._clinics.get_for_doctor(doctor.id, clinic_id)
        if clinic is None or clinic.status != ClinicStatus.ACTIVE:
            raise ApiException(404, "Clinic not found", "NOT_FOUND")

        return self._slots.list_available_dates(clinic_id, from_date, to_date)

    def list_available_slots(
        self, doctor_slug: str, clinic_id: uuid.UUID, slot_date: date
    ) -> list[PublicSlot]:
        doctor = self._require_active_doctor(doctor_slug)
        if not self._settings_for(doctor.id).booking_enabled:
            return []

        clinic = self._clinics.get_for_doctor(doctor.id, clinic_id)
        if clinic is None or clinic.status != ClinicStatus.ACTIVE:
            raise ApiException(404, "Clinic not found", "NOT_FOUND")

        slots = self._slots.list_public_for_date(clinic_id, slot_date)
        return [
            PublicSlot(
                id=slot.id,
                slot_date=slot.slot_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                capacity=slot.capacity,
                remaining=max(slot.capacity - slot.booked_count, 0),
                available_count=max(slot.capacity - slot.booked_count, 0),
            )
            for slot in slots
        ]
