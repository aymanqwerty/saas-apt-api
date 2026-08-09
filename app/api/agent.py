from datetime import date

from fastapi import APIRouter, Query, Request

from app.dependencies.agent_auth import AgentDoctor
from app.dependencies.database import DbSession
from app.schemas.agent import (
    AgentBookingInput,
    AgentBookingResult,
    AgentClinic,
    AgentPatientLookup,
    PhoneLookupRequest,
)
from app.schemas.common import ApiResponse
from app.schemas.public import PublicSlot
from app.services.agent_service import AgentService

# Tool endpoints the doctor's ElevenLabs agent calls during a conversation.
# Auth is the per-doctor agent key (X-Agent-Key); the doctor is never passed
# in the body — it is derived from the key.
router = APIRouter(prefix="/agent")


@router.get("/clinics", response_model=ApiResponse[list[AgentClinic]])
def list_clinics(doctor: AgentDoctor, db: DbSession) -> ApiResponse[list[AgentClinic]]:
    return ApiResponse(data=AgentService(db).list_clinics(doctor))


# The identifier params below are typed `str`, not `uuid.UUID`, on purpose: a
# hallucinated id would otherwise be rejected by FastAPI as a raw 422 that the
# agent reads as "no availability". As strings they reach AgentService, which
# answers with the valid choices so the agent can correct itself.
@router.get("/availability", response_model=ApiResponse[list[date]])
def availability(
    doctor: AgentDoctor,
    db: DbSession,
    clinic_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> ApiResponse[list[date]]:
    return ApiResponse(data=AgentService(db).available_dates(doctor, clinic_id, date_from, date_to))


@router.get("/slots", response_model=ApiResponse[list[PublicSlot]])
def slots(
    doctor: AgentDoctor,
    db: DbSession,
    clinic_id: str | None = Query(default=None),
    slot_date: str | None = Query(default=None),
) -> ApiResponse[list[PublicSlot]]:
    return ApiResponse(data=AgentService(db).slots(doctor, clinic_id, slot_date))


@router.post("/patient-lookup", response_model=ApiResponse[AgentPatientLookup])
def patient_lookup(
    body: PhoneLookupRequest, doctor: AgentDoctor, db: DbSession
) -> ApiResponse[AgentPatientLookup]:
    return ApiResponse(data=AgentService(db).lookup_patient(doctor, body.phone_number))


@router.post("/bookings", response_model=ApiResponse[AgentBookingResult])
def create_booking(
    body: AgentBookingInput, doctor: AgentDoctor, db: DbSession, request: Request
) -> ApiResponse[AgentBookingResult]:
    result = AgentService(db).book(doctor, body, request=request)
    return ApiResponse(message=result.message, data=result)


# Query alias kept for tools that prefer query params over a UUID path/body.
@router.get("/_ping", response_model=ApiResponse[None])
def ping(doctor: AgentDoctor, _q: str | None = Query(default=None)) -> ApiResponse[None]:
    return ApiResponse(message=f"agent ok for {doctor.slug}", data=None)
