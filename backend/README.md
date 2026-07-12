# Automo Health — Backend

A FastAPI service for booking, slots, appointments, and payments (Paystack).

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

## Payments (Paystack)

- **Booking init** — creating a booking initializes a Paystack transaction
  (`reference` + hosted `authorization_url`).
- **Per-booking virtual account** — `POST /payments/virtual-account` provisions a
  dedicated NUBAN (Paystack customer + dedicated account) so a patient can pay by
  bank transfer. `expected_amount` is snapshotted for exact-match reconciliation.
- **In-chat link** — `POST /payments/link` returns a shareable payload: hosted
  checkout URL + bank-transfer details + a ready-to-send `chat_message`.
- **Webhook** — `POST /payments/webhook` verifies the `x-paystack-signature`
  HMAC-SHA512, then reconciles `charge.success` events.
- **Reconciliation** (`app/services/reconciliation.py`) — resolves the payment by
  our `reference` or by the dedicated account; enforces an **exact-amount match**;
  idempotently confirms (booking → `confirmed`, slot → `booked`, appointment created,
  VA closed). Late payments (after expiry) are flagged, not double-booked.
- **Provider config** — `PAYMENT_PROVIDER` (`paystack`/`squad`). Without a real
  `PAYSTACK_SECRET_KEY`, the client runs in mock mode (fake accounts/verify/signature)
  so the whole flow is exercisable locally.

## Notifications

`app/services/notifications.py` dispatches domain events (`booking.created`,
`booking.confirmed`, `booking.expired`, `appointment.scheduled`, `payment.succeeded`,
`payment.mismatch`). Inline by default; set `NOTIFICATIONS_ASYNC=true` to enqueue via
Celery. If `NOTIFICATIONS_WEBHOOK_URL` is set, each event is POSTed there.

## Status

**Day 1 (done):** Postgres schema, FastAPI scaffold, published API contract.

**Day 2 (done):** slots/availability engine (open/held/booked) with row-level slot
locking (`SELECT ... FOR UPDATE` + `version_id`) and Celery hold-and-expiry; create
booking as `pending_payment`.

**Day 3 (done):** per-booking dedicated virtual accounts + in-chat payment link
generation (Paystack).

**Day 4 (done):** payment webhooks (HMAC-verified) and reconciliation — exact-amount
match, confirm the appointment, release on expiry; notification hooks fired. Verified
end-to-end against Neon (underpayment rejected, DVA-resolved confirm, idempotent
replay, late-payment guard, signature accept/reject).
