import uuid
from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.gallery import PublicGalleryItem


class PublicClinic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_name: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    country: str
    google_maps_url: str | None
    phone_number: str | None
    consultation_fee: Decimal | None


class PublicDoctor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    slug: str
    specialization: str
    qualification: str | None
    about: str | None
    profile_photo: str | None
    experience_years: int
    languages: list[str] | None


class PublicService(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    image_url: str | None


class PublicDoctorProfile(BaseModel):
    doctor: PublicDoctor
    clinics: list[PublicClinic]


class PublicSite(BaseModel):
    doctor: PublicDoctor
    clinics: list[PublicClinic]
    services: list[PublicService]
    gallery: list[PublicGalleryItem]


class PublicSlot(BaseModel):
    id: uuid.UUID
    slot_date: date
    start_time: time
    end_time: time
    capacity: int
    remaining: int
    available_count: int
