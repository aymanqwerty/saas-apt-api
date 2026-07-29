"""Internal maintenance jobs, callable over HTTP.

Cloud Run freezes the CPU between requests and scales to zero, so the in-process
APScheduler cannot be trusted to run anything: with no traffic the interval job
simply does not fire, and with N instances the daily job fires N times and races
itself. Exposing the jobs as endpoints lets an external scheduler (Cloud
Scheduler) own the timing, with exactly-once semantics per trigger.

Auth is a shared secret in `X-Internal-Token`, compared in constant time. The
endpoints are disabled entirely when no token is configured, so an unconfigured
deploy cannot expose them by accident.
"""

import hmac

from fastapi import APIRouter, Header

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.scheduler import run_daily_slot_maintenance, run_hold_expiry
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.services.booking_service import BookingService

router = APIRouter(prefix="/internal/jobs", tags=["internal"])


def _authorise(token: str | None) -> None:
    configured = settings.internal_job_token
    if not configured:
        # Not "unauthorised" — the feature is off. Do not hint that it exists.
        raise ApiException(404, "Not found", "NOT_FOUND")
    if not token or not hmac.compare_digest(token, configured):
        raise ApiException(401, "Invalid internal job token", "UNAUTHORIZED")


@router.post("/expire-holds", response_model=ApiResponse[dict])
def expire_holds(
    db: DbSession, x_internal_token: str | None = Header(default=None)
) -> ApiResponse[dict]:
    """Release seats held for payments that were never completed."""
    _authorise(x_internal_token)
    released = BookingService(db).expire_stale_holds()
    return ApiResponse(message="Hold expiry complete", data={"released": released})


@router.post("/slot-maintenance", response_model=ApiResponse[dict])
def slot_maintenance(x_internal_token: str | None = Header(default=None)) -> ApiResponse[dict]:
    """Extend the rolling slot window and expire past slots."""
    _authorise(x_internal_token)
    run_daily_slot_maintenance()
    return ApiResponse(message="Slot maintenance complete", data={"ok": True})


@router.post("/run-all", response_model=ApiResponse[dict])
def run_all(x_internal_token: str | None = Header(default=None)) -> ApiResponse[dict]:
    """Both jobs in one call, for a single catch-all schedule."""
    _authorise(x_internal_token)
    run_hold_expiry()
    run_daily_slot_maintenance()
    return ApiResponse(message="Maintenance complete", data={"ok": True})
