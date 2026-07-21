import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.availability_rule import AvailabilityRule, AvailabilityRuleStatus
from app.repositories.availability_rule_repository import AvailabilityRuleRepository
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.slot_repository import SlotRepository
from app.schemas.availability import (
    AvailabilityRuleBulkCreate,
    AvailabilityRuleCreate,
    AvailabilityRuleResponse,
    AvailabilityRuleUpdate,
)
from app.services.activity_log_service import ActivityLogService
from app.services.slot_generation_service import SlotGenerationService

_REFERENCE_TZ = "Asia/Kolkata"


def _times_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


def _windows_overlap(
    from_a: date, until_a: date | None, from_b: date, until_b: date | None
) -> bool:
    a_before_b = until_a is not None and until_a < from_b
    b_before_a = until_b is not None and until_b < from_a
    return not (a_before_b or b_before_a)


class AvailabilityService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._rules = AvailabilityRuleRepository(db)
        self._clinics = ClinicRepository(db)
        self._activity = ActivityLogService(db)
        self._generation = SlotGenerationService(db)
        self._slots = SlotRepository(db)

    def list_rules(self, doctor_id: uuid.UUID) -> list[AvailabilityRuleResponse]:
        today = datetime.now(ZoneInfo(_REFERENCE_TZ)).date()
        responses: list[AvailabilityRuleResponse] = []
        for rule in self._rules.list_for_doctor(doctor_id):
            resp = AvailabilityRuleResponse.model_validate(rule)
            resp.upcoming_booked_count = self._slots.count_future_booked_for_rule(rule.id, today)
            responses.append(resp)
        return responses

    def _require_clinic(self, doctor_id: uuid.UUID, clinic_id: uuid.UUID):
        clinic = self._clinics.get_for_doctor(doctor_id, clinic_id)
        if clinic is None:
            raise ApiException(404, "Clinic not found", "NOT_FOUND")
        return clinic

    def _assert_no_overlap(
        self,
        doctor_id: uuid.UUID,
        weekday,
        start_time: time,
        end_time: time,
        effective_from: date,
        effective_until: date | None,
        exclude_id: uuid.UUID | None,
    ) -> None:
        # A doctor is one person: overlap is checked across ALL clinics (docs/03 §5).
        for other in self._rules.list_active_for_doctor(doctor_id):
            if other.id == exclude_id or other.weekday != weekday:
                continue
            if _times_overlap(start_time, end_time, other.start_time, other.end_time) and (
                _windows_overlap(
                    effective_from, effective_until, other.effective_from, other.effective_until
                )
            ):
                raise ApiException(
                    409,
                    "This schedule overlaps an existing availability rule",
                    "OVERLAPPING_RULE",
                )

    def create_rule(
        self, doctor_id: uuid.UUID, data: AvailabilityRuleCreate, request: Request | None = None
    ) -> AvailabilityRule:
        clinic = self._require_clinic(doctor_id, data.clinic_id)
        if data.status == AvailabilityRuleStatus.ACTIVE:
            self._assert_no_overlap(
                doctor_id,
                data.weekday,
                data.start_time,
                data.end_time,
                data.effective_from,
                data.effective_until,
                exclude_id=None,
            )

        rule = AvailabilityRule(doctor_id=doctor_id, **data.model_dump())
        self._rules.add(rule)

        if rule.status == AvailabilityRuleStatus.ACTIVE:
            self._generation.generate_for_rule(rule, clinic)

        self._activity.record(
            doctor_id, "CREATE_AVAILABILITY", "AvailabilityRule", rule.id, request=request
        )
        self._db.commit()
        self._db.refresh(rule)
        return rule

    def create_rules_bulk(
        self,
        doctor_id: uuid.UUID,
        data: AvailabilityRuleBulkCreate,
        request: Request | None = None,
    ) -> list[AvailabilityRule]:
        clinic = self._require_clinic(doctor_id, data.clinic_id)

        # Validate every selected day first — all-or-nothing (docs/03 §5).
        if data.status == AvailabilityRuleStatus.ACTIVE:
            for weekday in data.weekdays:
                try:
                    self._assert_no_overlap(
                        doctor_id,
                        weekday,
                        data.start_time,
                        data.end_time,
                        data.effective_from,
                        data.effective_until,
                        exclude_id=None,
                    )
                except ApiException:
                    raise ApiException(
                        409,
                        f"{weekday.value.title()} overlaps an existing availability rule",
                        "OVERLAPPING_RULE",
                    ) from None

        shared = data.model_dump(exclude={"weekdays"})
        created: list[AvailabilityRule] = []
        for weekday in data.weekdays:
            rule = AvailabilityRule(doctor_id=doctor_id, weekday=weekday, **shared)
            self._rules.add(rule)
            if rule.status == AvailabilityRuleStatus.ACTIVE:
                self._generation.generate_for_rule(rule, clinic)
            self._activity.record(
                doctor_id, "CREATE_AVAILABILITY", "AvailabilityRule", rule.id, request=request
            )
            created.append(rule)

        self._db.commit()
        for rule in created:
            self._db.refresh(rule)
        return created

    def update_rule(
        self,
        doctor_id: uuid.UUID,
        rule_id: uuid.UUID,
        data: AvailabilityRuleUpdate,
        request: Request | None = None,
    ) -> AvailabilityRule:
        rule = self._rules.get_for_doctor(doctor_id, rule_id)
        if rule is None:
            raise ApiException(404, "Availability rule not found", "NOT_FOUND")

        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(rule, field, value)

        if rule.end_time <= rule.start_time:
            raise ApiException(422, "end_time must be after start_time", "VALIDATION_ERROR")

        clinic = self._require_clinic(doctor_id, rule.clinic_id)

        if rule.status == AvailabilityRuleStatus.ACTIVE:
            self._assert_no_overlap(
                doctor_id,
                rule.weekday,
                rule.start_time,
                rule.end_time,
                rule.effective_from,
                rule.effective_until,
                exclude_id=rule.id,
            )
            self._generation.regenerate_for_rule(rule, clinic)
        else:
            # Rule disabled: drop empty future slots, block the booked ones.
            self._generation.retire_future_slots_for_rule(
                rule.id, clinic.timezone, "Availability rule disabled"
            )

        self._activity.record(
            doctor_id, "UPDATE_AVAILABILITY", "AvailabilityRule", rule.id, request=request
        )
        self._db.commit()
        self._db.refresh(rule)
        return rule

    def delete_rule(
        self, doctor_id: uuid.UUID, rule_id: uuid.UUID, request: Request | None = None
    ) -> None:
        rule = self._rules.get_for_doctor(doctor_id, rule_id)
        if rule is None:
            raise ApiException(404, "Availability rule not found", "NOT_FOUND")

        clinic = self._clinics.get_for_doctor(doctor_id, rule.clinic_id)
        tz_name = clinic.timezone if clinic else "Asia/Kolkata"
        self._generation.retire_future_slots_for_rule(rule.id, tz_name, "Availability rule deleted")

        rule_id_value = rule.id
        self._rules.delete(rule)
        self._activity.record(
            doctor_id, "DELETE_AVAILABILITY", "AvailabilityRule", rule_id_value, request=request
        )
        self._db.commit()
