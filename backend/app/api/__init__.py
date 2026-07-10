from fastapi import APIRouter

from app.api.routes import appointments, bookings, payments, slots

api_router = APIRouter()
api_router.include_router(slots.router)
api_router.include_router(bookings.router)
api_router.include_router(appointments.router)
api_router.include_router(payments.router)
