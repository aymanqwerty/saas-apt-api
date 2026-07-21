import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service import Service, ServiceStatus


class ServiceRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_doctor(self, doctor_id: uuid.UUID) -> list[Service]:
        stmt = (
            select(Service)
            .where(Service.doctor_id == doctor_id)
            .order_by(Service.sort_order.asc(), Service.created_at.asc())
        )
        return list(self._db.scalars(stmt))

    def list_active_for_doctor(self, doctor_id: uuid.UUID) -> list[Service]:
        stmt = (
            select(Service)
            .where(Service.doctor_id == doctor_id, Service.status == ServiceStatus.ACTIVE)
            .order_by(Service.sort_order.asc(), Service.created_at.asc())
        )
        return list(self._db.scalars(stmt))

    def get_for_doctor(self, doctor_id: uuid.UUID, service_id: uuid.UUID) -> Service | None:
        stmt = select(Service).where(
            Service.id == service_id,
            Service.doctor_id == doctor_id,
        )
        return self._db.scalar(stmt)

    def add(self, service: Service) -> None:
        self._db.add(service)
        self._db.flush()

    def delete(self, service: Service) -> None:
        self._db.delete(service)
        self._db.flush()
