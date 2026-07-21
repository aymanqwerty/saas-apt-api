from fastapi import APIRouter

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard")


@router.get("", response_model=ApiResponse[DashboardSummary])
def get_dashboard(doctor: CurrentDoctor, db: DbSession) -> ApiResponse[DashboardSummary]:
    return ApiResponse(data=DashboardService(db).get_summary(doctor.id))
