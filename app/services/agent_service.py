import re
import uuid
from datetime import date, datetime, time, timedelta

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.clinic import Clinic, ClinicStatus
from app.models.doctor import Doctor
from app.models.patient import PatientRelationship
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.agent import (
    AgentBookingInput,
    AgentBookingRequest,
    AgentBookingResult,
    AgentClinic,
    AgentMember,
    AgentPatient,
    AgentPatientLookup,
)
from app.schemas.public import PublicSlot
from app.services.booking_service import BookingService
from app.services.public_service import PublicService
from app.utils.address import compose_clinic_address


class AgentService:
    """Read + orchestration surface exposed to a doctor's voice agent.

    Availability reuses PublicService; booking reuses BookingService. The agent
    never gets its own booking logic — this is a thin, doctor-scoped facade.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._clinics = ClinicRepository(db)
        self._patients = PatientRepository(db)
        self._public = PublicService(db)

    def list_clinics(self, doctor: Doctor) -> list[AgentClinic]:
        clinics = self._clinics.list_for_doctor(doctor.id, status=ClinicStatus.ACTIVE)
        return [
            AgentClinic(
                id=c.id,
                clinic_name=c.clinic_name,
                address=compose_clinic_address(c),
                consultation_fee=c.consultation_fee,
            )
            for c in clinics
        ]

    def available_dates(
        self,
        doctor: Doctor,
        clinic_ref: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> list[date]:
        clinic = self.resolve_clinic(doctor, clinic_ref)
        start = _parse_date(date_from, "date_from") or date.today()
        end = _parse_date(date_to, "date_to") or (start + timedelta(days=_DEFAULT_RANGE_DAYS))
        if end < start:
            raise ApiException(
                400, "date_to must be on or after date_from.", "VALIDATION_ERROR"
            )
        end = min(end, start + timedelta(days=_MAX_RANGE_DAYS))
        return self._public.list_available_dates(doctor.slug, clinic.id, start, end)

    def slots(
        self, doctor: Doctor, clinic_ref: str | None, slot_date: str | None
    ) -> list[PublicSlot]:
        clinic = self.resolve_clinic(doctor, clinic_ref)
        day = _parse_date(slot_date, "slot_date")
        if day is None:
            raise ApiException(
                400,
                "slot_date is required, in YYYY-MM-DD format. Call get_availability first "
                "to find which dates have openings.",
                "VALIDATION_ERROR",
            )
        return self._public.list_available_slots(doctor.slug, clinic.id, day)

    def resolve_clinic(self, doctor: Doctor, ref: str | None) -> Clinic:
        """Turn whatever the agent sent into a real clinic.

        Accepts a clinic id or a clinic name, and when the doctor has exactly
        one clinic, nothing at all. Anything unresolvable raises an error whose
        message lists the valid choices, so the agent can retry correctly
        instead of telling the caller there is no availability.
        """
        clinics = self._clinics.list_for_doctor(doctor.id, status=ClinicStatus.ACTIVE)
        if not clinics:
            raise ApiException(404, "This doctor has no active clinics.", "NOT_FOUND")

        ref = (ref or "").strip()
        if not ref:
            if len(clinics) == 1:
                return clinics[0]
            raise ApiException(
                400,
                "clinic_id is required. Ask the caller which clinic they want, then call "
                f"this tool again with clinic_id set to its exact id. {_choices(clinics)}",
                "CLINIC_REQUIRED",
            )

        try:
            clinic_id = uuid.UUID(ref)
        except ValueError:
            match = _match_by_name(clinics, ref)
            if match is not None:
                return match
            raise ApiException(
                400,
                f"'{ref}' is not a valid clinic id. Never invent an id — call list_clinics "
                f"and pass one of these back exactly as given. {_choices(clinics)}",
                "UNKNOWN_CLINIC",
            ) from None

        for clinic in clinics:
            if clinic.id == clinic_id:
                return clinic
        raise ApiException(
            400,
            f"No active clinic has the id '{ref}' for this doctor. {_choices(clinics)}",
            "UNKNOWN_CLINIC",
        )

    def _resolve_slot_id(
        self, doctor: Doctor, clinic: Clinic, data: AgentBookingInput
    ) -> uuid.UUID:
        """Resolve slot_id, falling back to slot_date + start_time."""
        ref = (data.slot_id or "").strip()
        if ref:
            try:
                return uuid.UUID(ref)
            except ValueError:
                pass  # fall through to date/time, then to a listing error

        day = _parse_date(data.slot_date, "slot_date")
        if day is None:
            raise ApiException(
                400,
                "slot_id is required (or slot_date + start_time). Call get_slots for the "
                "chosen date and pass back the exact id of the slot the caller picked.",
                "SLOT_REQUIRED",
            )

        open_slots = self._public.list_available_slots(doctor.slug, clinic.id, day)
        if not open_slots:
            raise ApiException(
                400,
                f"No open slots at {clinic.clinic_name} on {day.isoformat()}. Call "
                "get_availability to find dates that do have openings.",
                "NO_SLOTS",
            )

        wanted = _parse_time(data.start_time)
        if wanted is not None:
            for slot in open_slots:
                if slot.start_time == wanted:
                    return slot.id

        listing = ", ".join(s.start_time.strftime("%H:%M") for s in open_slots)
        raise ApiException(
            400,
            f"Could not match a slot on {day.isoformat()} at {clinic.clinic_name}. "
            f"Open start times are: {listing}. Confirm one with the caller and book that.",
            "UNKNOWN_SLOT",
        )

    def lookup_patient(self, doctor: Doctor, phone_number: str) -> AgentPatientLookup:
        patient = self._patients.get_by_phone(doctor.id, phone_number)
        if patient is None:
            return AgentPatientLookup(found=False)

        members: list[AgentMember] = []
        if patient.account_id is not None and patient.relationship == PatientRelationship.SELF:
            members = [
                AgentMember(
                    id=m.id,
                    name=m.full_name,
                    relationship=m.relationship,
                    age=m.age,
                    gender=m.gender,
                )
                for m in self._patients.list_members_for_account(patient.account_id)
            ]

        return AgentPatientLookup(
            found=True,
            patient=AgentPatient(
                name=patient.full_name,
                phone_number=patient.phone_number,
                age=patient.age,
                gender=patient.gender,
                email=patient.email,
            ),
            members=members,
        )

    def book(
        self, doctor: Doctor, data: AgentBookingInput, request: Request | None = None
    ) -> AgentBookingResult:
        clinic = self.resolve_clinic(doctor, data.clinic_id)
        slot_id = self._resolve_slot_id(doctor, clinic, data)

        member_id: uuid.UUID | None = None
        if data.account_member_id:
            try:
                member_id = uuid.UUID(data.account_member_id.strip())
            except ValueError:
                raise ApiException(
                    400,
                    "account_member_id must be an id returned by lookup_patient. Omit it to "
                    "book for the caller themselves.",
                    "VALIDATION_ERROR",
                ) from None

        strict = AgentBookingRequest(
            clinic_id=clinic.id,
            slot_id=slot_id,
            name=data.name,
            phone_number=data.phone_number,
            email=data.email,
            age=data.age,
            gender=data.gender,
            account_member_id=member_id,
            mode=data.mode,
            reason=data.reason,
        )
        return BookingService(self._db).start_agent_booking(doctor, strict, request=request)


_DEFAULT_RANGE_DAYS = 30
_MAX_RANGE_DAYS = 120


def _choices(clinics: list[Clinic]) -> str:
    listed = "; ".join(f"'{c.clinic_name}' (clinic_id: {c.id})" for c in clinics)
    return f"Valid clinics are: {listed}."


def _match_by_name(clinics: list[Clinic], ref: str) -> Clinic | None:
    """Match a spoken clinic name — exact first, then an unambiguous substring."""
    folded = ref.casefold()
    for clinic in clinics:
        if clinic.clinic_name.casefold() == folded:
            return clinic
    partial = [c for c in clinics if folded in c.clinic_name.casefold()]
    return partial[0] if len(partial) == 1 else None


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.casefold() == "today":
        return date.today()
    if text.casefold() == "tomorrow":
        return date.today() + timedelta(days=1)
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ApiException(
            400, f"{field} must be a date in YYYY-MM-DD format (got '{text}').", "VALIDATION_ERROR"
        ) from None


def _parse_time(value: str | None) -> time | None:
    """Accept the shapes a voice agent produces: 10:30, 10:30:00, 10:30 AM, 10 am."""
    if value is None or not value.strip():
        return None
    text = value.strip().casefold().replace(".", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?", text)
    if match is None:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    second = int(match.group(3) or 0)
    meridiem = match.group(4)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)
