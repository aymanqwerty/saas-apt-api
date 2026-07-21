import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog


class ActivityLogRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, log: ActivityLog) -> None:
        self._db.add(log)
        self._db.flush()

    def list_recent_for_doctor(self, doctor_id: uuid.UUID, limit: int = 10) -> list[ActivityLog]:
        stmt = (
            select(ActivityLog)
            .where(ActivityLog.doctor_id == doctor_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
        )
        return list(self._db.scalars(stmt))
