import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.availability import (
    AvailabilityRuleBulkCreate,
    AvailabilityRuleCreate,
    AvailabilityRuleResponse,
    AvailabilityRuleUpdate,
)
from app.schemas.availability_exception import (
    AvailabilityExceptionCreate,
    AvailabilityExceptionResponse,
    AvailabilityExceptionUpdate,
)
from app.schemas.common import ApiResponse
from app.services.availability_service import AvailabilityService
from app.services.exception_service import ExceptionService

router = APIRouter(prefix="/availability")


# --- Exceptions (defined before /{rule_id} routes) ---


@router.get("/exceptions", response_model=ApiResponse[list[AvailabilityExceptionResponse]])
def list_exceptions(
    doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[list[AvailabilityExceptionResponse]]:
    items = ExceptionService(db).list_exceptions(doctor.id)
    return ApiResponse(data=[AvailabilityExceptionResponse.model_validate(e) for e in items])


@router.post(
    "/exceptions", response_model=ApiResponse[AvailabilityExceptionResponse], status_code=201
)
def create_exception(
    body: AvailabilityExceptionCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[AvailabilityExceptionResponse]:
    exc = ExceptionService(db).create_exception(doctor.id, body, request=request)
    return ApiResponse(
        message="Exception created", data=AvailabilityExceptionResponse.model_validate(exc)
    )


@router.patch(
    "/exceptions/{exception_id}", response_model=ApiResponse[AvailabilityExceptionResponse]
)
def update_exception(
    exception_id: uuid.UUID,
    body: AvailabilityExceptionUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[AvailabilityExceptionResponse]:
    exc = ExceptionService(db).update_exception(doctor.id, exception_id, body, request=request)
    return ApiResponse(
        message="Exception updated", data=AvailabilityExceptionResponse.model_validate(exc)
    )


@router.delete("/exceptions/{exception_id}", response_model=ApiResponse[None])
def delete_exception(
    exception_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    ExceptionService(db).delete_exception(doctor.id, exception_id, request=request)
    return ApiResponse(message="Exception deleted", data=None)


# --- Recurring rules ---


@router.get("", response_model=ApiResponse[list[AvailabilityRuleResponse]])
def list_rules(doctor: CurrentDoctor, db: DbSession) -> ApiResponse[list[AvailabilityRuleResponse]]:
    return ApiResponse(data=AvailabilityService(db).list_rules(doctor.id))


@router.post("", response_model=ApiResponse[AvailabilityRuleResponse], status_code=201)
def create_rule(
    body: AvailabilityRuleCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[AvailabilityRuleResponse]:
    rule = AvailabilityService(db).create_rule(doctor.id, body, request=request)
    return ApiResponse(
        message="Availability rule created", data=AvailabilityRuleResponse.model_validate(rule)
    )


@router.post("/bulk", response_model=ApiResponse[list[AvailabilityRuleResponse]], status_code=201)
def create_rules_bulk(
    body: AvailabilityRuleBulkCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[list[AvailabilityRuleResponse]]:
    rules = AvailabilityService(db).create_rules_bulk(doctor.id, body, request=request)
    return ApiResponse(
        message="Availability rules created",
        data=[AvailabilityRuleResponse.model_validate(r) for r in rules],
    )


@router.patch("/{rule_id}", response_model=ApiResponse[AvailabilityRuleResponse])
def update_rule(
    rule_id: uuid.UUID,
    body: AvailabilityRuleUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[AvailabilityRuleResponse]:
    rule = AvailabilityService(db).update_rule(doctor.id, rule_id, body, request=request)
    return ApiResponse(
        message="Availability rule updated", data=AvailabilityRuleResponse.model_validate(rule)
    )


@router.delete("/{rule_id}", response_model=ApiResponse[None])
def delete_rule(
    rule_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    AvailabilityService(db).delete_rule(doctor.id, rule_id, request=request)
    return ApiResponse(message="Availability rule deleted", data=None)
