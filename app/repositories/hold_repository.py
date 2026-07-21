import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment_hold import AppointmentHold, HoldStatus


class HoldRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, hold_id: uuid.UUID) -> AppointmentHold | None:
        return self._db.scalar(select(AppointmentHold).where(AppointmentHold.id == hold_id))

    def has_active_for_slot_patient(self, slot_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
        stmt = select(AppointmentHold.id).where(
            AppointmentHold.slot_id == slot_id,
            AppointmentHold.patient_id == patient_id,
            AppointmentHold.status == HoldStatus.HELD,
        )
        return self._db.scalar(stmt) is not None

    def list_stale(self, now: datetime, limit: int = 200) -> list[AppointmentHold]:
        """HELD holds whose deadline has passed — candidates for release."""
        stmt = (
            select(AppointmentHold)
            .where(
                AppointmentHold.status == HoldStatus.HELD,
                AppointmentHold.expires_at <= now,
            )
            .order_by(AppointmentHold.expires_at)
            .limit(limit)
        )
        return list(self._db.scalars(stmt))

    def add(self, hold: AppointmentHold) -> None:
        self._db.add(hold)
        self._db.flush()
