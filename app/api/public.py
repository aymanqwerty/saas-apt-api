import uuid
from datetime import date

from fastapi import APIRouter

from app.dependencies.database import DbSession
from app.schemas.booking_session import BookingSessionPublic
from app.schemas.common import ApiResponse
from app.schemas.gallery import PublicGalleryDetail, PublicGalleryItem
from app.schemas.public import PublicDoctorProfile, PublicSite, PublicSlot
from app.schemas.public import PublicService as PublicServiceSchema
from app.schemas.settings import PublicSettings
from app.services.booking_session_service import BookingSessionService
from app.services.public_service import PublicService
from app.services.voice_token_service import VoiceTokenService

router = APIRouter()


@router.get(
    "/public/booking-sessions/{token}",
    response_model=ApiResponse[BookingSessionPublic],
)
def get_booking_session(token: str, db: DbSession) -> ApiResponse[BookingSessionPublic]:
    return ApiResponse(data=BookingSessionService(db).get_public(token))


@router.get("/public/voice-token", response_model=ApiResponse[dict])
def get_voice_token(doctor_slug: str, db: DbSession) -> ApiResponse[dict]:
    token = VoiceTokenService(db).webrtc_token(doctor_slug)
    return ApiResponse(data={"token": token})


@router.get("/doctors/public/{slug}", response_model=ApiResponse[PublicDoctorProfile])
def get_public_doctor(slug: str, db: DbSession) -> ApiResponse[PublicDoctorProfile]:
    doctor, clinics = PublicService(db).get_doctor_profile(slug)
    return ApiResponse(data=PublicDoctorProfile(doctor=doctor, clinics=clinics))


@router.get("/doctors/public/{slug}/site", response_model=ApiResponse[PublicSite])
def get_public_site(slug: str, db: DbSession) -> ApiResponse[PublicSite]:
    return ApiResponse(data=PublicService(db).get_site(slug))


@router.get("/doctors/public/{slug}/settings", response_model=ApiResponse[PublicSettings])
def get_public_settings(slug: str, db: DbSession) -> ApiResponse[PublicSettings]:
    return ApiResponse(data=PublicService(db).get_public_settings(slug))


@router.get(
    "/doctors/public/{slug}/gallery",
    response_model=ApiResponse[list[PublicGalleryItem]],
)
def get_public_gallery(slug: str, db: DbSession) -> ApiResponse[list[PublicGalleryItem]]:
    return ApiResponse(data=PublicService(db).list_gallery(slug))


@router.get(
    "/doctors/public/{slug}/gallery/{post_slug}",
    response_model=ApiResponse[PublicGalleryDetail],
)
def get_public_gallery_post(
    slug: str, post_slug: str, db: DbSession
) -> ApiResponse[PublicGalleryDetail]:
    post = PublicService(db).get_gallery_post(slug, post_slug)
    return ApiResponse(data=PublicGalleryDetail.model_validate(post))


@router.get(
    "/doctors/public/{slug}/services",
    response_model=ApiResponse[list[PublicServiceSchema]],
)
def get_public_services(slug: str, db: DbSession) -> ApiResponse[list[PublicServiceSchema]]:
    services = PublicService(db).list_services(slug)
    return ApiResponse(data=[PublicServiceSchema.model_validate(s) for s in services])


@router.get("/public/slots", response_model=ApiResponse[list[PublicSlot]])
def list_public_slots(
    doctor_slug: str,
    clinic_id: uuid.UUID,
    slot_date: date,
    db: DbSession,
) -> ApiResponse[list[PublicSlot]]:
    slots = PublicService(db).list_available_slots(doctor_slug, clinic_id, slot_date)
    return ApiResponse(data=slots)


@router.get("/public/availability-dates", response_model=ApiResponse[list[date]])
def list_public_availability_dates(
    doctor_slug: str,
    clinic_id: uuid.UUID,
    date_from: date,
    date_to: date,
    db: DbSession,
) -> ApiResponse[list[date]]:
    dates = PublicService(db).list_available_dates(doctor_slug, clinic_id, date_from, date_to)
    return ApiResponse(data=dates)
