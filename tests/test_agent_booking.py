import uuid
import datetime as _dt
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_hold import AppointmentHold, HoldStatus
from app.models.availability_rule import AvailabilityRule
from app.models.booking_session import BookingSession
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.doctor_settings import DoctorSettings
from app.models.patient import Patient
from app.models.payment import Payment, PaymentStatus
from app.models.slot import Slot
from app.schemas.agent import AgentBookingRequest
from app.services.booking_service import BookingService
from app.services.payments.base import PaymentLink, PaymentWebhookEvent
from app.api.webhooks import get_webhook_provider
from main import app

client = TestClient(app)
PASSWORD = "test-password-123"
API = "/api/v1"
AGENT_KEY = None  # set per fixture


class FakeProvider:
    name = "fake"

    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid

    def create_order(self, amount, currency, receipt):
        raise NotImplementedError

    def verify_payment(self, order_id, payment_id, signature) -> bool:
        return self.valid

    def create_payment_link(self, amount, currency, *, receipt, description, customer_name, customer_phone, expire_by_epoch=None) -> PaymentLink:
        return PaymentLink(link_id=f"plink_{uuid.uuid4().hex[:10]}", short_url="https://pay.test/abc")

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        return self.valid

    def parse_webhook(self, payload: dict) -> PaymentWebhookEvent:
        paid = {"payment.captured", "payment_link.paid", "order.paid"}
        return PaymentWebhookEvent(
            kind="paid" if payload.get("event") in paid else "other",
            payment_id=payload.get("payment_id"),
            hold_id=payload.get("hold_id"),
            link_id=payload.get("link_id"),
        )

    def refund_payment(self, payment_id, amount=None) -> str:
        return "rfnd_x"


def _make_clinic(
    headers: dict, name: str, fee: str, start: str = "09:00:00", end: str = "10:00:00"
) -> tuple[str, list[dict]]:
    clinic_id = client.post(
        f"{API}/clinics",
        headers=headers,
        json={"clinic_name": name, "address_line_1": "1 St", "city": "Pune", "state": "MH", "consultation_fee": fee},
    ).json()["data"]["id"]
    client.post(
        f"{API}/availability",
        headers=headers,
        json={"clinic_id": clinic_id, "weekday": "MONDAY", "start_time": start, "end_time": end,
              "slot_duration_minutes": 30, "patients_per_slot": 2, "effective_from": "2026-01-01"},
    )
    _all_slots = client.get(f"{API}/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    return clinic_id, slots


@pytest.fixture
def ctx() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-agent-{unique}"
    key = "agt_test_" + unique
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Agent Doctor", slug=slug, email=f"agent-{unique}@example.com",
            password_hash=hash_password(PASSWORD), phone_number="+91-9999999999",
            specialization="Testing", agent_api_key=key, website_url="http://site.test",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        f"{API}/auth/login", json={"email": f"agent-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    free_clinic, free_slots = _make_clinic(headers, "Free Clinic", "0.00", "09:00:00", "10:00:00")
    paid_clinic, paid_slots = _make_clinic(headers, "Paid Clinic", "500.00", "11:00:00", "12:00:00")

    yield {
        "slug": slug, "doctor_id": doctor_id, "agent": {"X-Agent-Key": key}, "admin": headers,
        "free_clinic": free_clinic, "free_slots": free_slots,
        "paid_clinic": paid_clinic, "paid_slots": paid_slots,
    }

    with SessionLocal() as db:
        for model in (BookingSession, Payment, AppointmentHold, Appointment, Patient, Slot,
                      AvailabilityRule, ActivityLog, DoctorSettings, Clinic):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def test_agent_auth_required(ctx: dict) -> None:
    assert client.get(f"{API}/agent/clinics").status_code == 401
    assert client.get(f"{API}/agent/clinics", headers={"X-Agent-Key": "bogus"}).status_code == 401


def test_agent_clinics_and_availability(ctx: dict) -> None:
    clinics = client.get(f"{API}/agent/clinics", headers=ctx["agent"]).json()["data"]
    assert len(clinics) == 2
    fees = {c["clinic_name"]: c["consultation_fee"] for c in clinics}
    assert fees["Paid Clinic"] == "500.00"

    slot = ctx["free_slots"][0]
    slots = client.get(
        f"{API}/agent/slots?clinic_id={ctx['free_clinic']}&slot_date={slot['slot_date']}",
        headers=ctx["agent"],
    ).json()["data"]
    assert any(s["id"] == slot["id"] for s in slots)


def test_agent_free_direct_booking_and_lookup(ctx: dict) -> None:
    phone = "+91-8700000001"
    lookup = client.post(
        f"{API}/agent/patient-lookup", headers=ctx["agent"], json={"phone_number": phone}
    ).json()["data"]
    assert lookup["found"] is False

    slot = ctx["free_slots"][-1]  # furthest-future slot (robust to the current weekday)
    resp = client.post(
        f"{API}/agent/bookings",
        headers=ctx["agent"],
        json={"clinic_id": ctx["free_clinic"], "slot_id": slot["id"], "name": "Ravi Voice",
              "phone_number": phone, "mode": "direct"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "confirmed"
    assert data["appointment"]["appointment_status"] == "CONFIRMED"

    # Now the patient is found by phone.
    again = client.post(
        f"{API}/agent/patient-lookup", headers=ctx["agent"], json={"phone_number": phone}
    ).json()["data"]
    assert again["found"] is True
    assert again["patient"]["name"] == "Ravi Voice"


def test_agent_review_session_creates_prefilled_draft(ctx: dict) -> None:
    slot = ctx["free_slots"][1]
    resp = client.post(
        f"{API}/agent/bookings",
        headers=ctx["agent"],
        json={"clinic_id": ctx["free_clinic"], "slot_id": slot["id"], "name": "Reviewer",
              "phone_number": "+91-8700000002", "age": 29, "gender": "FEMALE",
              "mode": "review", "reason": "Checkup"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "review"
    assert data["review_url"].startswith("http://site.test/book?session=")

    token = data["review_url"].split("session=")[1]
    session = client.get(f"{API}/public/booking-sessions/{token}").json()["data"]
    assert session["name"] == "Reviewer"
    assert session["age"] == 29
    assert session["slot_id"] == slot["id"]
    assert session["clinic_name"] == "Free Clinic"
    assert session["doctor_slug"] == ctx["slug"]

    # No seat was reserved by a review draft.
    with SessionLocal() as db:
        assert db.get(Slot, uuid.UUID(slot["id"])).booked_count == 0


def test_agent_paid_booking_sends_link_then_webhook_confirms(ctx: dict) -> None:
    # Require advance payment.
    client.patch(f"{API}/settings", headers=ctx["admin"], json={"payment_required": True})
    slot_id = ctx["paid_slots"][-1]["id"]

    # Paid path uses a real gateway, so drive the service directly with a fake.
    with SessionLocal() as db:
        doctor = db.get(Doctor, ctx["doctor_id"])
        result = BookingService(db, provider=FakeProvider()).start_agent_booking(
            doctor,
            AgentBookingRequest(clinic_id=uuid.UUID(ctx["paid_clinic"]), slot_id=uuid.UUID(slot_id),
                                name="Payer Voice", phone_number="+91-8700000003", mode="direct"),
        )
    assert result.status == "payment_link"
    assert result.payment_link_url == "https://pay.test/abc"

    with SessionLocal() as db:
        db.query(Payment).filter(Payment.hold_id == result.hold_id).one()
        assert db.get(Slot, uuid.UUID(slot_id)).booked_count == 1  # seat held

    # Simulate Razorpay's payment.captured webhook (hold_id rides in the notes).
    app.dependency_overrides[get_webhook_provider] = lambda: FakeProvider()
    try:
        hook = client.post(
            f"{API}/webhooks/razorpay",
            headers={"X-Razorpay-Signature": "sig"},
            json={"event": "payment.captured", "hold_id": str(result.hold_id), "payment_id": "pay_voice_1"},
        )
        assert hook.status_code == 200, hook.text
    finally:
        app.dependency_overrides.pop(get_webhook_provider, None)

    with SessionLocal() as db:
        hold = db.get(AppointmentHold, result.hold_id)
        pay = db.query(Payment).filter(Payment.hold_id == result.hold_id).one()
        assert hold.status == HoldStatus.CONFIRMED
        assert pay.status == PaymentStatus.PAID
        assert pay.appointment_id is not None
        appt = db.get(Appointment, pay.appointment_id)
        assert appt.appointment_status == AppointmentStatus.CONFIRMED
