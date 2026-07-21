import logging
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.patient import Patient, PatientRelationship
from app.models.patient_account import PatientAccount
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.patient_account import (
    MemberCreateRequest,
    MemberUpdateRequest,
    MyAppointmentItem,
    PatientProfile,
    ProfileUpsertRequest,
)
from app.utils.dates import age_from_dob

logger = logging.getLogger(__name__)


class PatientAccountService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._patients = PatientRepository(db)
        self._appointments = AppointmentRepository(db)

    # ------------------------------------------------------------- profile
    def get_profile(self, account: PatientAccount) -> PatientProfile | None:
        self_patient = self._patients.get_self_for_account(account.id)
        return PatientProfile.model_validate(self_patient) if self_patient else None

    def upsert_profile(
        self, account: PatientAccount, data: ProfileUpsertRequest
    ) -> PatientProfile:
        self_patient = self._patients.get_self_for_account(account.id)

        if self_patient is None:
            # Adopt an existing guest record for this phone if there is one, so a
            # patient who booked as a guest before signing up keeps their history.
            self_patient = self._patients.get_by_phone(account.doctor_id, account.phone_number)
            if self_patient is not None and self_patient.account_id is None:
                self_patient.account_id = account.id
                self_patient.relationship = PatientRelationship.SELF
            else:
                self_patient = Patient(
                    doctor_id=account.doctor_id,
                    account_id=account.id,
                    relationship=PatientRelationship.SELF,
                    patient_code=self._patients.next_patient_code(account.doctor_id),
                    full_name=data.full_name,
                    phone_number=account.phone_number,
                )
                self._patients.add(self_patient)

        self_patient.full_name = data.full_name
        self_patient.email = data.email
        self_patient.gender = data.gender
        self._apply_age(self_patient, data.date_of_birth, data.age)

        self._db.commit()
        self._db.refresh(self_patient)
        return PatientProfile.model_validate(self_patient)

    # ------------------------------------------------------------- members
    def list_members(self, account: PatientAccount) -> list[PatientProfile]:
        members = self._patients.list_members_for_account(account.id)
        return [PatientProfile.model_validate(m) for m in members]

    def add_member(
        self, account: PatientAccount, data: MemberCreateRequest
    ) -> PatientProfile:
        if data.relationship == PatientRelationship.SELF:
            raise ApiException(400, "Use the profile to edit your own details", "INVALID_RELATIONSHIP")

        member = Patient(
            doctor_id=account.doctor_id,
            account_id=account.id,
            relationship=data.relationship,
            patient_code=self._patients.next_patient_code(account.doctor_id),
            full_name=data.full_name,
            # A family member may not have their own phone — fall back to the
            # account holder's (they are exempt from the primary-phone rule).
            phone_number=data.phone_number or account.phone_number,
            email=data.email,
            gender=data.gender,
        )
        self._apply_age(member, data.date_of_birth, data.age)
        self._patients.add(member)
        self._db.commit()
        self._db.refresh(member)
        logger.info("Family member added: account=%s member=%s", account.id, member.id)
        return PatientProfile.model_validate(member)

    def update_member(
        self, account: PatientAccount, member_id: uuid.UUID, data: MemberUpdateRequest
    ) -> PatientProfile:
        member = self._require_member(account, member_id)

        if data.relationship is not None:
            if data.relationship == PatientRelationship.SELF:
                raise ApiException(
                    400, "A family member cannot be set to self", "INVALID_RELATIONSHIP"
                )
            member.relationship = data.relationship
        if data.full_name is not None:
            member.full_name = data.full_name
        if data.phone_number is not None:
            member.phone_number = data.phone_number or account.phone_number
        fields = data.model_dump(exclude_unset=True)
        if "email" in fields:
            member.email = data.email
        if "gender" in fields:
            member.gender = data.gender
        if "date_of_birth" in fields or "age" in fields:
            self._apply_age(
                member,
                data.date_of_birth if "date_of_birth" in fields else member.date_of_birth,
                data.age if "age" in fields else member.age,
            )

        self._db.commit()
        self._db.refresh(member)
        return PatientProfile.model_validate(member)

    def delete_member(self, account: PatientAccount, member_id: uuid.UUID) -> None:
        member = self._require_member(account, member_id)
        if self._patients.has_appointments(member.id):
            raise ApiException(
                409,
                "This member has appointments and cannot be removed.",
                "MEMBER_HAS_APPOINTMENTS",
            )
        self._patients.delete(member)
        self._db.commit()
        logger.info("Family member removed: account=%s member=%s", account.id, member_id)

    # -------------------------------------------------------- appointments
    def list_appointments(self, account: PatientAccount) -> list[MyAppointmentItem]:
        appointments = self._appointments.list_for_account(account.id)
        return [
            MyAppointmentItem(
                id=a.id,
                appointment_number=a.appointment_number,
                token_number=a.token_number,
                appointment_status=a.appointment_status,
                patient_id=a.patient_id,
                patient_name=a.patient.full_name,
                doctor_name=a.doctor_name,
                clinic_name=a.clinic_name,
                clinic_address=a.clinic_address,
                consultation_fee=a.consultation_fee,
                appointment_date=a.appointment_date,
                start_time=a.start_time,
                end_time=a.end_time,
            )
            for a in appointments
        ]

    # ------------------------------------------------------------ internals
    def _require_member(self, account: PatientAccount, member_id: uuid.UUID) -> Patient:
        member = self._patients.get_for_account(account.id, member_id)
        if member is None or member.relationship == PatientRelationship.SELF:
            raise ApiException(404, "Family member not found", "NOT_FOUND")
        return member

    def _apply_age(self, patient: Patient, dob, age) -> None:
        """Keep date_of_birth and age consistent — DOB wins when both are given."""
        patient.date_of_birth = dob
        if dob is not None:
            patient.age = age_from_dob(dob)
        else:
            patient.age = age
