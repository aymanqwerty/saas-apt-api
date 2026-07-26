import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.payment import Payment, PaymentStatus


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_hold(self, hold_id: uuid.UUID) -> Payment | None:
        return self._db.scalar(select(Payment).where(Payment.hold_id == hold_id))

    def get_by_provider_order_id(self, provider_order_id: str) -> Payment | None:
        return self._db.scalar(
            select(Payment).where(Payment.provider_order_id == provider_order_id)
        )

    def list_for_doctor(
        self,
        doctor_id: uuid.UUID,
        *,
        status: PaymentStatus | None = None,
        clinic_id: uuid.UUID | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Payment], int]:
        filters = [Payment.doctor_id == doctor_id]
        if status:
            filters.append(Payment.status == status)
        if clinic_id:
            filters.append(Payment.clinic_id == clinic_id)
        if search:
            # Assuming search by patient_name
            filters.append(Payment.patient_name.ilike(f"%{search}%"))
        if date_from:
            filters.append(Payment.created_at >= date_from)
        if date_to:
            # created_at is a timestamp; add a day so the whole `date_to` is inclusive.
            filters.append(Payment.created_at < date_to + timedelta(days=1))

        base = select(Payment).where(*filters)
        total = self._db.scalar(select(func.count()).select_from(base.subquery()))
        items = list(
            self._db.scalars(
                base.order_by(Payment.created_at.asc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        )
        return items, total or 0

    def add(self, payment: Payment) -> None:
        self._db.add(payment)
        self._db.flush()
