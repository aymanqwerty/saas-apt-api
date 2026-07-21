import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.activity_log_repository import ActivityLogRepository
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.gallery_repository import GalleryRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.appointment import AppointmentListItem
from app.schemas.dashboard import ActivityEntry, DashboardSummary

# "Today" for the summary is evaluated in a single reference timezone.
_REFERENCE_TZ = "Asia/Kolkata"


class DashboardService:
    def __init__(self, db: Session) -> None:
        self._appointments = AppointmentRepository(db)
        self._patients = PatientRepository(db)
        self._clinics = ClinicRepository(db)
        self._gallery = GalleryRepository(db)
        self._activity = ActivityLogRepository(db)

    def get_summary(self, doctor_id: uuid.UUID) -> DashboardSummary:
        today = datetime.now(ZoneInfo(_REFERENCE_TZ)).date()

        today_appointments = self._appointments.list_on_date(doctor_id, today)
        recent = self._activity.list_recent_for_doctor(doctor_id, limit=10)

        return DashboardSummary(
            today_count=len(today_appointments),
            upcoming_count=self._appointments.count_upcoming(doctor_id, today),
            total_patients=self._patients.count_for_doctor(doctor_id),
            total_clinics=self._clinics.count_active(doctor_id),
            published_posts=self._gallery.count_published(doctor_id),
            today_appointments=[AppointmentListItem.from_model(a) for a in today_appointments],
            recent_activity=[ActivityEntry.model_validate(e) for e in recent],
        )
