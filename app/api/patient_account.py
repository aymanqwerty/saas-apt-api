import uuid

from fastapi import APIRouter

from app.dependencies.database import DbSession
from app.dependencies.patient_auth import CurrentAccount
from app.schemas.common import ApiResponse
from app.schemas.patient_account import (
    MemberCreateRequest,
    MemberUpdateRequest,
    MyAppointmentItem,
    PatientProfile,
    ProfileUpsertRequest,
)
from app.services.patient_account_service import PatientAccountService

router = APIRouter(prefix="/patient-account")


@router.get("/profile", response_model=ApiResponse[PatientProfile | None])
def get_profile(account: CurrentAccount, db: DbSession) -> ApiResponse[PatientProfile | None]:
    return ApiResponse(data=PatientAccountService(db).get_profile(account))


@router.put("/profile", response_model=ApiResponse[PatientProfile])
def upsert_profile(
    body: ProfileUpsertRequest, account: CurrentAccount, db: DbSession
) -> ApiResponse[PatientProfile]:
    profile = PatientAccountService(db).upsert_profile(account, body)
    return ApiResponse(message="Profile saved", data=profile)


@router.get("/members", response_model=ApiResponse[list[PatientProfile]])
def list_members(account: CurrentAccount, db: DbSession) -> ApiResponse[list[PatientProfile]]:
    return ApiResponse(data=PatientAccountService(db).list_members(account))


@router.post("/members", response_model=ApiResponse[PatientProfile], status_code=201)
def add_member(
    body: MemberCreateRequest, account: CurrentAccount, db: DbSession
) -> ApiResponse[PatientProfile]:
    member = PatientAccountService(db).add_member(account, body)
    return ApiResponse(message="Family member added", data=member)


@router.patch("/members/{member_id}", response_model=ApiResponse[PatientProfile])
def update_member(
    member_id: uuid.UUID,
    body: MemberUpdateRequest,
    account: CurrentAccount,
    db: DbSession,
) -> ApiResponse[PatientProfile]:
    member = PatientAccountService(db).update_member(account, member_id, body)
    return ApiResponse(message="Family member updated", data=member)


@router.delete("/members/{member_id}", response_model=ApiResponse[None])
def delete_member(
    member_id: uuid.UUID, account: CurrentAccount, db: DbSession
) -> ApiResponse[None]:
    PatientAccountService(db).delete_member(account, member_id)
    return ApiResponse(message="Family member removed", data=None)


@router.get("/appointments", response_model=ApiResponse[list[MyAppointmentItem]])
def list_appointments(
    account: CurrentAccount, db: DbSession
) -> ApiResponse[list[MyAppointmentItem]]:
    return ApiResponse(data=PatientAccountService(db).list_appointments(account))
