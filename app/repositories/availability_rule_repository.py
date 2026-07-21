import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.availability_rule import AvailabilityRule, AvailabilityRuleStatus


class AvailabilityRuleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_doctor(self, doctor_id: uuid.UUID) -> list[AvailabilityRule]:
        stmt = (
            select(AvailabilityRule)
            .where(AvailabilityRule.doctor_id == doctor_id)
            .order_by(AvailabilityRule.weekday, AvailabilityRule.start_time)
        )
        return list(self._db.scalars(stmt))

    def get_for_doctor(self, doctor_id: uuid.UUID, rule_id: uuid.UUID) -> AvailabilityRule | None:
        stmt = select(AvailabilityRule).where(
            AvailabilityRule.id == rule_id,
            AvailabilityRule.doctor_id == doctor_id,
        )
        return self._db.scalar(stmt)

    def list_active_for_doctor(self, doctor_id: uuid.UUID) -> list[AvailabilityRule]:
        stmt = select(AvailabilityRule).where(
            AvailabilityRule.doctor_id == doctor_id,
            AvailabilityRule.status == AvailabilityRuleStatus.ACTIVE,
        )
        return list(self._db.scalars(stmt))

    def list_all_active(self) -> list[AvailabilityRule]:
        stmt = select(AvailabilityRule).where(
            AvailabilityRule.status == AvailabilityRuleStatus.ACTIVE
        )
        return list(self._db.scalars(stmt))

    def add(self, rule: AvailabilityRule) -> None:
        self._db.add(rule)
        self._db.flush()

    def delete(self, rule: AvailabilityRule) -> None:
        self._db.delete(rule)
        self._db.flush()
