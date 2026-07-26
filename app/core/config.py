from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    cors_origins: list[str] = ["http://localhost:3000"]

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    auth_cookie_name: str = "access_token"
    auth_cookie_secure: bool = False

    # Patient (public) accounts — a separate identity/session from the doctor
    # dashboard. Patients stay signed in longer and use their own cookie so a
    # patient session never collides with a doctor session in the same browser.
    patient_auth_cookie_name: str = "patient_access_token"
    patient_access_token_expire_minutes: int = 60 * 24 * 30

    # Phone OTP for patient auth. The sender is swappable behind the OtpSender
    # interface; "console" just logs the code (no SMS integration in dev),
    # "msg91" delivers it as an SMS via the MSG91 gateway.
    otp_provider: str = "console"
    otp_length: int = 6
    otp_expiry_minutes: int = 5
    otp_max_attempts: int = 5

    # MSG91 SMS gateway (used when otp_provider=msg91). We generate/verify the
    # OTP ourselves; MSG91 only delivers the code through a DLT-approved template.
    msg91_authkey: str = ""
    msg91_sender_id: str = ""
    msg91_otp_template_id: str = ""
    # Prepended to a bare 10-digit number so MSG91 gets full international form.
    msg91_default_country_code: str = "91"

    media_root: str = "media"

    # Payments. The provider is swappable behind the PaymentProvider interface;
    # `payment_provider` selects the implementation (only "razorpay" today).
    payment_provider: str = "razorpay"
    payment_currency: str = "INR"
    hold_expiry_minutes: int = 10
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    # Secret configured in the Razorpay dashboard for webhook signature checks.
    razorpay_webhook_secret: str = ""

    # Notifications (WhatsApp/SMS) behind the Notifier interface; "console" logs,
    # "whatsapp" sends via the Meta WhatsApp Cloud API.
    notification_provider: str = "console"
    # Meta WhatsApp Cloud API (Meta for Developers). Fill these to send real
    # messages and set notification_provider=whatsapp.
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_api_version: str = "v21.0"
    # Prepended to bare local numbers (e.g. a 10-digit Indian mobile) so WhatsApp
    # gets a full international number. Set "" to disable.
    whatsapp_default_country_code: str = "91"

    # Voice-agent orchestration: how long a review link's draft stays valid.
    review_session_expiry_minutes: int = 60 * 24
    # ElevenLabs account API key (platform-level) — used to mint a per-agent
    # WebRTC conversation token so the website widget can connect to a PRIVATE
    # agent. Leave blank to use a public agent via its id only.
    elevenlabs_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
