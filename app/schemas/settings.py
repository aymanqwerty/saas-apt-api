from pydantic import BaseModel, ConfigDict, Field

# Shown when the doctor hasn't chosen their own wording.
DEFAULT_SECTION_LABEL = "Success Stories"


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_enabled: bool
    gallery_enabled: bool
    show_consultation_fee: bool
    show_contact_information: bool
    payment_required: bool
    section_label: str | None = None


class SettingsUpdate(BaseModel):
    booking_enabled: bool | None = None
    gallery_enabled: bool | None = None
    show_consultation_fee: bool | None = None
    show_contact_information: bool | None = None
    payment_required: bool | None = None
    section_label: str | None = Field(default=None, max_length=50)


class PublicSettings(BaseModel):
    """Toggles the public website needs to know about."""

    booking_enabled: bool
    gallery_enabled: bool
    show_consultation_fee: bool
    show_contact_information: bool
    payment_required: bool = False
    # Always resolved to a usable string for the public site, so the frontend
    # never has to decide on a fallback.
    section_label: str = DEFAULT_SECTION_LABEL
