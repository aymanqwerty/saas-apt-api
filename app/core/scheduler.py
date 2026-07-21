import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database.session import SessionLocal
from app.services.booking_service import BookingService
from app.services.slot_generation_service import SlotGenerationService

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_daily_slot_maintenance() -> None:
    """Extend the rolling slot window and expire past slots (docs/02 §8)."""
    logger.info("Running daily slot maintenance")
    with SessionLocal() as db:
        try:
            SlotGenerationService(db).run_maintenance()
        except Exception:
            db.rollback()
            logger.exception("Slot maintenance failed")


def run_hold_expiry() -> None:
    """Release seats held for payments that were never completed in time."""
    with SessionLocal() as db:
        try:
            BookingService(db).expire_stale_holds()
        except Exception:
            db.rollback()
            logger.exception("Hold expiry sweep failed")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_daily_slot_maintenance,
        CronTrigger(hour=0, minute=30),
        id="daily_slot_maintenance",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_hold_expiry,
        IntervalTrigger(minutes=1),
        id="hold_expiry_sweep",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Background scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
