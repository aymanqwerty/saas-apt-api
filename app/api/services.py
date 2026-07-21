import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.schemas.service import ServiceCreate, ServiceResponse, ServiceUpdate
from app.services.service_catalog_service import ServiceCatalogService

router = APIRouter(prefix="/services")


@router.get("", response_model=ApiResponse[list[ServiceResponse]])
def list_services(doctor: CurrentDoctor, db: DbSession) -> ApiResponse[list[ServiceResponse]]:
    services = ServiceCatalogService(db).list_services(doctor.id)
    return ApiResponse(data=[ServiceResponse.model_validate(s) for s in services])


@router.post("", response_model=ApiResponse[ServiceResponse], status_code=201)
def create_service(
    body: ServiceCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[ServiceResponse]:
    service = ServiceCatalogService(db).create_service(doctor.id, body, request=request)
    return ApiResponse(message="Service created", data=ServiceResponse.model_validate(service))


@router.patch("/{service_id}", response_model=ApiResponse[ServiceResponse])
def update_service(
    service_id: uuid.UUID,
    body: ServiceUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[ServiceResponse]:
    service = ServiceCatalogService(db).update_service(doctor.id, service_id, body, request=request)
    return ApiResponse(message="Service updated", data=ServiceResponse.model_validate(service))


@router.delete("/{service_id}", response_model=ApiResponse[None])
def delete_service(
    service_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    ServiceCatalogService(db).delete_service(doctor.id, service_id, request=request)
    return ApiResponse(message="Service deleted", data=None)
