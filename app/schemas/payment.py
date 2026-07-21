import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.payment import Payment, PaymentStatus


class PaymentListItem(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider: str
    patient_name: str
    clinic_name: str
    appointment_id: uuid.UUID | None
    provider_payment_id: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, payment: Payment) -> "PaymentListItem":
        return cls(
            id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            provider=payment.provider,
            patient_name=payment.patient_name,
            clinic_name=payment.clinic_name,
            appointment_id=payment.appointment_id,
            provider_payment_id=payment.provider_payment_id,
            created_at=payment.created_at,
        )
