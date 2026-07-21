import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.appointment import Appointment, AppointmentStatus
from app.models.clinic import ClinicStatus
from app.models.slot import Slot, SlotStatus
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.slot_repository import SlotRepository
from app.schemas.appointment import AppointmentUpdate
from app.services.activity_log_service import ActivityLogService
from app.utils.address import compose_clinic_address

# Allowed status transitions (docs/03 §10).
ALLOWED_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.PENDING: {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED},
    AppointmentStatus.CONFIRMED: {
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    },
    AppointmentStatus.COMPLETED: set(),
    AppointmentStatus.CANCELLED: set(),
    AppointmentStatus.NO_SHOW: {AppointmentStatus.COMPLETED},
}

RESCHEDULABLE = {AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED}


class AppointmentService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._appointments = AppointmentRepository(db)
        self._slots = SlotRepository(db)
        self._clinics = ClinicRepository(db)
        self._activity = ActivityLogService(db)

    def list_appointments(
        self, doctor_id: uuid.UUID, filters: dict, page: int, limit: int
    ) -> tuple[list[Appointment], int]:
        return self._appointments.list_for_doctor(doctor_id, page=page, limit=limit, **filters)

    def get_appointment(self, doctor_id: uuid.UUID, appointment_id: uuid.UUID) -> Appointment:
        appointment = self._appointments.get_for_doctor(doctor_id, appointment_id)
        if appointment is None:
            raise ApiException(404, "Appointment not found", "NOT_FOUND")
        return appointment

    def update_appointment(
        self,
        doctor_id: uuid.UUID,
        appointment_id: uuid.UUID,
        data: AppointmentUpdate,
        request: Request | None = None,
    ) -> Appointment:
        appointment = self.get_appointment(doctor_id, appointment_id)

        if data.reschedule_slot_id is not None:
            self._reschedule(doctor_id, appointment, data.reschedule_slot_id, request)

        if data.status is not None:
            self._transition_status(appointment, data.status, data.cancellation_reason, request)

        if data.doctor_notes is not None:
            appointment.doctor_notes = data.doctor_notes

        self._db.commit()
        self._db.refresh(appointment)
        return appointment

    def _transition_status(
        self,
        appointment: Appointment,
        new_status: AppointmentStatus,
        cancellation_reason: str | None,
        request: Request | None,
    ) -> None:
        current = appointment.appointment_status
        if new_status == current:
            return
        if new_status not in ALLOWED_TRANSITIONS[current]:
            raise ApiException(
                422,
                f"Cannot change status from {current.value} to {new_status.value}",
                "VALIDATION_ERROR",
            )

        appointment.appointment_status = new_status

        if new_status == AppointmentStatus.CANCELLED:
            appointment.cancellation_reason = cancellation_reason
            self._slots.release_capacity(appointment.slot_id)
            self._activity.record(
                appointment.doctor_id,
                "CANCEL_APPOINTMENT",
                "Appointment",
                appointment.id,
                request=request,
            )
        else:
            self._activity.record(
                appointment.doctor_id,
                "UPDATE_APPOINTMENT",
                "Appointment",
                appointment.id,
                request=request,
            )

    def _reschedule(
        self,
        doctor_id: uuid.UUID,
        appointment: Appointment,
        new_slot_id: uuid.UUID,
        request: Request | None,
    ) -> None:
        if appointment.appointment_status not in RESCHEDULABLE:
            raise ApiException(
                422,
                "Only pending or confirmed appointments can be rescheduled",
                "VALIDATION_ERROR",
            )
        if new_slot_id == appointment.slot_id:
            return

        new_slot = self._slots.get_for_doctor(doctor_id, new_slot_id)
        if new_slot is None:
            raise ApiException(404, "Target slot not found", "NOT_FOUND")

        clinic = self._clinics.get_for_doctor(doctor_id, new_slot.clinic_id)
        if clinic is None or clinic.status != ClinicStatus.ACTIVE:
            raise ApiException(403, "Target clinic is not active", "CLINIC_INACTIVE")

        self._assert_slot_bookable(new_slot, clinic.timezone)

        if self._appointments.has_active_for_slot_patient(new_slot.id, appointment.patient_id):
            raise ApiException(
                409, "The patient already has a booking for that slot", "DUPLICATE_BOOKING"
            )

        if not self._slots.claim_capacity(new_slot.id):
            raise ApiException(409, "That slot is no longer available", "SLOT_FULL")

        old_slot_id = appointment.slot_id
        self._slots.release_capacity(old_slot_id)
        self._slots.mark_full_if_reached(new_slot.id)

        # Update slot reference + snapshots (the only permitted snapshot change).
        appointment.slot_id = new_slot.id
        appointment.clinic_id = clinic.id
        appointment.clinic_name = clinic.clinic_name
        appointment.clinic_address = compose_clinic_address(clinic)
        appointment.consultation_fee = clinic.consultation_fee
        appointment.appointment_date = new_slot.slot_date
        appointment.start_time = new_slot.start_time
        appointment.end_time = new_slot.end_time
        appointment.token_number = self._appointments.next_token_number(
            clinic.id, new_slot.slot_date
        )

        self._activity.record(
            doctor_id, "RESCHEDULE_APPOINTMENT", "Appointment", appointment.id, request=request
        )

    def _assert_slot_bookable(self, slot: Slot, tz_name: str) -> None:
        try:
            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now = datetime.now(ZoneInfo("Asia/Kolkata"))

        slot_start = datetime.combine(slot.slot_date, slot.start_time, tzinfo=now.tzinfo)
        if slot_start <= now:
            raise ApiException(409, "That slot is in the past", "SLOT_UNAVAILABLE")
        if slot.status == SlotStatus.FULL or slot.booked_count >= slot.capacity:
            raise ApiException(409, "That slot is fully booked", "SLOT_FULL")
        if slot.status != SlotStatus.AVAILABLE:
            raise ApiException(409, "That slot is not available", "SLOT_UNAVAILABLE")

    @staticmethod
    def parse_filters(
        status: AppointmentStatus | None,
        clinic_id: uuid.UUID | None,
        appointment_date: date | None,
        date_from: date | None,
        date_to: date | None,
        patient_name: str | None,
        appointment_number: str | None,
    ) -> dict:
        return {
            "status": status,
            "clinic_id": clinic_id,
            "appointment_date": appointment_date,
            "date_from": date_from,
            "date_to": date_to,
            "patient_name": patient_name,
            "appointment_number": appointment_number,
        }
