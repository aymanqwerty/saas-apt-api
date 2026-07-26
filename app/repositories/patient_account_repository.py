import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone import normalize_phone
from app.models.patient_account import PatientAccount


class PatientAccountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, account_id: uuid.UUID) -> PatientAccount | None:
        return self._db.scalar(select(PatientAccount).where(PatientAccount.id == account_id))

    def get_by_phone(self, doctor_id: uuid.UUID, phone_number: str) -> PatientAccount | None:
        stmt = select(PatientAccount).where(
            PatientAccount.doctor_id == doctor_id,
            PatientAccount.phone_number == normalize_phone(phone_number),
        )
        return self._db.scalar(stmt)

    def add(self, account: PatientAccount) -> None:
        self._db.add(account)
        self._db.flush()

    def update_last_login(self, account: PatientAccount) -> None:
        account.last_login_at = datetime.now(UTC)
        self._db.flush()
