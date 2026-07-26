import uuid
import datetime as _dt
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.appointment import Appointment
from app.models.appointment_hold import AppointmentHold
from app.models.availability_rule import AvailabilityRule
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.otp_challenge import OtpChallenge
from app.models.patient import Patient
from app.models.patient_account import PatientAccount
from app.models.payment import Payment
from app.models.slot import Slot
from main import app

client = TestClient(app)

PASSWORD = "test-password-123"
API = "/api/v1"


@pytest.fixture
def ctx() -> Generator[dict, None, None]:
    unique = uuid.uuid4().hex[:10]
    slug = f"dr-pa-{unique}"
    with SessionLocal() as db:
        doctor = Doctor(
            full_name="Account Doctor",
            slug=slug,
            email=f"pa-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9999999999",
            specialization="Testing",
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        doctor_id = doctor.id

    token = client.post(
        f"{API}/auth/login", json={"email": f"pa-{unique}@example.com", "password": PASSWORD}
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    clinic_id = client.post(
        f"{API}/clinics",
        headers=headers,
        json={
            "clinic_name": "PA Clinic",
            "address_line_1": "1 St",
            "city": "Pune",
            "state": "MH",
            "consultation_fee": "0.00",
        },
    ).json()["data"]["id"]

    client.post(
        f"{API}/availability",
        headers=headers,
        json={
            "clinic_id": clinic_id,
            "weekday": "MONDAY",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 3,
            "effective_from": "2026-01-01",
        },
    )
    _all_slots = client.get(f"{API}/slots?clinic_id={clinic_id}", headers=headers).json()["data"]["items"]
    slots = [s for s in _all_slots if s["slot_date"] > _dt.date.today().isoformat()]
    yield {"slug": slug, "clinic_id": clinic_id, "slots": slots, "doctor_id": doctor_id}

    with SessionLocal() as db:
        for model in (Payment, AppointmentHold, Appointment, Patient):
            db.query(model).filter(model.doctor_id == doctor_id).delete()
        db.query(OtpChallenge).filter(OtpChallenge.doctor_id == doctor_id).delete()
        db.query(PatientAccount).filter(PatientAccount.doctor_id == doctor_id).delete()
        db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_id).delete()
        db.query(AvailabilityRule).filter(AvailabilityRule.doctor_id == doctor_id).delete()
        db.query(Slot).filter(Slot.doctor_id == doctor_id).delete()
        db.query(Clinic).filter(Clinic.doctor_id == doctor_id).delete()
        db.delete(db.get(Doctor, doctor_id))
        db.commit()


def _request_otp(slug: str, phone: str) -> str:
    resp = client.post(f"{API}/patient-auth/request-otp", json={"doctor_slug": slug, "phone_number": phone})
    assert resp.status_code == 200
    code = resp.json()["data"]["debug_code"]
    assert code is not None  # development returns the code for testing
    return code


def _verify(slug: str, phone: str, code: str) -> dict:
    resp = client.post(
        f"{API}/patient-auth/verify-otp",
        json={"doctor_slug": slug, "phone_number": phone, "code": code},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_via_otp_then_complete_profile(ctx: dict) -> None:
    phone = "+91-9100000001"
    code = _request_otp(ctx["slug"], phone)
    data = _verify(ctx["slug"], phone, code)

    assert data["is_new"] is True
    assert data["account"]["profile_complete"] is False
    assert data["profile"] is None
    token = data["token"]

    # Complete the profile — creates the SELF patient.
    profile = client.put(
        f"{API}/patient-account/profile",
        headers=_auth(token),
        json={"full_name": "Asha Rao", "gender": "FEMALE", "date_of_birth": "1990-05-20"},
    )
    assert profile.status_code == 200, profile.text
    body = profile.json()["data"]
    assert body["full_name"] == "Asha Rao"
    assert body["relationship"] == "SELF"
    assert body["date_of_birth"] == "1990-05-20"
    assert body["age"] is not None and body["age"] >= 33  # derived from DOB

    me = client.get(f"{API}/patient-auth/me", headers=_auth(token)).json()["data"]
    assert me["account"]["profile_complete"] is True
    assert me["profile"]["full_name"] == "Asha Rao"


def test_wrong_otp_rejected(ctx: dict) -> None:
    phone = "+91-9100000002"
    code = _request_otp(ctx["slug"], phone)
    wrong = "111111" if code != "111111" else "222222"
    resp = client.post(
        f"{API}/patient-auth/verify-otp",
        json={"doctor_slug": ctx["slug"], "phone_number": phone, "code": wrong},
    )
    # A wrong code is rejected.
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "OTP_INVALID"


def test_returning_user_and_password_login(ctx: dict) -> None:
    phone = "+91-9100000003"
    data = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))
    token = data["token"]
    client.put(
        f"{API}/patient-account/profile",
        headers=_auth(token),
        json={"full_name": "Ravi Kumar"},
    )

    # Log in again via OTP — existing account, profile already complete.
    again = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))
    assert again["is_new"] is False
    assert again["account"]["profile_complete"] is True

    # Set a password, then log in with it.
    assert (
        client.post(
            f"{API}/patient-auth/set-password", headers=_auth(token), json={"password": "s3cretpass"}
        ).status_code
        == 200
    )
    login = client.post(
        f"{API}/patient-auth/login",
        json={"doctor_slug": ctx["slug"], "phone_number": phone, "password": "s3cretpass"},
    )
    assert login.status_code == 200
    assert login.json()["data"]["account"]["has_password"] is True

    bad = client.post(
        f"{API}/patient-auth/login",
        json={"doctor_slug": ctx["slug"], "phone_number": phone, "password": "wrong"},
    )
    assert bad.status_code == 401


def test_family_members_crud(ctx: dict) -> None:
    phone = "+91-9100000004"
    token = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))["token"]
    client.put(f"{API}/patient-account/profile", headers=_auth(token), json={"full_name": "Head Account"})

    add = client.post(
        f"{API}/patient-account/members",
        headers=_auth(token),
        json={"full_name": "Grandpa", "relationship": "FATHER", "age": 70},
    )
    assert add.status_code == 201, add.text
    member = add.json()["data"]
    assert member["relationship"] == "FATHER"
    # No own phone given → inherits the account's (normalized) phone.
    assert member["phone_number"] == "9100000004"

    members = client.get(f"{API}/patient-account/members", headers=_auth(token)).json()["data"]
    assert len(members) == 1

    upd = client.patch(
        f"{API}/patient-account/members/{member['id']}",
        headers=_auth(token),
        json={"full_name": "Grandfather"},
    )
    assert upd.json()["data"]["full_name"] == "Grandfather"

    # Cannot promote a member to SELF.
    bad = client.patch(
        f"{API}/patient-account/members/{member['id']}",
        headers=_auth(token),
        json={"relationship": "SELF"},
    )
    assert bad.status_code == 400

    delete = client.delete(f"{API}/patient-account/members/{member['id']}", headers=_auth(token))
    assert delete.status_code == 200
    assert client.get(f"{API}/patient-account/members", headers=_auth(token)).json()["data"] == []


def test_logged_in_booking_for_self_and_member(ctx: dict) -> None:
    phone = "+91-9100000005"
    token = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))["token"]
    client.put(
        f"{API}/patient-account/profile",
        headers=_auth(token),
        json={"full_name": "Meera", "gender": "FEMALE"},
    )
    son = client.post(
        f"{API}/patient-account/members",
        headers=_auth(token),
        json={"full_name": "Little Meer", "relationship": "SON", "age": 6},
    ).json()["data"]

    slots = ctx["slots"]
    # Book for self.
    r1 = client.post(
        f"{API}/public/bookings",
        headers=_auth(token),
        json={"doctor_slug": ctx["slug"], "slot_id": slots[0]["id"]},
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["data"]["status"] == "confirmed"

    # Book for the son in the same slot — distinct patient, so allowed.
    r2 = client.post(
        f"{API}/public/bookings",
        headers=_auth(token),
        json={"doctor_slug": ctx["slug"], "slot_id": slots[0]["id"], "account_member_id": son["id"]},
    )
    assert r2.status_code == 201, r2.text

    appts = client.get(f"{API}/patient-account/appointments", headers=_auth(token)).json()["data"]
    assert len(appts) == 2
    names = {a["patient_name"] for a in appts}
    assert names == {"Meera", "Little Meer"}
    assert len({a["patient_id"] for a in appts}) == 2  # two distinct patient records


def test_guest_booking_still_works(ctx: dict) -> None:
    # A separate client with no patient session — pure guest path.
    guest = TestClient(app)
    slot = ctx["slots"][1]
    resp = guest.post(
        f"{API}/public/bookings",
        json={
            "doctor_slug": ctx["slug"],
            "slot_id": slot["id"],
            "name": "Walk In",
            "phone_number": "+91-8123456789",
            "age": 40,
            "gender": "MALE",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["status"] == "confirmed"


def test_guest_booking_ignores_foreign_doctor_session(ctx: dict) -> None:
    # Patient is signed in with doctor A (ctx)...
    phone = "+91-9100000007"
    token = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))["token"]
    client.put(f"{API}/patient-account/profile", headers=_auth(token), json={"full_name": "Traveler"})

    # ...but books as a GUEST on a different doctor B. The doctor-A cookie/token
    # must be ignored, not rejected.
    unique = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        doctor_b = Doctor(
            full_name="Other Doctor",
            slug=f"dr-other-{unique}",
            email=f"other-{unique}@example.com",
            password_hash=hash_password(PASSWORD),
            phone_number="+91-9888888888",
            specialization="Testing",
        )
        db.add(doctor_b)
        db.commit()
        db.refresh(doctor_b)
        doctor_b_id = doctor_b.id
        slug_b = doctor_b.slug

    b_headers = {
        "Authorization": "Bearer "
        + client.post(
            f"{API}/auth/login", json={"email": f"other-{unique}@example.com", "password": PASSWORD}
        ).json()["data"]["token"]
    }
    clinic_b = client.post(
        f"{API}/clinics",
        headers=b_headers,
        json={"clinic_name": "B Clinic", "address_line_1": "2 St", "city": "Pune", "state": "MH"},
    ).json()["data"]["id"]
    client.post(
        f"{API}/availability",
        headers=b_headers,
        json={
            "clinic_id": clinic_b,
            "weekday": "TUESDAY",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
            "patients_per_slot": 2,
            "effective_from": "2026-01-01",
        },
    )
    slot_b = client.get(f"{API}/slots?clinic_id={clinic_b}", headers=b_headers).json()["data"]["items"][0]

    try:
        resp = client.post(
            f"{API}/public/bookings",
            headers=_auth(token),  # doctor-A patient token
            json={
                "doctor_slug": slug_b,
                "slot_id": slot_b["id"],
                "name": "Guest On B",
                "phone_number": "+91-8222222222",
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["status"] == "confirmed"
    finally:
        with SessionLocal() as db:
            for model in (Appointment, Patient):
                db.query(model).filter(model.doctor_id == doctor_b_id).delete()
            db.query(ActivityLog).filter(ActivityLog.doctor_id == doctor_b_id).delete()
            db.query(AvailabilityRule).filter(AvailabilityRule.doctor_id == doctor_b_id).delete()
            db.query(Slot).filter(Slot.doctor_id == doctor_b_id).delete()
            db.query(Clinic).filter(Clinic.doctor_id == doctor_b_id).delete()
            db.delete(db.get(Doctor, doctor_b_id))
            db.commit()


def test_manual_one_off_booking_linked_to_account(ctx: dict) -> None:
    phone = "+91-9100000008"
    token = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))["token"]
    client.put(f"{API}/patient-account/profile", headers=_auth(token), json={"full_name": "Booker"})

    # Logged in, but type a one-off person's details (no member id, no save).
    resp = client.post(
        f"{API}/public/bookings",
        headers=_auth(token),
        json={
            "doctor_slug": ctx["slug"],
            "slot_id": ctx["slots"][0]["id"],
            "name": "Friend Onceoff",
            "phone_number": "+91-8300000001",
            "age": 25,
        },
    )
    assert resp.status_code == 201, resp.text

    # It appears in the booker's history (linked)...
    appts = client.get(f"{API}/patient-account/appointments", headers=_auth(token)).json()["data"]
    assert any(a["patient_name"] == "Friend Onceoff" for a in appts)
    # ...but was NOT saved to the family members list.
    members = client.get(f"{API}/patient-account/members", headers=_auth(token)).json()["data"]
    assert all(m["full_name"] != "Friend Onceoff" for m in members)


def test_manual_booking_save_as_member(ctx: dict) -> None:
    phone = "+91-9100000009"
    token = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))["token"]
    client.put(f"{API}/patient-account/profile", headers=_auth(token), json={"full_name": "Saver"})

    resp = client.post(
        f"{API}/public/bookings",
        headers=_auth(token),
        json={
            "doctor_slug": ctx["slug"],
            "slot_id": ctx["slots"][1]["id"],
            "name": "Cousin Keep",
            "phone_number": "+91-8300000002",
            "age": 22,
            "save_as_member": True,
            "relationship": "BROTHER",
        },
    )
    assert resp.status_code == 201, resp.text

    members = client.get(f"{API}/patient-account/members", headers=_auth(token)).json()["data"]
    assert any(
        m["full_name"] == "Cousin Keep" and m["relationship"] == "BROTHER" for m in members
    )
    appts = client.get(f"{API}/patient-account/appointments", headers=_auth(token)).json()["data"]
    assert any(a["patient_name"] == "Cousin Keep" for a in appts)


def test_booking_member_requires_ownership(ctx: dict) -> None:
    phone = "+91-9100000006"
    token = _verify(ctx["slug"], phone, _request_otp(ctx["slug"], phone))["token"]
    client.put(f"{API}/patient-account/profile", headers=_auth(token), json={"full_name": "Owner"})

    # A random member id that isn't on this account is rejected.
    resp = client.post(
        f"{API}/public/bookings",
        headers=_auth(token),
        json={
            "doctor_slug": ctx["slug"],
            "slot_id": ctx["slots"][2]["id"],
            "account_member_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "MEMBER_NOT_FOUND"
