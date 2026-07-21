import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.dependencies.database import DbSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health_check(db: DbSession) -> dict:
    database_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        database_status = "disconnected"

    return {
        "success": True,
        "message": "Success",
        "data": {"status": "ok", "database": database_status},
    }
