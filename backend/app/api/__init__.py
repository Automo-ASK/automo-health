from fastapi import APIRouter

from app.api.routes import ai_service, appointments, bookings, payments, slots, sms, ussd

api_router = APIRouter()
api_router.include_router(slots.router)
api_router.include_router(bookings.router)
api_router.include_router(appointments.router)
api_router.include_router(payments.router)
api_router.include_router(ai_service.router)
api_router.include_router(ussd.router)
api_router.include_router(sms.router)
