from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.appointment import AppointmentListItem


class ActivityEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    entity: str
    description: str | None
    created_at: datetime


class DashboardSummary(BaseModel):
    today_count: int
    upcoming_count: int
    total_patients: int
    total_clinics: int
    published_posts: int
    today_appointments: list[AppointmentListItem]
    recent_activity: list[ActivityEntry]
