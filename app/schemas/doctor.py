import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.doctor import DoctorStatus


class DoctorResponse(BaseModel):
    """Doctor as returned to the authenticated dashboard. Never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    slug: str
    email: str
    phone_number: str
    profile_photo: str | None
    qualification: str | None
    specialization: str
    experience_years: int
    registration_number: str | None
    about: str | None
    languages: list[str] | None
    status: DoctorStatus


class DoctorProfileUpdate(BaseModel):
    """Partial profile update. Slug is immutable and deliberately absent (docs/03 §2)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)
    profile_photo: str | None = None
    qualification: str | None = Field(default=None, max_length=500)
    specialization: str | None = Field(default=None, min_length=1, max_length=150)
    experience_years: int | None = Field(default=None, ge=0, le=80)
    registration_number: str | None = Field(default=None, max_length=100)
    about: str | None = Field(default=None, max_length=5000)
    languages: list[str] | None = None
