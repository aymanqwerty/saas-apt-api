import uuid
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.security import decode_access_token
from app.dependencies.database import DbSession
from app.models.patient_account import PatientAccount
from app.repositories.patient_account_repository import PatientAccountRepository


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    return request.cookies.get(settings.patient_auth_cookie_name)


def _account_from_token(request: Request, db) -> PatientAccount | None:
    token = _extract_token(request)
    if not token:
        return None
    subject = decode_access_token(token, expected_type="patient")
    if subject is None:
        return None
    try:
        account_id = uuid.UUID(subject)
    except ValueError:
        return None
    return PatientAccountRepository(db).get_by_id(account_id)


def get_current_account(request: Request, db: DbSession) -> PatientAccount:
    account = _account_from_token(request, db)
    if account is None:
        raise ApiException(401, "Not authenticated", "UNAUTHORIZED")
    return account


def get_optional_account(request: Request, db: DbSession) -> PatientAccount | None:
    """Patient account if a valid patient token is present, else None (guest)."""
    return _account_from_token(request, db)


CurrentAccount = Annotated[PatientAccount, Depends(get_current_account)]
OptionalAccount = Annotated[PatientAccount | None, Depends(get_optional_account)]
