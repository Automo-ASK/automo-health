# Architecture & ownership map

One picture of how Automo Health fits together, who owns each piece, and how the
pieces talk. Keep this current — it's the map everyone navigates by.

## Who owns what

| Area | Path | Owner | Consumes | Produces |
|------|------|-------|----------|----------|
| Staff dashboards | `frontend/` | **Quadri** | Booking API | Doctor / lab / cashier screens |
| WhatsApp channel | `channels/whatsapp/` | **Quadri** | AI service, Booking API | Inbound/outbound WhatsApp (Evolution API) |
| USSD + SMS | `channels/ussd-sms/` | **Adam** | AI service, Booking API | USSD menus, SMS conversations, notifications out |
| AI conversation service | `ai-service/` | **Adam** | Booking API (function-calling) | Intent + entities + phrased replies |
| Backend core + payments | `backend/` | **Koded** | Postgres, payment processor | The Booking API (source of truth) |
| Booking API stub | `backend-stub/` | shared (Quadri seeded) | — | Fake Booking API for days 1–4 |
| Contracts | `docs/contracts/` | shared | — | The two locked API shapes |

## The system

```
                        PATIENTS
        ┌──────────────┬──────────────┬──────────────┐
        │   WhatsApp   │     USSD     │     SMS      │
        ▼              ▼              ▼              
 ┌───────────────┐  ┌──────────────────────────────┐
 │  channels/    │  │        channels/             │
 │  whatsapp     │  │        ussd-sms              │
 │  [Quadri]     │  │        [Adam]                │
 │  Evolution API│  │        Africa's Talking      │
 └───────┬───────┘  └───────┬──────────────────────┘
         │                  │
         │  interpret/render│  (natural language in/out)
         ▼                  ▼
      ┌─────────────────────────┐
      │      ai-service         │   never owns the truth —
      │      [Adam]             │   language + phrasing only
      └───────────┬─────────────┘
                  │ function-calls for real data
   all channels ──┼── real slots / fees / holds / confirmations
                  ▼
      ┌─────────────────────────┐        ┌──────────────────┐
      │        backend          │◀──────▶│   Postgres       │
      │        [Koded]          │        │   + Celery       │
      │  slots · bookings ·     │        └──────────────────┘
      │  payments · webhooks ·  │
      │  notification hooks     │───▶ payment processor (Squad/Paystack)
      └───────────┬─────────────┘
                  │ Booking API (docs/contracts/booking-api.md)
                  ▼
      ┌─────────────────────────┐
      │       frontend          │   doctor / lab / cashier
      │       [Quadri]          │   read + close visits
      └─────────────────────────┘

  Notifications (confirmations, reminders, results) go OUT via
  channels/whatsapp + channels/ussd-sms. USSD bookers get everything by SMS.
```

## The two contracts (the only coupling that matters)

Everyone builds against these, not against each other's running code:

- **`docs/contracts/booking-api.md`** — Koded's Booking API. The `backend-stub`
  implements it exactly, so channels + frontend build before the real backend
  exists. Days 5–6 swap the stub for `backend/` at the same paths.
- **`docs/contracts/ai-service.md`** — Adam's AI service. WhatsApp and SMS both
  call it. Until it's live, `channels/whatsapp` uses a built-in stub client
  (swap via `AI_SERVICE_URL`).

**Rule:** if you need to change a contract, raise it at standup first. The
contract is the single source of truth; running services conform to it.

## Demo-slice data flow (what we film)

1. Patient messages WhatsApp → `channels/whatsapp` receives via Evolution webhook.
2. WhatsApp asks `ai-service` to interpret → intent `book`, needs real data.
3. WhatsApp calls `backend` for real services + open slots → phrases them via `ai-service`.
4. Patient picks a slot → `backend` holds it, creates a `pending_payment` appointment.
5. WhatsApp sends an in-chat pay link (`backend` → processor).
6. Processor webhook → `backend` confirms → appointment `confirmed`, slot `booked`.
7. Doctor works the queue in `frontend`; ticking **Done** advances it.

USSD mirrors 1–6 with a shallow menu and an SMS payment instruction instead of a link.
