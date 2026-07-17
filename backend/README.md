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

`patients`, `providers`, `services`, `slots`, `bookings`, `appointments`,
`payments`, `virtual_accounts`, `lab_orders`, `conversations`, `emergencies`.

> `providers` and `services` carry a stable **`slug`** (`prov_ade`, `svc_consult`)
> so the staff dashboards can address them by a fixed identifier that survives
> re-seeds. Dashboard-facing endpoints accept a slug **or** a UUID.

- **Slot** lifecycle: `open → held → booked` (or back to `open` on hold expiry);
  carries `hold_expires_at` and a `version_id` for optimistic locking.
- **Booking** is created as `pending_payment`, snapshots the price, and has an
  `expires_at` deadline. On successful payment it becomes `confirmed`, the slot
  flips to `booked`, and an **Appointment** is created. (Note: `bookings.slot_id`
  is unique — a slot maps to at most one booking row for its lifetime.)
- **Appointment** lifecycle: `scheduled → completed` (tick Done) / `no_show` /
  `cancelled`. Can be rescheduled onto another open slot, and carries an optional
  `parent_appointment_id` when created as a **follow-up**.
- **Payment** brokers a Paystack transaction (`reference`, `authorization_url`),
  reconciled via verify + webhook. Provider may also be `cash` (cashier desk).
- **LabOrder** — a test ordered off an appointment: `ordered → collected → resulted`.
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
- `app.tasks.payments.reverify_pending_payments` — safety-net re-verify of pending
  Paystack payments in case a webhook was missed (reconciliation is idempotent)

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

## Appointments & doctor actions

`app/services/appointments.py`, routed under `/appointments`:

- `GET /appointments` — filter by `patient_id` / `provider_id` / `status`.
- `POST /appointments/{id}/complete` — **tick Done** (optional clinician `notes`).
- `POST /appointments/{id}/no-show` — mark the patient a no-show.
- `POST /appointments/{id}/cancel` — cancel and release the slot back to OPEN.
- `POST /appointments/{id}/reschedule` — move onto another open slot (locks both
  slots, releases the old, books the new, repoints the booking).
- `POST /appointments/{id}/follow-up` — clinician-scheduled follow-up: books the
  chosen slot immediately (booking `confirmed`, appointment `scheduled`) and links
  back via `parent_appointment_id`. Any charge is settled at the desk.

## Cashier

`app/services/cashier.py`, routed under `/cashier` — front-desk cash/POS collection:

- `GET /cashier/outstanding` — the work queue of bookings still `pending_payment`.
- `POST /cashier/collect` — record a cash payment (exact amount enforced) and
  confirm the booking through the **same** reconciliation path as an online payment
  (booking `confirmed`, slot `booked`, appointment created; payment provider `cash`).

## Labs

`app/services/labs.py`, routed under `/labs`:

- `POST /labs/orders` — order a test against an appointment.
- `POST /labs/orders/{id}/collect` — mark the sample collected.
- `POST /labs/orders/{id}/result` — enter the result (`ordered → resulted`).
- `GET /labs/orders` — filter by appointment / patient / status.

## Staff dashboards (one backend)

The doctor / lab / cashier screens in `frontend/` consume **this** backend directly
(the throwaway `backend-stub` is retired). Endpoints, all under `/api/v1`:

- `GET /appointments?provider_id=<slug|uuid>` — a provider's live **queue**, enriched
  (position, is_next, patient, visit type, home reading / test details).
- `GET /appointments/day?date=` — every appointment on the day + still-owing holds
  (cashier). `POST /appointments/{id}/close` — Done / follow-up / Admitted (and the
  lab's collection date); advances the queue.
- `GET /slots?provider_id=<slug>&service_id=<slug>&include=all` — availability grid.
- `GET /payments?date=` — the day's cleared payments (cashier ledger).
- `GET /emergencies?status=open`, `POST /emergencies/{id}/ack`,
  `POST /emergencies/{id}/make-room` — PRD §8.6 seat-now / shift-the-queue.

Seed the dashboards (slug'd providers/services, a few days of slots, today's demo
queue + an emergency — idempotent):

```bash
python -m scripts.seed_dashboard
```

Run the pair (frontend proxies `/api` → `http://localhost:8000` by default):

```bash
uvicorn app.main:app --reload           # this backend, :8000
npm run dev -w frontend                  # dashboards, :5173  (from repo root)
```

## Channels & messaging

Inbound patient conversations arrive over WhatsApp, SMS (`/channels/sms/inbound`)
and USSD (`/channels/ussd`). Outbound patient-facing messages (booking confirmed,
rescheduled, cancelled, follow-up) route through `app/services/messaging.py`, which
sends SMS via Africa's Talking and logs WhatsApp/USSD (WhatsApp push is owned by the
conversation service). It degrades to logging when AT isn't configured or the patient
has no phone, so the flow stays exercisable offline.

## Notifications

`app/services/notifications.py` dispatches domain events: booking (`created`,
`confirmed`, `expired`), appointment (`scheduled`, `completed`, `cancelled`,
`rescheduled`, `no_show`, `follow_up`), payment (`succeeded`, `mismatch`, `overpaid`)
and lab (`ordered`, `resulted`). Inline by default; set `NOTIFICATIONS_ASYNC=true` to
enqueue via Celery. If `NOTIFICATIONS_WEBHOOK_URL` is set, each event is POSTed there.

## Tests & demo data

```bash
python -m scripts.seed_demo          # idempotent: providers, services, week of slots, patients
python -m pytest                     # edge cases: double-booking, under/over-payment, expiry,
                                     # lifecycle, cashier, labs (runs against DATABASE_URL)
python -m scripts.load_double_booking 12   # concurrency: N threads race one slot → exactly 1 wins
```

Tests run inside a per-test transaction that's rolled back on teardown (via
`join_transaction_mode="create_savepoint"`), so they leave no residue in the database.
Payments run in Paystack mock mode, so no network/keys are required.

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

**Day 5 (done):** appointment lifecycle & doctor actions — statuses, tick Done,
no-show, cancel (release slot), reschedule (move slot), follow-up creation (parent
link).

**Day 6 (done):** outbound messaging across channels (SMS via AT, WhatsApp/USSD
logged); payment hardening (over/under-payment distinguished, missed-webhook re-verify
sweep, `cash` provider); lab endpoints (`/labs`) and cashier endpoints (`/cashier`).

**Day 7 (done):** pytest edge suite (double-booking, under/over-payment, expiry,
lifecycle, cashier, labs — 17 tests) + threaded double-booking load test; idempotent
`seed_demo`. A merge migration (`b7f3c9d21a45`) unifies the two prior heads and adds
the appointment columns, `lab_orders`, and the `cash` provider value.
