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
    # Per-PHONE send caps, enforced in the database so they hold across
    # instances and cannot be reset by rotating IPs. This is what protects the
    # SMS bill and stops a victim's handset being bombed; the IP-keyed limiter
    # in the router is a separate, weaker first line.
    otp_max_per_phone_hour: int = 5
    otp_max_per_phone_day: int = 15

    # MSG91 SMS gateway (used when otp_provider=msg91). We generate/verify the
    # OTP ourselves; MSG91 only delivers the code through a DLT-approved template.
    msg91_authkey: str = ""
    msg91_sender_id: str = ""
    # The MSG91 *flow* template id (24-char ObjectId) — see msg91_sender.py for
    # why this goes to the flow API rather than the OTP API.
    msg91_otp_template_id: str = ""
    # Name of the placeholder in that template (##var## -> "var"). Configurable
    # because it is fixed by the DLT registration, which changes on re-approval.
    msg91_otp_variable: str = "var"
    # Prepended to a bare 10-digit number so MSG91 gets full international form.
    msg91_default_country_code: str = "91"

    # Media storage behind the MediaStorage interface. "local" writes to disk
    # (dev only — Cloud Run's filesystem is ephemeral and per-instance, so
    # uploads are lost on every deploy); "gcs" writes to a public bucket.
    media_storage_provider: str = "local"
    media_root: str = "media"
    gcs_bucket: str = ""
    # Optional CDN/custom domain in front of the bucket. Empty = serve from
    # storage.googleapis.com directly.
    gcs_public_base_url: str = ""

    # In-process APScheduler. Must stay FALSE on Cloud Run (frozen CPU between
    # requests, N instances racing the daily job) — drive /internal/jobs/*
    # from Cloud Scheduler there instead.
    scheduler_enabled: bool = True
    # Shared secret for /internal/jobs/*. Empty disables those endpoints.
    internal_job_token: str = ""

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
    # "whatsapp" sends free-form via the Meta WhatsApp Cloud API, and
    # "msg91_whatsapp" sends approved templates via MSG91's WABA API (the only
    # option that reaches patients outside the 24-hour window).
    notification_provider: str = "console"

    # MSG91 WhatsApp (WABA). A SEPARATE MSG91 account from the SMS/OTP one, so
    # it carries its own authkey — msg91_authkey above is not interchangeable.
    msg91_wa_authkey: str = ""
    msg91_wa_integrated_number: str = ""
    msg91_wa_namespace: str = ""
    msg91_wa_language: str = "en"
    msg91_wa_default_country_code: str = "91"
    # Approved template names, keyed by our logical template ids. Defaults match
    # the names registered in MSG91; override per-environment if they diverge.
    msg91_wa_template_appointment_confirmed: str = "appointment_confirmed"
    msg91_wa_template_payment_link: str = "payment_link"
    msg91_wa_template_review_link: str = "review_link"
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
