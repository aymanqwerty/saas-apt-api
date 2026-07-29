import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.otp_challenge import OtpChallenge


class OtpChallengeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_active(
        self, doctor_id: uuid.UUID, phone_number: str, now: datetime
    ) -> OtpChallenge | None:
        """The most recent unconsumed, unexpired challenge for a (doctor, phone)."""
        stmt = (
            select(OtpChallenge)
            .where(
                OtpChallenge.doctor_id == doctor_id,
                OtpChallenge.phone_number == phone_number,
                OtpChallenge.consumed_at.is_(None),
                OtpChallenge.expires_at > now,
            )
            .order_by(OtpChallenge.created_at.desc())
        )
        return self._db.scalar(stmt)

    def invalidate_active(
        self, doctor_id: uuid.UUID, phone_number: str, now: datetime
    ) -> None:
        """Consume any live challenges so only the newest code is ever valid."""
        self._db.execute(
            update(OtpChallenge)
            .where(
                OtpChallenge.doctor_id == doctor_id,
                OtpChallenge.phone_number == phone_number,
                OtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

    def count_for_phone_since(self, phone_number: str, since: datetime) -> int:
        """How many codes we have sent to this number since `since`.

        Deliberately NOT scoped to a doctor: the thing being protected is the
        handset (and our SMS spend), so someone cycling through doctor slugs
        must not get a fresh allowance each time. Database-backed rather than
        in-memory so the cap holds across instances.
        """
        return (
            self._db.scalar(
                select(func.count())
                .select_from(OtpChallenge)
                .where(
                    OtpChallenge.phone_number == phone_number,
                    OtpChallenge.created_at > since,
                )
            )
            or 0
        )

    def add(self, challenge: OtpChallenge) -> None:
        self._db.add(challenge)
        self._db.flush()
