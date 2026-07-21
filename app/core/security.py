from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(
    subject: str, token_type: str = "doctor", expires_minutes: int | None = None
) -> str:
    now = datetime.now(UTC)
    minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.access_token_expire_minutes
    )
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, expected_type: str = "doctor") -> str | None:
    """Return the token subject or None if invalid/expired/wrong audience.

    A token is only accepted for the audience it was minted for so a patient
    token can never authenticate against doctor endpoints (or vice versa).
    Tokens issued before typed claims existed are treated as doctor tokens.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type", "doctor") != expected_type:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
