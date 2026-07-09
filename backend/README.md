# backend — booking core & payments

**Owner: Koded** · Stack: FastAPI (Python) + PostgreSQL + Celery · Port: `8000` (suggested)

> This directory is the charter for the real backend. It's yours to build. The
> `backend-stub/` at the repo root already implements the contract with fake
> data so everyone is unblocked — replace it here, keeping the **same paths**.

## You own the source of truth

Everything real lives here: slots, holds, bookings, payments, reconciliation,
appointment lifecycle, notification hooks. The AI and channels call you; they
never invent a slot, a fee, or a confirmation.

## The contract you implement

`docs/contracts/booking-api.md` — **locked day 1**. The stub matches it exactly;
your job is to make it real. If a change is needed, raise it at standup and
update the contract first.

Key rules baked into the contract (don't drift):
- Money in **kobo** (int). Times in **WAT (+01:00)**.
- Slot locking prevents double-booking; a held slot is exclusive until paid or expired.
- Hold expiry 10–15 min (Celery) releases unpaid holds.
- Payment confirms **only on exact-amount match** via webhook — never the AI/channel.
  Underpayment → notice, no confirm. Overpayment → confirm + flag.
- `done` fires only after consult + meds + next appointment are settled; the
  next-appointment step sits before `done`.

## Build from the PRD data model

PRD §12 (`C:\Users\USER\Downloads\Automo_Health_V1_PRD.docx`): Facility, Provider,
Service, Slot, Patient, Appointment, Payment, LabTest, EmergencyRequest,
Conversation, Notification.

## Suggested structure

```
backend/
├── pyproject.toml
├── app/
│   ├── main.py            FastAPI app
│   ├── api/v1/            services, slots, appointments, payments routers
│   ├── models/           SQLAlchemy models (PRD §12)
│   ├── schemas/          Pydantic request/response (mirror the contract)
│   ├── services/         slots engine, booking, payments, reconciliation
│   ├── workers/          Celery: hold expiry, reminders
│   └── db.py
└── alembic/              migrations
```

## Sprint

Day 1 schema + FastAPI scaffold + publish/confirm contract · Day 2 slots engine +
hold/expiry · Day 3 payments (Squad/Paystack, virtual accounts) · Day 4 webhooks +
reconciliation + notification hooks · Day 5 appointment lifecycle + doctor actions.
