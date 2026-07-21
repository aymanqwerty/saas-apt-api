from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.rate_limit import login_rate_limiter
from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.auth import LoginData, LoginRequest
from app.schemas.common import ApiResponse
from app.schemas.doctor import DoctorResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth")


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=ApiResponse[LoginData])
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession
) -> ApiResponse[LoginData]:
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{body.email.lower()}"
    if not login_rate_limiter.is_allowed(rate_key):
        raise ApiException(
            429, "Too many login attempts. Please try again shortly.", "RATE_LIMITED"
        )

    token, doctor = AuthService(db).login(body.email, body.password, request=request)
    _set_auth_cookie(response, token)

    return ApiResponse(
        message="Login successful",
        data=LoginData(token=token, doctor=DoctorResponse.model_validate(doctor)),
    )


@router.get("/me", response_model=ApiResponse[DoctorResponse])
def me(doctor: CurrentDoctor) -> ApiResponse[DoctorResponse]:
    return ApiResponse(data=DoctorResponse.model_validate(doctor))


@router.post("/logout", response_model=ApiResponse[None])
def logout(doctor: CurrentDoctor, response: Response) -> ApiResponse[None]:
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return ApiResponse(message="Logged out", data=None)
