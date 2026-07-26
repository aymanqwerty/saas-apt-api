import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limit import get_client_ip
from app.models.activity_log import ActivityLog
from app.repositories.activity_log_repository import ActivityLogRepository


class ActivityLogService:
    """Records audit events (docs/03 §19). Descriptions must never contain PII."""

    def __init__(self, db: Session) -> None:
        self._logs = ActivityLogRepository(db)

    def record(
        self,
        doctor_id: uuid.UUID,
        action: str,
        entity: str,
        entity_id: uuid.UUID | None = None,
        description: str | None = None,
        request: Request | None = None,
    ) -> None:
        self._logs.add(
            ActivityLog(
                doctor_id=doctor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                description=description,
                ip_address=get_client_ip(request) if request else None,
                user_agent=request.headers.get("User-Agent") if request else None,
            )
        )
