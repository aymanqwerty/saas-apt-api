import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.service import Service
from app.repositories.service_repository import ServiceRepository
from app.schemas.service import ServiceCreate, ServiceUpdate
from app.services.activity_log_service import ActivityLogService


class ServiceCatalogService:
    """Manages the treatments/procedures a doctor offers (docs/03 §13a)."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._services = ServiceRepository(db)
        self._activity = ActivityLogService(db)

    def list_services(self, doctor_id: uuid.UUID) -> list[Service]:
        return self._services.list_for_doctor(doctor_id)

    def get_service(self, doctor_id: uuid.UUID, service_id: uuid.UUID) -> Service:
        service = self._services.get_for_doctor(doctor_id, service_id)
        if service is None:
            raise ApiException(404, "Service not found", "NOT_FOUND")
        return service

    def create_service(
        self, doctor_id: uuid.UUID, data: ServiceCreate, request: Request | None = None
    ) -> Service:
        service = Service(doctor_id=doctor_id, **data.model_dump())
        self._services.add(service)
        self._activity.record(doctor_id, "CREATE_SERVICE", "Service", service.id, request=request)
        self._db.commit()
        self._db.refresh(service)
        return service

    def update_service(
        self,
        doctor_id: uuid.UUID,
        service_id: uuid.UUID,
        data: ServiceUpdate,
        request: Request | None = None,
    ) -> Service:
        service = self.get_service(doctor_id, service_id)

        updates = data.model_dump(exclude_unset=True)
        for field in {"title", "sort_order", "status"} & updates.keys():
            if updates[field] is None:
                raise ApiException(422, f"{field} cannot be empty", "VALIDATION_ERROR")

        for field, value in updates.items():
            setattr(service, field, value)

        self._activity.record(doctor_id, "UPDATE_SERVICE", "Service", service.id, request=request)
        self._db.commit()
        self._db.refresh(service)
        return service

    def delete_service(
        self, doctor_id: uuid.UUID, service_id: uuid.UUID, request: Request | None = None
    ) -> None:
        service = self.get_service(doctor_id, service_id)
        service_id_value = service.id
        self._services.delete(service)
        self._activity.record(
            doctor_id, "DELETE_SERVICE", "Service", service_id_value, request=request
        )
        self._db.commit()
