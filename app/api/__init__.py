from fastapi import APIRouter

from app.api.agent import router as agent_router
from app.api.appointments import router as appointments_router
from app.api.auth import router as auth_router
from app.api.availability import router as availability_router
from app.api.bookings import router as bookings_router
from app.api.clinics import router as clinics_router
from app.api.dashboard import router as dashboard_router
from app.api.doctors import router as doctors_router
from app.api.gallery import router as gallery_router
from app.api.health import router as health_router
from app.api.internal import router as internal_router
from app.api.media import router as media_router
from app.api.patient_account import router as patient_account_router
from app.api.patient_auth import router as patient_auth_router
from app.api.patients import router as patients_router
from app.api.payments import router as payments_router
from app.api.public import router as public_router
from app.api.services import router as services_router
from app.api.settings import router as settings_router
from app.api.slots import router as slots_router
from app.api.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(patient_auth_router, tags=["patient-auth"])
api_router.include_router(patient_account_router, tags=["patient-account"])
api_router.include_router(doctors_router, tags=["doctors"])
api_router.include_router(media_router, tags=["media"])
api_router.include_router(clinics_router, tags=["clinics"])
api_router.include_router(services_router, tags=["services"])
api_router.include_router(availability_router, tags=["availability"])
api_router.include_router(slots_router, tags=["slots"])
api_router.include_router(public_router, tags=["public"])
api_router.include_router(bookings_router, tags=["bookings"])
api_router.include_router(appointments_router, tags=["appointments"])
api_router.include_router(payments_router, tags=["payments"])
api_router.include_router(patients_router, tags=["patients"])
api_router.include_router(gallery_router, tags=["gallery"])
api_router.include_router(settings_router, tags=["settings"])
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(agent_router, tags=["agent"])
api_router.include_router(webhooks_router, tags=["webhooks"])
api_router.include_router(internal_router)
