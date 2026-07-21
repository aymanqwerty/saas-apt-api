from pydantic import BaseModel, ConfigDict


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_enabled: bool
    gallery_enabled: bool
    show_consultation_fee: bool
    show_contact_information: bool
    payment_required: bool


class SettingsUpdate(BaseModel):
    booking_enabled: bool | None = None
    gallery_enabled: bool | None = None
    show_consultation_fee: bool | None = None
    show_contact_information: bool | None = None
    payment_required: bool | None = None


class PublicSettings(BaseModel):
    """Toggles the public website needs to know about."""

    booking_enabled: bool
    gallery_enabled: bool
    show_consultation_fee: bool
    show_contact_information: bool
    payment_required: bool = False
