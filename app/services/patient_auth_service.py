import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.doctor import Doctor, DoctorStatus
from app.models.otp_challenge import OtpChallenge, OtpPurpose
from app.models.patient import Patient
from app.models.patient_account import PatientAccount
from app.repositories.doctor_repository import DoctorRepository
from app.repositories.otp_challenge_repository import OtpChallengeRepository
from app.repositories.patient_account_repository import PatientAccountRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.patient_account import PatientProfile
from app.schemas.patient_auth import AccountSummary, MeResponse, PatientAuthData
from app.services.otp import get_otp_sender

logger = logging.getLogger(__name__)


class PatientAuthService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._doctors = DoctorRepository(db)
        self._accounts = PatientAccountRepository(db)
        self._otps = OtpChallengeRepository(db)
        self._patients = PatientRepository(db)
        self._sender = get_otp_sender()

    # ------------------------------------------------------------------ otp
    def request_otp(self, doctor_slug: str, phone_number: str) -> tuple[int, str | None]:
        doctor = self._require_doctor(doctor_slug)

        code = self._generate_code()
        now = datetime.now(UTC)
        self._otps.invalidate_active(doctor.id, phone_number, now)
        challenge = OtpChallenge(
            doctor_id=doctor.id,
            phone_number=phone_number,
            code_hash=hash_password(code),
            purpose=OtpPurpose.AUTH,
            attempts=0,
            expires_at=now + timedelta(minutes=settings.otp_expiry_minutes),
        )
        self._otps.add(challenge)

        self._sender.send(phone_number, code, doctor_name=doctor.full_name)
        self._db.commit()

        debug_code = code if settings.environment == "development" else None
        return settings.otp_expiry_minutes * 60, debug_code

    def verify_otp(self, doctor_slug: str, phone_number: str, code: str) -> PatientAuthData:
        doctor = self._require_doctor(doctor_slug)
        now = datetime.now(UTC)

        challenge = self._otps.get_active(doctor.id, phone_number, now)
        if challenge is None:
            raise ApiException(400, "This code has expired. Please request a new one.", "OTP_INVALID")

        if challenge.attempts >= settings.otp_max_attempts:
            challenge.consumed_at = now
            self._db.commit()
            raise ApiException(429, "Too many attempts. Please request a new code.", "OTP_LOCKED")

        if not verify_password(code, challenge.code_hash):
            challenge.attempts += 1
            self._db.commit()
            raise ApiException(400, "Incorrect code. Please try again.", "OTP_INVALID")

        challenge.consumed_at = now

        account, is_new = self._get_or_create_account(doctor, phone_number)
        account.is_verified = True
        self._accounts.update_last_login(account)
        self._db.commit()

        logger.info("Patient logged in via OTP: account=%s (new=%s)", account.id, is_new)
        return self._auth_data(account, is_new=is_new)

    # ------------------------------------------------------------- password
    def login_with_password(
        self, doctor_slug: str, phone_number: str, password: str
    ) -> PatientAuthData:
        doctor = self._require_doctor(doctor_slug)
        account = self._accounts.get_by_phone(doctor.id, phone_number)
        if account is None or account.password_hash is None:
            raise ApiException(401, "Invalid phone number or password", "UNAUTHORIZED")
        if not verify_password(password, account.password_hash):
            raise ApiException(401, "Invalid phone number or password", "UNAUTHORIZED")

        self._accounts.update_last_login(account)
        self._db.commit()
        return self._auth_data(account, is_new=False)

    def set_password(self, account: PatientAccount, password: str) -> None:
        account.password_hash = hash_password(password)
        self._db.commit()
        logger.info("Patient set password: account=%s", account.id)

    def me(self, account: PatientAccount) -> MeResponse:
        self_patient = self._patients.get_self_for_account(account.id)
        return MeResponse(
            account=self._summary(account, self_patient),
            profile=PatientProfile.model_validate(self_patient) if self_patient else None,
        )

    # ------------------------------------------------------------- internals
    def _require_doctor(self, slug: str) -> Doctor:
        doctor = self._doctors.get_by_slug(slug)
        if doctor is None:
            raise ApiException(404, "Doctor not found", "NOT_FOUND")
        if doctor.status == DoctorStatus.SUSPENDED:
            raise ApiException(403, "This doctor is not available", "DOCTOR_INACTIVE")
        return doctor

    def _get_or_create_account(
        self, doctor: Doctor, phone_number: str
    ) -> tuple[PatientAccount, bool]:
        existing = self._accounts.get_by_phone(doctor.id, phone_number)
        if existing is not None:
            return existing, False
        account = PatientAccount(
            doctor_id=doctor.id,
            phone_number=phone_number,
            is_verified=True,
        )
        try:
            self._accounts.add(account)
        except IntegrityError:
            # Concurrent verify created the account first — reuse it.
            self._db.rollback()
            existing = self._accounts.get_by_phone(doctor.id, phone_number)
            if existing is None:
                raise
            return existing, False
        return account, True

    def _auth_data(self, account: PatientAccount, *, is_new: bool) -> PatientAuthData:
        token = create_access_token(
            str(account.id),
            token_type="patient",
            expires_minutes=settings.patient_access_token_expire_minutes,
        )
        self_patient: Patient | None = self._patients.get_self_for_account(account.id)
        return PatientAuthData(
            token=token,
            account=self._summary(account, self_patient),
            profile=PatientProfile.model_validate(self_patient) if self_patient else None,
            is_new=is_new,
        )

    def _summary(self, account: PatientAccount, self_patient: Patient | None) -> AccountSummary:
        doctor = self._doctors.get_by_id(account.doctor_id)
        return AccountSummary(
            id=account.id,
            doctor_slug=doctor.slug if doctor else "",
            phone_number=account.phone_number,
            is_verified=account.is_verified,
            has_password=account.password_hash is not None,
            profile_complete=self_patient is not None,
        )

    def _generate_code(self) -> str:
        return "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))
