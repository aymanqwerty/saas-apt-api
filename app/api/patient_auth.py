from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.rate_limit import (
    get_client_ip,
    otp_request_rate_limiter,
    patient_login_rate_limiter,
)
from app.dependencies.database import DbSession
from app.dependencies.patient_auth import CurrentAccount
from app.schemas.common import ApiResponse
from app.schemas.patient_auth import (
    MeResponse,
    PasswordLoginRequest,
    PatientAuthData,
    RequestOtpRequest,
    RequestOtpResponse,
    SetPasswordRequest,
    VerifyOtpRequest,
)
from app.services.patient_auth_service import PatientAuthService

router = APIRouter(prefix="/patient-auth")


def _set_patient_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.patient_auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=settings.patient_access_token_expire_minutes * 60,
        path="/",
    )


def _client_key(request: Request, *parts: str) -> str:
    return ":".join([get_client_ip(request), *parts])


@router.post("/request-otp", response_model=ApiResponse[RequestOtpResponse])
def request_otp(
    body: RequestOtpRequest, request: Request, db: DbSession
) -> ApiResponse[RequestOtpResponse]:
    if not otp_request_rate_limiter.is_allowed(
        _client_key(request, body.doctor_slug, body.phone_number)
    ):
        raise ApiException(429, "Too many requests. Please try again shortly.", "RATE_LIMITED")

    expires_in, debug_code = PatientAuthService(db).request_otp(
        body.doctor_slug, body.phone_number
    )
    return ApiResponse(
        message="Verification code sent",
        data=RequestOtpResponse(expires_in_seconds=expires_in, debug_code=debug_code),
    )


@router.post("/verify-otp", response_model=ApiResponse[PatientAuthData])
def verify_otp(
    body: VerifyOtpRequest, request: Request, response: Response, db: DbSession
) -> ApiResponse[PatientAuthData]:
    if not patient_login_rate_limiter.is_allowed(
        _client_key(request, body.doctor_slug, body.phone_number)
    ):
        raise ApiException(429, "Too many attempts. Please try again shortly.", "RATE_LIMITED")

    data = PatientAuthService(db).verify_otp(body.doctor_slug, body.phone_number, body.code)
    _set_patient_cookie(response, data.token)
    return ApiResponse(message="Signed in", data=data)


@router.post("/login", response_model=ApiResponse[PatientAuthData])
def login_with_password(
    body: PasswordLoginRequest, request: Request, response: Response, db: DbSession
) -> ApiResponse[PatientAuthData]:
    if not patient_login_rate_limiter.is_allowed(
        _client_key(request, body.doctor_slug, body.phone_number)
    ):
        raise ApiException(429, "Too many attempts. Please try again shortly.", "RATE_LIMITED")

    data = PatientAuthService(db).login_with_password(
        body.doctor_slug, body.phone_number, body.password
    )
    _set_patient_cookie(response, data.token)
    return ApiResponse(message="Signed in", data=data)


@router.get("/me", response_model=ApiResponse[MeResponse])
def me(account: CurrentAccount, db: DbSession) -> ApiResponse[MeResponse]:
    return ApiResponse(data=PatientAuthService(db).me(account))


@router.post("/set-password", response_model=ApiResponse[None])
def set_password(
    body: SetPasswordRequest, account: CurrentAccount, db: DbSession
) -> ApiResponse[None]:
    PatientAuthService(db).set_password(account, body.password)
    return ApiResponse(message="Password updated", data=None)


@router.post("/logout", response_model=ApiResponse[None])
def logout(response: Response) -> ApiResponse[None]:
    response.delete_cookie(settings.patient_auth_cookie_name, path="/")
    return ApiResponse(message="Signed out", data=None)
