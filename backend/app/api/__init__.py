from fastapi import APIRouter

from app.api.routes import (
    ai_service,
    appointments,
    bookings,
    cashier,
    emergencies,
    labs,
    payments,
    providers,
    services,
    slots,
    sms,
    ussd,
)

api_router = APIRouter()
api_router.include_router(providers.router)
api_router.include_router(services.router)
api_router.include_router(slots.router)
api_router.include_router(bookings.router)
api_router.include_router(appointments.router)
api_router.include_router(payments.router)
api_router.include_router(cashier.router)
api_router.include_router(labs.router)
api_router.include_router(emergencies.router)
api_router.include_router(ai_service.router)
api_router.include_router(ussd.router)
api_router.include_router(sms.router)
