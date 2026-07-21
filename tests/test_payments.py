import uuid
import datetime as _dt
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ApiException
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_hold import AppointmentHold, HoldStatus
from app.models.availability_rule import AvailabilityRule
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.doctor_settings import DoctorSettings
from app.models.patient import Patient
from app.models.payment import Payment, PaymentStatus
from app.models.slot import Slot
from app.schemas.booking import BookingRequest, ConfirmPaymentRequest
from app.services.booking_service import BookingService
from app.services.payments.base import PaymentOrder
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"


class FakeProvider:
    """In-memory gateway so the paid flow can be tested without Razorpay."""

    name = "fake"

    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid

    def create_order(self, amount, currency, receipt) -> PaymentOrder:
        return PaymentOrder(
            order_id=f"order_{uuid.uuid4().hex[:10]}",
            amount=int(amount * 100),
            currency=currency,
        )

    def verify_payment(self, order_id, payment_id, signature) -> bool:
        return self.valid

    def refund_payment(self, payment_id, amount=None) -> str:
        return f"rfnd_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def paid_context() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-pay-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Paid Doctor",
            slug=slug,
            email=f"pay-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        "/api/v1/auth/login", json={"email": f"pay-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        "/api/v1/clinics",
        headers=headers,
        json={
            "clinic_name": "Pay Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
            "consultation_fee": "500.00",
        },
    ).json()["data"]["id"]

    # Require advance payment for this doctor.
    client.patch("/api/v1/settings", headers=headers, json={"payment_required": True})

    client.post(
        "/api/v1/availability",
        headers=headers,
        json={
            "clinic_id": clinic_id,
            "weekday": "MONDAY",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 2,
            "effective_from": "2026-01-01",
        },
    )
    _all_slots = client.get(f"/api/v1/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    yield {"slug": slug, "clinic_id": clinic_id, "slots": slots, "headers": headers}

    with SessionLocal() as db:
        for model in (Payment, AppointmentHold, Appointment, Patient, Slot, AvailabilityRule,
                      ActivityLog, DoctorSettings, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _request(context: dict, slot_id: str, phone: str = "+91-8000000301") -> BookingRequest:
    return BookingRequest(
        doctor_slug=context["slug"],
        slot_id=uuid.UUID(slot_id),
        name="Paying Patient",
        phone_number=phone,
    )


def _slot(slot_id: str) -> Slot:
    with SessionLocal() as db:
        return db.get(Slot, uuid.UUID(slot_id))


def test_payment_required_holds_seat(paid_context: dict) -> None:
    slot_id = paid_context["slots"][0]["id"]
    with SessionLocal() as db:
        result = BookingService(db, provider=FakeProvider()).start_booking(
            _request(paid_context, slot_id)
        )

    assert result.status == "payment_required"
    assert result.hold_id is not None
    assert result.payment is not None
    assert result.payment.amount == 50000  # 500.00 -> paise
    assert result.payment.display_amount == pytest.approx(500)
    # The seat is held: booked_count is claimed even before payment.
    assert _slot(slot_id).booked_count == 1


def test_successful_payment_confirms_appointment(paid_context: dict) -> None:
    slot_id = paid_context["slots"][0]["id"]
    provider = FakeProvider(valid=True)
    with SessionLocal() as db:
        service = BookingService(db, provider=provider)
        started = service.start_booking(_request(paid_context, slot_id))
        payment = service._payments.get_by_hold(started.hold_id)
        order_id = payment.provider_order_id

    with SessionLocal() as db:
        confirmation = BookingService(db, provider=provider).confirm_booking(
            started.hold_id,
            ConfirmPaymentRequest(order_id=order_id, payment_id="pay_123", signature="sig_ok"),
        )

    assert confirmation.appointment_status == AppointmentStatus.CONFIRMED

    with SessionLocal() as db:
        hold = db.get(AppointmentHold, started.hold_id)
        pay = db.query(Payment).filter(Payment.hold_id == started.hold_id).one()
        assert hold.status == HoldStatus.CONFIRMED
        assert pay.status == PaymentStatus.PAID
        assert pay.provider_payment_id == "pay_123"
        assert pay.appointment_id is not None
        assert db.get(Slot, uuid.UUID(slot_id)).booked_count == 1


def test_failed_verification_releases_seat(paid_context: dict) -> None:
    slot_id = paid_context["slots"][0]["id"]
    with SessionLocal() as db:
        service = BookingService(db, provider=FakeProvider(valid=True))
        started = service.start_booking(_request(paid_context, slot_id))
        order_id = service._payments.get_by_hold(started.hold_id).provider_order_id

    with SessionLocal() as db:
        service = BookingService(db, provider=FakeProvider(valid=False))
        with pytest.raises(ApiException) as exc:
            service.confirm_booking(
                started.hold_id,
                ConfirmPaymentRequest(order_id=order_id, payment_id="pay_x", signature="bad"),
            )
        assert exc.value.status_code == 402

    with SessionLocal() as db:
        hold = db.get(AppointmentHold, started.hold_id)
        pay = db.query(Payment).filter(Payment.hold_id == started.hold_id).one()
        assert hold.status == HoldStatus.EXPIRED
        assert pay.status == PaymentStatus.FAILED
        # Seat is freed for someone else.
        assert db.get(Slot, uuid.UUID(slot_id)).booked_count == 0


def test_expiry_sweep_releases_stale_hold(paid_context: dict) -> None:
    slot_id = paid_context["slots"][0]["id"]
    with SessionLocal() as db:
        started = BookingService(db, provider=FakeProvider()).start_booking(
            _request(paid_context, slot_id)
        )

    # Force the hold past its deadline, then run the sweep.
    with SessionLocal() as db:
        hold = db.get(AppointmentHold, started.hold_id)
        hold.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    with SessionLocal() as db:
        released = BookingService(db, provider=FakeProvider()).expire_stale_holds()
        assert released >= 1

    with SessionLocal() as db:
        assert db.get(AppointmentHold, started.hold_id).status == HoldStatus.EXPIRED
        assert db.get(Slot, uuid.UUID(slot_id)).booked_count == 0
