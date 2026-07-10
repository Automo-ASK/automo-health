# Automo Health — Backend

FastAPI service for booking, slots, appointments, and payments (Paystack).

## Stack

- **FastAPI** — HTTP API
- **SQLAlchemy 2.0** + **Alembic** — ORM & migrations (Postgres)
- **Celery** + **Redis** — slot hold-and-expiry, booking expiry (Day 2)
- **Paystack** — payment provider

## Layout

```
app/
  main.py            # FastAPI app + /health
  core/
    config.py        # settings (pydantic-settings, reads .env)
    database.py      # engine + get_db() session dependency
    celery_app.py    # Celery app + beat schedule (Day 2 tasks)
  models/            # SQLAlchemy models (the Postgres schema)
    enums.py         # slot/booking/appointment/payment statuses
  schemas/           # Pydantic request/response contracts
  api/
    __init__.py      # aggregates all routers under /api/v1
    routes/          # slots, bookings, appointments, payments
alembic/             # migration environment + versions
```

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # if not already present
pip install -r requirements.txt
cp .env.example .env        # then fill in DATABASE_URL + Paystack keys
```

## Database migrations

```bash
alembic upgrade head                        # apply migrations
alembic revision --autogenerate -m "msg"    # create a new migration from model changes
```

## Run

```bash
uvicorn app.main:app --reload
```

- API docs (Swagger): http://localhost:8000/docs
- OpenAPI spec: http://localhost:8000/openapi.json
- Health: http://localhost:8000/health

## Data model

`patients`, `providers`, `services`, `slots`, `bookings`, `appointments`, `payments`.

- **Slot** lifecycle: `open → held → booked` (or back to `open` on hold expiry);
  carries `hold_expires_at` and a `version_id` for optimistic locking.
- **Booking** is created as `pending_payment`, snapshots the price, and has an
  `expires_at` deadline. On successful payment it becomes `confirmed`, the slot
  flips to `booked`, and an **Appointment** is created.
- **Payment** brokers a Paystack transaction (`reference`, `authorization_url`),
  reconciled via verify + webhook.
- Money is stored as integer **minor units** (kobo for NGN).

## Celery worker

The hold-and-expiry sweeps run under Celery beat (schedule in
`app/core/celery_app.py`). With Redis running:

```bash
celery -A app.core.celery_app.celery_app worker --beat --loglevel=info
```

- `app.tasks.slots.release_expired_holds` — returns standalone expired holds to OPEN
- `app.tasks.bookings.expire_unpaid_bookings` — expires unpaid bookings, abandons
  their payment, releases the slot

## Status

**Day 1 (done):** Postgres schema, FastAPI scaffold, published API contract.

**Day 2 (done):** slots/availability engine (open/held/booked) with row-level slot
locking (`SELECT ... FOR UPDATE` + `version_id`) and Celery hold-and-expiry; create
booking as `pending_payment` (snapshots price, holds slot, initializes Paystack).
Verified end-to-end against Neon, incl. double-booking rejection (`409`) and both
expiry sweeps.
