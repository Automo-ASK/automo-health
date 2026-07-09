# Booking API Contract — v1 (LOCKED Day 1)

Owner: **Koded** (backend lead). Consumed by: WhatsApp service (Quadri), USSD/SMS
service (Adam), staff dashboards (Quadri).

> This is the single source of truth for the booking backend shape. During
> days 1–4 everyone codes against the stub in `apps/backend-stub`, which
> implements exactly this contract. Days 5–6 swap the stub for Koded's real
> FastAPI service at the same paths. **Changes go through the daily standup.**

Base URL (stub): `http://localhost:3002`
Prefix: `/api/v1`
Auth (real service): `Authorization: Bearer <service-token>` — the stub ignores it.
All money is in **kobo** (integer). All times are **WAT (UTC+1)**, ISO-8601.

---

## Health

`GET /health` → `200 { "status": "ok", "service": "backend-stub" }`

---

## Services

`GET /api/v1/services`

```json
[
  {
    "id": "svc_consult",
    "type": "consultation",
    "name": "General Consultation",
    "fee": 500000,
    "currency": "NGN",
    "duration_minutes": 20
  }
]
```

`type` ∈ `consultation | lab_test | virtual`.

---

## Slots

`GET /api/v1/slots?service_id=svc_consult&date=2026-07-10`

- `date` optional. Omitted → next available across the coming days.
- Returns only bookable (`open`) slots unless `?include=all`.

```json
[
  {
    "id": "slot_a1",
    "provider_id": "prov_ade",
    "provider_name": "Dr. Adeyemi",
    "service_id": "svc_consult",
    "start_time": "2026-07-10T09:00:00+01:00",
    "duration_minutes": 20,
    "status": "open"
  }
]
```

`status` ∈ `open | held | booked`.

`GET /api/v1/slots/next?service_id=svc_consult` → single next open slot (USSD default).

---

## Appointments

### Create (holds the slot)

`POST /api/v1/appointments`

```json
{
  "slot_id": "slot_a1",
  "service_id": "svc_consult",
  "type": "physical",
  "channel": "whatsapp",
  "patient": {
    "phone": "2348012345678",
    "name": "Chidi Okafor",
    "preferred_language": "en",
    "preferred_channel": "whatsapp",
    "consent": true
  }
}
```

`type` ∈ `physical | virtual | lab`. Creates/links the patient, **holds the
slot** (exclusive), creates the appointment as `pending_payment`, and starts
the hold-expiry clock (10–15 min).

`201`:

```json
{
  "id": "apt_001",
  "status": "pending_payment",
  "type": "physical",
  "patient_id": "pat_001",
  "slot": { "id": "slot_a1", "start_time": "2026-07-10T09:00:00+01:00", "provider_name": "Dr. Adeyemi" },
  "amount": 510000,
  "consultation_fee": 500000,
  "platform_fee": 10000,
  "currency": "NGN",
  "hold_expires_at": "2026-07-09T12:15:00+01:00"
}
```

Errors: `409 { "error": "slot_unavailable" }` if the slot was taken/expired.

### Read

`GET /api/v1/appointments/:id` → the appointment object above (with live `status`).

### Queue (doctor screen)

`GET /api/v1/appointments?date=2026-07-09&provider_id=prov_ade`

```json
[
  {
    "id": "apt_001",
    "position": 1,
    "is_next": true,
    "patient_name": "Chidi Okafor",
    "type": "physical",
    "service_name": "General Consultation",
    "slot_time": "2026-07-09T09:00:00+01:00",
    "status": "checked_in"
  }
]
```

`status` ∈ `pending_payment | confirmed | checked_in | in_progress | done | admitted | cancelled | no_show`.

### Close a visit (doctor action)

`POST /api/v1/appointments/:id/close`

```json
{ "state": "done" }
```

`state` ∈ `done | follow_up | admitted`. Per the reviewing doctor, `done`
fires only after consult + meds + next appointment are settled; the
next-appointment step sits **before** `done`. Closing advances the queue.

`200` → updated appointment; response includes `"next": { "id": "apt_002", ... } | null`.

---

## Payments

The AI/channel layer never decides money arrived — only the webhook does.

### WhatsApp: in-chat link

`POST /api/v1/payments/link`  `{ "appointment_id": "apt_001" }`

```json
{
  "payment_id": "pay_001",
  "method": "link",
  "url": "https://pay.squadco.com/checkout/AB12CD34",
  "amount": 510000,
  "currency": "NGN",
  "expires_at": "2026-07-09T12:15:00+01:00"
}
```

### USSD/SMS: one-time virtual account

`POST /api/v1/payments/virtual-account`  `{ "appointment_id": "apt_001" }`

```json
{
  "payment_id": "pay_002",
  "method": "ussd_transfer",
  "virtual_account": "9915042317",
  "bank": "Sterling Bank",
  "account_name": "AUTOMO/CHIDI OKAFOR",
  "amount": 510000,
  "currency": "NGN",
  "expires_at": "2026-07-09T12:15:00+01:00"
}
```

### Read

`GET /api/v1/payments/:id` → `{ payment_id, status, ... }`.
`status` ∈ `pending | paid | failed | expired`.

### Webhook (processor → backend)

`POST /api/v1/payments/webhook` — signature-verified in the real service.
Confirms **only on exact-amount match**; underpayment does not confirm and
triggers a notice; overpayment confirms and flags. On confirm: appointment →
`confirmed`, slot → `booked`, notification hook fires.

**Dev helper (stub only):** `POST /api/v1/payments/:id/simulate-webhook`
`{ "amount": 510000 }` — mimics the processor so channels can be tested
end-to-end without real money.
