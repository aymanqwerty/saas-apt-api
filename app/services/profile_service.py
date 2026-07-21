from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.doctor import Doctor
from app.repositories.doctor_repository import DoctorRepository
from app.schemas.doctor import DoctorProfileUpdate


class ProfileService:
    # Columns that are NOT NULL in the database; an explicit null in the
    # request must be rejected rather than crash on commit.
    NON_NULLABLE_FIELDS = frozenset(
        {"full_name", "email", "phone_number", "specialization", "experience_years"}
    )

    def __init__(self, db: Session) -> None:
        self._db = db
        self._doctors = DoctorRepository(db)

    def update_profile(self, doctor: Doctor, data: DoctorProfileUpdate) -> Doctor:
        updates = data.model_dump(exclude_unset=True)

        for field in self.NON_NULLABLE_FIELDS & updates.keys():
            if updates[field] is None:
                raise ApiException(422, f"{field} cannot be empty", "VALIDATION_ERROR")

        new_email = updates.get("email")
        if new_email and new_email != doctor.email:
            existing = self._doctors.get_by_email(new_email)
            if existing and existing.id != doctor.id:
                raise ApiException(409, "Email is already in use", "CONFLICT")

        for field, value in updates.items():
            setattr(doctor, field, value)

        self._db.commit()
        self._db.refresh(doctor)
        return doctor
