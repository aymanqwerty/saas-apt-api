import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.availability_exception import AvailabilityException
from app.models.availability_rule import (
    WEEKDAY_TO_PY,
    AvailabilityRule,
    AvailabilityRuleStatus,
)
from app.models.clinic import Clinic
from app.models.slot import Slot, SlotStatus
from app.repositories.availability_exception_repository import (
    AvailabilityExceptionRepository,
)
from app.repositories.availability_rule_repository import AvailabilityRuleRepository
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.slot_repository import SlotRepository

# Rolling window of days for which slots are pre-generated (docs/04 §21).
GENERATION_WINDOW_DAYS = 90


def _today_in_timezone(tz_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def _time_slots(
    start: time, end: time, duration_minutes: int, buffer_minutes: int
) -> list[tuple[time, time]]:
    """Split [start, end] into (slot_start, slot_end) pairs, buffer between them."""
    base = datetime(2000, 1, 1)
    cursor = datetime.combine(base.date(), start)
    end_dt = datetime.combine(base.date(), end)
    duration = timedelta(minutes=duration_minutes)
    step = duration + timedelta(minutes=buffer_minutes)

    slots: list[tuple[time, time]] = []
    while cursor + duration <= end_dt:
        slot_end = cursor + duration
        slots.append((cursor.time(), slot_end.time()))
        cursor = cursor + step
    return slots


class SlotGenerationService:
    """Generates persisted slots from availability rules, applying exceptions."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._slots = SlotRepository(db)
        self._exceptions = AvailabilityExceptionRepository(db)
        self._rules = AvailabilityRuleRepository(db)
        self._clinics = ClinicRepository(db)

    def _effective_exception(
        self,
        exceptions: list[AvailabilityException],
        clinic_id: uuid.UUID,
        on_date: date,
    ) -> AvailabilityException | None:
        """Clinic-specific exception wins over a doctor-wide (clinic NULL) one."""
        clinic_specific = None
        doctor_wide = None
        for exc in exceptions:
            if exc.exception_date != on_date:
                continue
            if exc.clinic_id == clinic_id:
                clinic_specific = exc
            elif exc.clinic_id is None:
                doctor_wide = exc
        return clinic_specific or doctor_wide

    def generate_for_rule(self, rule: AvailabilityRule, clinic: Clinic) -> int:
        """Create missing slots for a rule across the rolling window. Returns count added."""
        today = _today_in_timezone(clinic.timezone)
        window_end = today + timedelta(days=GENERATION_WINDOW_DAYS)

        start_date = max(today, rule.effective_from)
        end_date = window_end
        if rule.effective_until:
            end_date = min(end_date, rule.effective_until)
        if start_date > end_date:
            return 0

        exceptions = self._exceptions.list_for_doctor_in_range(rule.doctor_id, start_date, end_date)
        target_weekday = WEEKDAY_TO_PY[rule.weekday]

        added = 0
        current = start_date
        while current <= end_date:
            if current.weekday() == target_weekday:
                added += self._generate_for_date(rule, clinic, current, exceptions)
            current += timedelta(days=1)

        return added

    def _generate_for_date(
        self,
        rule: AvailabilityRule,
        clinic: Clinic,
        on_date: date,
        exceptions: list[AvailabilityException],
    ) -> int:
        start_time = rule.start_time
        end_time = rule.end_time

        exception = self._effective_exception(exceptions, clinic.id, on_date)
        if exception is not None:
            if not exception.is_available:
                return 0  # doctor unavailable this day
            if exception.custom_start_time and exception.custom_end_time:
                start_time = exception.custom_start_time
                end_time = exception.custom_end_time

        existing = self._slots.existing_start_times(clinic.id, on_date)

        added = 0
        for slot_start, slot_end in _time_slots(
            start_time, end_time, rule.slot_duration_minutes, rule.buffer_minutes
        ):
            if slot_start in existing:
                continue
            self._slots.add(
                Slot(
                    doctor_id=rule.doctor_id,
                    clinic_id=clinic.id,
                    availability_rule_id=rule.id,
                    slot_date=on_date,
                    start_time=slot_start,
                    end_time=slot_end,
                    capacity=rule.patients_per_slot,
                    status=SlotStatus.AVAILABLE,
                )
            )
            added += 1
        return added

    def regenerate_for_rule(self, rule: AvailabilityRule, clinic: Clinic) -> None:
        """Drop future unbooked, unblocked slots for the rule, then regenerate.

        Booked or manually blocked slots are preserved (docs/04 §21).
        """
        today = _today_in_timezone(clinic.timezone)
        for slot in self._slots.list_for_rule_from(rule.id, today):
            if slot.booked_count == 0 and not slot.is_manually_blocked:
                self._slots.delete(slot)
        self._db.flush()
        self.generate_for_rule(rule, clinic)

    def retire_future_slots_for_rule(
        self, rule_id: uuid.UUID, tz_name: str, reason: str = "Availability removed"
    ) -> None:
        """A rule was deleted or disabled.

        Remove its empty future slots and BLOCK the booked ones, so existing
        appointments are preserved but the freed capacity no longer accepts new
        bookings (docs/03 §5).
        """
        today = _today_in_timezone(tz_name)
        for slot in self._slots.list_for_rule_from(rule_id, today):
            if slot.is_manually_blocked:
                continue
            if slot.booked_count == 0:
                self._slots.delete(slot)
            else:
                slot.is_manually_blocked = True
                slot.status = SlotStatus.BLOCKED
                slot.block_reason = reason
        self._db.flush()

    def rebuild_doctor_date(
        self, doctor_id: uuid.UUID, on_date: date, clinic_id: uuid.UUID | None
    ) -> None:
        """Rebuild slots for a single date after an exception change.

        Removes future unbooked/unblocked slots on that date (for the given
        clinic, or all clinics if None), then regenerates from active rules
        (which re-reads the current exceptions).
        """
        clinics = (
            [self._clinics.get_for_doctor(doctor_id, clinic_id)]
            if clinic_id is not None
            else self._clinics.list_for_doctor(doctor_id)
        )
        clinics = [c for c in clinics if c is not None]
        if not clinics:
            return

        py_weekday = on_date.weekday()
        active_rules = self._rules.list_active_for_doctor(doctor_id)

        for clinic in clinics:
            for slot in self._slots.list_for_doctor(
                doctor_id, clinic_id=clinic.id, slot_date=on_date
            ):
                if slot.booked_count == 0 and not slot.is_manually_blocked:
                    self._slots.delete(slot)
            self._db.flush()

            for rule in active_rules:
                if rule.clinic_id != clinic.id:
                    continue
                if WEEKDAY_TO_PY[rule.weekday] != py_weekday:
                    continue
                if rule.status != AvailabilityRuleStatus.ACTIVE:
                    continue
                if on_date < rule.effective_from:
                    continue
                if rule.effective_until and on_date > rule.effective_until:
                    continue
                self._generate_for_date(
                    rule,
                    clinic,
                    on_date,
                    self._exceptions.list_for_doctor_in_range(doctor_id, on_date, on_date),
                )
        self._db.flush()

    def run_maintenance(self) -> None:
        """Daily job: extend the rolling window and expire past slots."""
        for rule in self._rules.list_all_active():
            clinic = self._clinics.get_for_doctor(rule.doctor_id, rule.clinic_id)
            if clinic is not None:
                self.generate_for_rule(rule, clinic)

        for clinic in self._clinics_all():
            today = _today_in_timezone(clinic.timezone)
            for slot in self._slots.list_for_doctor(clinic.doctor_id, clinic_id=clinic.id):
                if slot.slot_date < today and slot.status == SlotStatus.AVAILABLE:
                    slot.status = SlotStatus.EXPIRED
        self._db.commit()

    def _clinics_all(self) -> list[Clinic]:
        from sqlalchemy import select

        stmt = select(Clinic).where(Clinic.deleted_at.is_(None))
        return list(self._db.scalars(stmt))
