import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.phone import normalize_phone
from app.models.appointment import Appointment, AppointmentStatus, BookingSource
from app.models.appointment_hold import AppointmentHold, HoldStatus
from app.models.booking_session import BookingSession, BookingSessionStatus
from app.models.clinic import Clinic, ClinicStatus
from app.models.doctor import Doctor, DoctorStatus
from app.models.patient import Patient, PatientRelationship
from app.models.patient_account import PatientAccount
from app.models.payment import Payment, PaymentStatus
from app.models.slot import Slot, SlotStatus
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.booking_session_repository import BookingSessionRepository
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.doctor_repository import DoctorRepository
from app.repositories.hold_repository import HoldRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.slot_repository import SlotRepository
from app.schemas.agent import AgentBookingRequest, AgentBookingResult
from app.schemas.booking import (
    BookingConfirmation,
    BookingRequest,
    BookingStartResponse,
    ConfirmPaymentRequest,
    PaymentOrderInfo,
)
from app.services.activity_log_service import ActivityLogService
from app.services.notifications import get_notifier
from app.services.payments import PaymentError, PaymentProvider, get_payment_provider
from app.utils.address import compose_clinic_address

logger = logging.getLogger(__name__)

_APPOINTMENT_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _generate_appointment_number() -> str:
    suffix = "".join(secrets.choice(_APPOINTMENT_ALPHABET) for _ in range(8))
    return f"APT-{suffix}"


class BookingService:
    def __init__(self, db: Session, provider: PaymentProvider | None = None) -> None:
        self._db = db
        self._doctors = DoctorRepository(db)
        self._clinics = ClinicRepository(db)
        self._slots = SlotRepository(db)
        self._patients = PatientRepository(db)
        self._appointments = AppointmentRepository(db)
        self._holds = HoldRepository(db)
        self._payments = PaymentRepository(db)
        self._settings = SettingsRepository(db)
        self._sessions = BookingSessionRepository(db)
        self._activity = ActivityLogService(db)
        # Injectable so tests can supply a fake gateway; defaults to the configured one.
        self._provider = provider or get_payment_provider()
        self._notifier = get_notifier()

    # ------------------------------------------------------------------ start
    def start_booking(
        self,
        data: BookingRequest,
        request: Request | None = None,
        account: PatientAccount | None = None,
    ) -> BookingStartResponse:
        """Reserve a seat and, if advance payment is required, open a payment order.

        Free bookings are confirmed immediately. Paid bookings hold the seat for
        `settings.hold_expiry_minutes` while the patient pays; the appointment is
        created only once payment is verified in `confirm_booking`. A logged-in
        patient books for a saved profile (self or family member); guests supply
        their details inline exactly as before.
        """
        doctor = self._doctors.get_by_slug(data.doctor_slug)
        if doctor is None:
            raise ApiException(404, "Doctor not found", "NOT_FOUND")
        if doctor.status != DoctorStatus.ACTIVE:
            raise ApiException(403, "This doctor is not accepting bookings", "DOCTOR_INACTIVE")

        settings_row = self._settings.get_for_doctor(doctor.id)
        if settings_row is not None and not settings_row.booking_enabled:
            raise ApiException(403, "Online booking is currently disabled", "BOOKING_DISABLED")

        slot = self._slots.get_for_doctor(doctor.id, data.slot_id)
        if slot is None:
            raise ApiException(404, "Slot not found", "NOT_FOUND")

        clinic = self._clinics.get_for_doctor(doctor.id, slot.clinic_id)
        if clinic is None or clinic.status != ClinicStatus.ACTIVE:
            raise ApiException(403, "This clinic is not accepting bookings", "CLINIC_INACTIVE")

        self._assert_bookable(slot, clinic)

        patient = self._resolve_patient(doctor, data, account)

        if self._appointments.has_active_for_slot_patient(slot.id, patient.id):
            raise ApiException(409, "You already have a booking for this slot", "DUPLICATE_BOOKING")
        if self._holds.has_active_for_slot_patient(slot.id, patient.id):
            raise ApiException(
                409, "You already have a pending booking for this slot", "DUPLICATE_BOOKING"
            )

        # Atomically claim one seat; the same guard prevents overbooking across
        # confirmed bookings AND live holds (both live in booked_count).
        if not self._slots.claim_capacity(slot.id):
            raise ApiException(409, "This slot is no longer available", "SLOT_FULL")

        payment_required, fee = self._resolve_payment(settings_row, clinic)

        if not payment_required:
            appointment = self._create_appointment(doctor, clinic, slot, patient, data.reason)
            self._slots.mark_full_if_reached(slot.id)
            self._activity.record(
                doctor.id, "BOOK_APPOINTMENT", "Appointment", appointment.id, request=request
            )
            self._db.commit()
            self._db.refresh(appointment)
            logger.info("Appointment booked (free): %s", appointment.id)
            return BookingStartResponse(
                status="confirmed",
                appointment=BookingConfirmation.model_validate(appointment),
            )

        # Paid path: create the hold, then the gateway order. If the gateway call
        # fails, the whole transaction (incl. the seat claim) is rolled back.
        hold = AppointmentHold(
            doctor_id=doctor.id,
            clinic_id=clinic.id,
            slot_id=slot.id,
            patient_id=patient.id,
            visit_reason=data.reason,
            status=HoldStatus.HELD,
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.hold_expiry_minutes),
        )
        self._holds.add(hold)

        try:
            order = self._provider.create_order(
                fee, settings.payment_currency, receipt=str(hold.id)
            )
        except PaymentError:
            self._db.rollback()  # releases the claimed seat
            logger.exception("Payment order creation failed for slot %s", slot.id)
            raise ApiException(
                502, "Could not start the payment. Please try again.", "PAYMENT_INIT_FAILED"
            ) from None

        payment = Payment(
            doctor_id=doctor.id,
            hold_id=hold.id,
            patient_id=patient.id,
            clinic_id=clinic.id,
            amount=fee,
            currency=settings.payment_currency,
            status=PaymentStatus.PENDING,
            provider=self._provider.name,
            provider_order_id=order.order_id,
            patient_name=patient.full_name,
            clinic_name=clinic.clinic_name,
        )
        self._payments.add(payment)
        self._activity.record(
            doctor.id, "HOLD_APPOINTMENT", "AppointmentHold", hold.id, request=request
        )
        self._db.commit()
        logger.info("Slot held pending payment: hold=%s slot=%s", hold.id, slot.id)

        return BookingStartResponse(
            status="payment_required",
            hold_id=hold.id,
            payment=PaymentOrderInfo(
                provider=self._provider.name,
                order_id=order.order_id,
                amount=order.amount,
                currency=order.currency,
                key_id=settings.razorpay_key_id,
                display_amount=fee,
                doctor_name=doctor.full_name,
                clinic_name=clinic.clinic_name,
            ),
        )

    # ---------------------------------------------------------------- confirm
    def confirm_booking(
        self, hold_id, payload: ConfirmPaymentRequest, request: Request | None = None
    ) -> BookingConfirmation:
        """Verify the payment and turn a held seat into a confirmed appointment."""
        hold = self._holds.get(hold_id)
        if hold is None:
            raise ApiException(404, "Reservation not found", "NOT_FOUND")

        payment = self._payments.get_by_hold(hold.id)

        if hold.status == HoldStatus.CONFIRMED:
            # Idempotent: return the already-created appointment.
            appointment = None
            if payment is not None and payment.appointment_id is not None:
                appointment = self._appointments.get_for_doctor(
                    hold.doctor_id, payment.appointment_id
                )
            if appointment is None:
                raise ApiException(
                    409, "This reservation is already confirmed", "ALREADY_CONFIRMED"
                )
            return BookingConfirmation.model_validate(appointment)

        if hold.status != HoldStatus.HELD:
            raise ApiException(409, "This reservation has expired", "HOLD_EXPIRED")

        if hold.expires_at <= datetime.now(UTC):
            self._release_hold(hold, payment, HoldStatus.EXPIRED, "expired")
            self._db.commit()
            raise ApiException(409, "This reservation has expired", "HOLD_EXPIRED")

        if payment is None:
            raise ApiException(409, "No payment is associated with this reservation", "NO_PAYMENT")

        if payload.order_id != payment.provider_order_id:
            raise ApiException(400, "Payment does not match this reservation", "PAYMENT_MISMATCH")

        verified = self._provider.verify_payment(
            payment.provider_order_id, payload.payment_id, payload.signature
        )
        if not verified:
            payment.provider_payment_id = payload.payment_id
            self._release_hold(hold, payment, HoldStatus.EXPIRED, "signature verification failed")
            self._db.commit()
            raise ApiException(402, "Payment could not be verified", "PAYMENT_FAILED")

        doctor = self._doctors.get_by_id(hold.doctor_id)
        clinic = self._clinics.get_for_doctor(hold.doctor_id, hold.clinic_id)
        slot = self._slots.get_for_doctor(hold.doctor_id, hold.slot_id)
        patient = self._patients.get_for_doctor(hold.doctor_id, hold.patient_id)
        if doctor is None or clinic is None or slot is None or patient is None:
            raise ApiException(409, "This reservation is no longer valid", "HOLD_INVALID")

        appointment = self._create_appointment(doctor, clinic, slot, patient, hold.visit_reason)
        self._slots.mark_full_if_reached(slot.id)

        hold.status = HoldStatus.CONFIRMED
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = payload.payment_id
        payment.provider_signature = payload.signature
        payment.appointment_id = appointment.id

        self._activity.record(
            doctor.id, "BOOK_APPOINTMENT", "Appointment", appointment.id, request=request
        )
        self._db.commit()
        self._db.refresh(appointment)
        logger.info("Appointment booked (paid): %s", appointment.id)
        return BookingConfirmation.model_validate(appointment)

    # ---------------------------------------------------------------- release
    def release_booking(self, hold_id) -> None:
        """Release a held seat when the patient abandons checkout (best-effort)."""
        hold = self._holds.get(hold_id)
        if hold is None or hold.status != HoldStatus.HELD:
            return
        payment = self._payments.get_by_hold(hold.id)
        self._release_hold(hold, payment, HoldStatus.CANCELLED, "abandoned by patient")
        self._db.commit()
        logger.info("Hold released by patient: %s", hold.id)

    def expire_stale_holds(self) -> int:
        """Release every HELD hold whose deadline has passed. Runs on a timer."""
        now = datetime.now(UTC)
        stale = self._holds.list_stale(now)
        for hold in stale:
            payment = self._payments.get_by_hold(hold.id)
            self._release_hold(hold, payment, HoldStatus.EXPIRED, "expired")
        if stale:
            self._db.commit()
            logger.info("Expired %d stale hold(s)", len(stale))
        return len(stale)

    # ------------------------------------------------------------ voice agent
    def start_agent_booking(
        self, doctor: Doctor, data: AgentBookingRequest, request: Request | None = None
    ) -> AgentBookingResult:
        """Channel-agnostic booking orchestration for the voice agent.

        Three outcomes: a review link (draft, no seat reserved), an instant
        confirmation (free clinic), or a payment link + 10-min seat hold. All of
        it flows through the same primitives the website uses.
        """
        if doctor.status != DoctorStatus.ACTIVE:
            raise ApiException(403, "This doctor is not accepting bookings", "DOCTOR_INACTIVE")

        settings_row = self._settings.get_for_doctor(doctor.id)
        if settings_row is not None and not settings_row.booking_enabled:
            raise ApiException(403, "Online booking is currently disabled", "BOOKING_DISABLED")

        slot = self._slots.get_for_doctor(doctor.id, data.slot_id)
        if slot is None:
            raise ApiException(404, "Slot not found", "NOT_FOUND")
        if slot.clinic_id != data.clinic_id:
            raise ApiException(400, "Slot does not belong to that clinic", "VALIDATION_ERROR")

        clinic = self._clinics.get_for_doctor(doctor.id, slot.clinic_id)
        if clinic is None or clinic.status != ClinicStatus.ACTIVE:
            raise ApiException(403, "This clinic is not accepting bookings", "CLINIC_INACTIVE")

        if data.mode == "review":
            return self._create_review_session(doctor, clinic, slot, data)

        # Direct booking — reserve the seat now.
        self._assert_bookable(slot, clinic)
        patient = self._resolve_agent_patient(doctor, data)

        if self._appointments.has_active_for_slot_patient(slot.id, patient.id):
            raise ApiException(409, "This patient already has a booking for that slot", "DUPLICATE_BOOKING")
        if self._holds.has_active_for_slot_patient(slot.id, patient.id):
            raise ApiException(409, "This patient already has a pending booking", "DUPLICATE_BOOKING")

        if not self._slots.claim_capacity(slot.id):
            raise ApiException(409, "That slot is no longer available", "SLOT_FULL")

        payment_required, fee = self._resolve_payment(settings_row, clinic)

        if not payment_required:
            appointment = self._create_appointment(doctor, clinic, slot, patient, data.reason)
            self._slots.mark_full_if_reached(slot.id)
            self._activity.record(
                doctor.id, "BOOK_APPOINTMENT", "Appointment", appointment.id, request=request
            )
            self._db.commit()
            self._db.refresh(appointment)
            conf = BookingConfirmation.model_validate(appointment)
            self._notify_confirmation(patient.phone_number, doctor, conf)
            logger.info("Agent booked (free): %s", appointment.id)
            return AgentBookingResult(
                status="confirmed",
                message=(
                    f"Your appointment with {doctor.full_name} at {clinic.clinic_name} on "
                    f"{conf.appointment_date} at {conf.start_time.strftime('%H:%M')} is confirmed. "
                    f"Your token number is {conf.token_number}."
                ),
                appointment=conf,
            )

        # Paid: hold the seat and send a payment link.
        hold = AppointmentHold(
            doctor_id=doctor.id,
            clinic_id=clinic.id,
            slot_id=slot.id,
            patient_id=patient.id,
            visit_reason=data.reason,
            status=HoldStatus.HELD,
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.hold_expiry_minutes),
        )
        self._holds.add(hold)

        try:
            link = self._provider.create_payment_link(
                fee,
                settings.payment_currency,
                receipt=str(hold.id),
                description=f"Consultation with {doctor.full_name} at {clinic.clinic_name}",
                customer_name=patient.full_name,
                customer_phone=data.phone_number,
            )
        except PaymentError:
            self._db.rollback()
            logger.exception("Agent payment link creation failed for slot %s", slot.id)
            raise ApiException(
                502, "Could not start the payment. Please try again.", "PAYMENT_INIT_FAILED"
            ) from None

        payment = Payment(
            doctor_id=doctor.id,
            hold_id=hold.id,
            patient_id=patient.id,
            clinic_id=clinic.id,
            amount=fee,
            currency=settings.payment_currency,
            status=PaymentStatus.PENDING,
            provider=self._provider.name,
            provider_order_id=link.link_id,
            patient_name=patient.full_name,
            clinic_name=clinic.clinic_name,
        )
        self._payments.add(payment)
        self._activity.record(
            doctor.id, "HOLD_APPOINTMENT", "AppointmentHold", hold.id, request=request
        )
        self._notify_pay_link(data.phone_number, doctor, clinic, slot, fee, link.short_url)
        self._db.commit()
        logger.info("Agent held seat + sent pay link: hold=%s", hold.id)
        return AgentBookingResult(
            status="payment_link",
            message=(
                f"I've sent a payment link for Rs. {fee} to your phone. Please pay within "
                f"{settings.hold_expiry_minutes} minutes to confirm your appointment."
            ),
            hold_id=hold.id,
            payment_link_url=link.short_url,
            expires_in_seconds=settings.hold_expiry_minutes * 60,
        )

    def confirm_payment_link(
        self, link_id: str, payment_id: str, request: Request | None = None
    ) -> None:
        """Confirm a booking from a `payment_link.paid` webhook (correlate by link id)."""
        self._confirm_paid(
            self._payments.get_by_provider_order_id(link_id), payment_id, request
        )

    def confirm_hold_payment(
        self, hold_id: str, payment_id: str, request: Request | None = None
    ) -> None:
        """Confirm a booking from a `payment.captured` webhook (correlate by hold id)."""
        try:
            hold_uuid = uuid.UUID(hold_id)
        except (ValueError, TypeError):
            return
        self._confirm_paid(self._payments.get_by_hold(hold_uuid), payment_id, request)

    def _confirm_paid(
        self, payment: Payment | None, payment_id: str, request: Request | None
    ) -> None:
        if payment is None or payment.hold_id is None:
            return
        if payment.status == PaymentStatus.PAID:
            return  # idempotent — already handled

        hold = self._holds.get(payment.hold_id)
        if hold is None or hold.status == HoldStatus.CONFIRMED:
            return

        # If the seat was released (hold expired before payment), try to re-secure it.
        if hold.status != HoldStatus.HELD:
            if not self._slots.claim_capacity(hold.slot_id):
                payment.status = PaymentStatus.PAID
                payment.provider_payment_id = payment_id
                payment.failure_reason = "paid after hold expiry; seat unavailable"
                self._db.commit()
                logger.warning("Late payment, seat unavailable: payment=%s", payment.id)
                return
            hold.status = HoldStatus.HELD

        doctor = self._doctors.get_by_id(hold.doctor_id)
        clinic = self._clinics.get_for_doctor(hold.doctor_id, hold.clinic_id)
        slot = self._slots.get_for_doctor(hold.doctor_id, hold.slot_id)
        patient = self._patients.get_for_doctor(hold.doctor_id, hold.patient_id)
        if doctor is None or clinic is None or slot is None or patient is None:
            return

        appointment = self._create_appointment(doctor, clinic, slot, patient, hold.visit_reason)
        self._slots.mark_full_if_reached(slot.id)
        hold.status = HoldStatus.CONFIRMED
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = payment_id
        payment.appointment_id = appointment.id
        self._activity.record(
            doctor.id, "BOOK_APPOINTMENT", "Appointment", appointment.id, request=request
        )
        self._db.commit()
        self._db.refresh(appointment)
        conf = BookingConfirmation.model_validate(appointment)
        self._notify_confirmation(patient.phone_number, doctor, conf)
        logger.info("Payment-link booking confirmed: %s", appointment.id)

    def _create_review_session(
        self, doctor: Doctor, clinic: Clinic, slot: Slot, data: AgentBookingRequest
    ) -> AgentBookingResult:
        token = secrets.token_urlsafe(24)
        session = BookingSession(
            token=token,
            doctor_id=doctor.id,
            clinic_id=clinic.id,
            slot_id=slot.id,
            name=data.name,
            phone_number=data.phone_number,
            email=data.email,
            age=data.age,
            gender=data.gender,
            reason=data.reason,
            clinic_name=clinic.clinic_name,
            slot_date=slot.slot_date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            status=BookingSessionStatus.DRAFT,
            source="VOICE_AGENT",
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.review_session_expiry_minutes),
        )
        self._sessions.add(session)
        review_url = self._site_url(doctor, f"/book?session={token}")
        self._notify_review_link(data.phone_number, doctor, clinic, slot, review_url)
        self._db.commit()
        logger.info("Agent created review session: %s", session.id)
        return AgentBookingResult(
            status="review",
            message=(
                "I've sent you a link to review and confirm your appointment. "
                "Open it to check the details and complete the booking."
            ),
            review_url=review_url,
            expires_in_seconds=settings.review_session_expiry_minutes * 60,
        )

    def _resolve_agent_patient(self, doctor: Doctor, data: AgentBookingRequest) -> Patient:
        if data.account_member_id is not None:
            patient = self._patients.get_for_doctor(doctor.id, data.account_member_id)
            if patient is None:
                raise ApiException(404, "The selected profile was not found", "MEMBER_NOT_FOUND")
            return patient
        return self._match_or_create_patient(doctor, data)

    def _site_url(self, doctor: Doctor, path: str) -> str:
        base = (doctor.website_url or "").rstrip("/")
        return f"{base}{path}" if base else path

    # --- notification message builders ---------------------------------------
    def _send(self, phone: str, message: str) -> None:
        """Send a notification best-effort — a delivery failure never breaks booking."""
        try:
            self._notifier.send(phone, message)
        except Exception:
            logger.exception("Notification delivery failed for %s", phone)

    def _notify_confirmation(
        self, phone: str, doctor: Doctor, conf: BookingConfirmation
    ) -> None:
        self._send(
            phone,
            (
                f"🎉 *Appointment Confirmed!*\n\n"
                f"Your appointment with *{doctor.full_name}* has been confirmed.\n\n"
                f"🏥 Clinic: {conf.clinic_name}\n"
                f"📅 Date: {conf.appointment_date}\n"
                f"🕒 Time: {conf.start_time.strftime('%I:%M %p')}\n"
                f"🎟️ Token Number: {conf.token_number}\n"
                f"🆔 Appointment ID: {conf.appointment_number}\n\n"
                f"Please arrive 10–15 minutes before your scheduled appointment time.\n"
                f"Thank you, and we wish you good health! 😊"
            ),
        )

    def _notify_pay_link(
        self, phone: str, doctor: Doctor, clinic: Clinic, slot: Slot, fee, url: str
    ) -> None:
        self._send(
            phone,
            (
                f"Hello! 😊\n\n"
                f"Your appointment has been reserved with *{doctor.full_name}*.\n\n"
                f"🏥 Clinic: {clinic.clinic_name}\n"
                f"📅 Date: {slot.slot_date}\n"
                f"🕒 Time: {slot.start_time.strftime('%I:%M %p')}\n"
                f"💰 Consultation Fee: ₹{fee}\n\n"
                f"To *confirm your appointment*, please complete the payment within "
                f"{settings.hold_expiry_minutes} minutes.\n\n"
                f"💳 Payment Link:\n{url}\n\n"
                f"✅ Once your payment is successful, your appointment will be confirmed automatically.\n\n"
                f"Thank you! We look forward to seeing you."
            ),
        )

    def _notify_review_link(
        self, phone: str, doctor: Doctor, clinic: Clinic, slot: Slot, url: str
    ) -> None:
        self._send(
            phone,
            (
                f"Review your appointment with {doctor.full_name} at {clinic.clinic_name} on "
                f"{slot.slot_date} at {slot.start_time.strftime('%H:%M')} and confirm here:\n{url}"
            ),
        )

    # ------------------------------------------------------------------ internals
    def _release_hold(
        self,
        hold: AppointmentHold,
        payment: Payment | None,
        status: HoldStatus,
        reason: str,
    ) -> None:
        self._slots.release_capacity(hold.slot_id)
        hold.status = status
        if payment is not None and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = reason

    def _resolve_payment(self, settings_row, clinic: Clinic) -> tuple[bool, Decimal]:
        """Whether this booking needs payment, and for how much.

        Payment is required only when the doctor has opted in AND the clinic has a
        positive consultation fee; a missing/zero fee is treated as a free booking.
        """
        required = settings_row is not None and settings_row.payment_required
        fee = clinic.consultation_fee or Decimal("0")
        if not required or fee <= 0:
            return False, Decimal("0")
        return True, fee

    def _assert_bookable(self, slot: Slot, clinic: Clinic) -> None:
        try:
            now = datetime.now(ZoneInfo(clinic.timezone))
        except Exception:
            now = datetime.now(ZoneInfo("Asia/Kolkata"))

        slot_start = datetime.combine(slot.slot_date, slot.start_time, tzinfo=now.tzinfo)
        if slot_start <= now:
            raise ApiException(409, "This slot is in the past", "SLOT_UNAVAILABLE")
        if slot.status == SlotStatus.FULL or slot.booked_count >= slot.capacity:
            raise ApiException(409, "This slot is fully booked", "SLOT_FULL")
        if slot.status != SlotStatus.AVAILABLE:
            raise ApiException(409, "This slot is not available", "SLOT_UNAVAILABLE")

    def _resolve_patient(
        self, doctor: Doctor, data: BookingRequest, account: PatientAccount | None
    ) -> Patient:
        # Only a session belonging to THIS doctor counts; a cookie for another
        # doctor is ignored so the patient can still book here as a guest.
        account_here = account if account is not None and account.doctor_id == doctor.id else None

        if data.account_member_id is not None:
            # Explicit booking for a saved profile requires a matching session.
            if account is None:
                raise ApiException(401, "Please sign in to book for a saved profile", "UNAUTHORIZED")
            if account_here is None:
                raise ApiException(403, "This account cannot book with this doctor", "ACCOUNT_MISMATCH")
            patient = self._patients.get_for_account(account_here.id, data.account_member_id)
            if patient is None:
                raise ApiException(404, "The selected profile was not found", "MEMBER_NOT_FOUND")
            return patient

        if account_here is not None:
            # Manual entry: the account holder typed a one-off person's details.
            if data.name.strip() and data.phone_number.strip():
                return self._resolve_manual_patient(account_here, doctor, data)
            # Otherwise the booking is for the account holder themselves.
            self_patient = self._patients.get_self_for_account(account_here.id)
            if self_patient is None:
                raise ApiException(400, "Complete your profile before booking", "PROFILE_INCOMPLETE")
            return self_patient

        # Guest booking — identity comes from the form.
        if not data.name.strip() or not data.phone_number.strip():
            raise ApiException(400, "Name and phone number are required", "VALIDATION_ERROR")
        return self._match_or_create_patient(doctor, data)

    def _resolve_manual_patient(
        self, account: PatientAccount, doctor: Doctor, data: BookingRequest
    ) -> Patient:
        """A logged-in patient booking for a manually-entered ("someone else") person."""
        # Save-for-next-time → a new family member (exempt from the primary-phone
        # rule, so it can even share the account phone).
        phone = normalize_phone(data.phone_number)
        if data.save_as_member:
            member = Patient(
                doctor_id=doctor.id,
                account_id=account.id,
                relationship=data.relationship or PatientRelationship.OTHER,
                patient_code=self._patients.next_patient_code(doctor.id),
                full_name=data.name,
                phone_number=phone or account.phone_number,
                email=data.email,
                age=data.age,
                gender=data.gender,
            )
            self._patients.add(member)
            return member

        # One-off: match/create the primary patient for this phone and link it to
        # the booker's account so it shows in their history — but never re-home a
        # record that already belongs to a different account.
        existing = self._patients.get_by_phone(doctor.id, phone)
        if existing is not None:
            if existing.account_id in (None, account.id):
                existing.account_id = account.id
                # Only refresh a plain one-off/guest record, never a SELF profile.
                if existing.relationship is None:
                    existing.full_name = data.name
                    if data.email:
                        existing.email = data.email
                    if data.age is not None:
                        existing.age = data.age
                    if data.gender is not None:
                        existing.gender = data.gender
                self._db.flush()
            return existing

        patient = Patient(
            doctor_id=doctor.id,
            account_id=account.id,
            patient_code=self._patients.next_patient_code(doctor.id),
            full_name=data.name,
            phone_number=phone,
            email=data.email,
            age=data.age,
            gender=data.gender,
        )
        try:
            self._patients.add(patient)
        except IntegrityError:
            # Concurrent booking created the same primary — reuse it.
            self._db.rollback()
            existing = self._patients.get_by_phone(doctor.id, phone)
            if existing is None:
                raise
            return existing
        return patient

    def _match_or_create_patient(self, doctor: Doctor, data: BookingRequest) -> Patient:
        # Canonicalise the phone so the same person always maps to one record,
        # regardless of how they typed it (matches patient-auth normalization).
        phone = normalize_phone(data.phone_number)
        existing = self._patients.get_by_phone(doctor.id, phone)
        if existing is not None:
            # Refresh details from the latest booking.
            existing.full_name = data.name
            if data.email:
                existing.email = data.email
            if data.age is not None:
                existing.age = data.age
            if data.gender is not None:
                existing.gender = data.gender
            self._db.flush()
            return existing

        patient = Patient(
            doctor_id=doctor.id,
            patient_code=self._patients.next_patient_code(doctor.id),
            full_name=data.name,
            phone_number=phone,
            email=data.email,
            age=data.age,
            gender=data.gender,
        )
        try:
            self._patients.add(patient)
        except IntegrityError:
            # Concurrent booking created the same patient first — reuse it.
            self._db.rollback()
            existing = self._patients.get_by_phone(doctor.id, phone)
            if existing is None:
                raise
            return existing
        return patient

    def _create_appointment(
        self,
        doctor: Doctor,
        clinic: Clinic,
        slot: Slot,
        patient: Patient,
        reason: str | None,
    ) -> Appointment:
        # `token_number` (MAX+1 per clinic-day) and `appointment_number` (random)
        # both carry unique constraints. Under concurrency two bookings can pick
        # the same value; the DB rejects the loser, so recompute and retry inside
        # a SAVEPOINT to avoid tearing down the whole booking transaction.
        last_error: IntegrityError | None = None
        for _ in range(5):
            appointment = Appointment(
                doctor_id=doctor.id,
                clinic_id=clinic.id,
                patient_id=patient.id,
                slot_id=slot.id,
                appointment_number=self._unique_appointment_number(),
                token_number=self._appointments.next_token_number(clinic.id, slot.slot_date),
                appointment_status=AppointmentStatus.CONFIRMED,
                booking_source=BookingSource.WEBSITE,
                visit_reason=reason,
                doctor_name=doctor.full_name,
                clinic_name=clinic.clinic_name,
                clinic_address=compose_clinic_address(clinic),
                consultation_fee=clinic.consultation_fee,
                appointment_date=slot.slot_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )
            try:
                with self._db.begin_nested():
                    self._appointments.add(appointment)
                return appointment
            except IntegrityError as exc:
                last_error = exc
        raise ApiException(
            500, "Could not allocate an appointment. Please try again.", "INTERNAL_ERROR"
        ) from last_error

    def _unique_appointment_number(self) -> str:
        for _ in range(10):
            number = _generate_appointment_number()
            if not self._appointments.exists_number(number):
                return number
        raise ApiException(500, "Could not allocate an appointment number", "INTERNAL_ERROR")
