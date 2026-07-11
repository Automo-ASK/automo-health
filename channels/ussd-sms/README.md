# channels/ussd-sms — USSD & SMS channels + notifications

**Owner: Adam** · Stack: Africa's Talking (USSD + SMS) · Port: served by the backend

> ⚠️ **Where the code actually lives:** Adam implemented USSD + SMS **inside the
> backend app**, not here — see `backend/app/api/routes/ussd.py`,
> `backend/app/api/routes/sms.py`, `backend/app/services/africastalking.py`, and
> `backend/app/services/ussd_session.py`. Webhooks:
> `POST /api/v1/channels/ussd` and `POST /api/v1/channels/sms/inbound`. This
> directory is kept as the charter/spec only.

> Charter for the USSD and SMS channels and the outbound notification sender.
> Mirrors `channels/whatsapp` (Quadri's) — same Booking API + AI service, different
> transport. Look at the WhatsApp service for the pattern.

## Responsibility

- **USSD (book only):** shallow, fast menu; session under ~120s; default to the
  next available slot rather than long lists. Language choice. Book via the
  Booking API. Never block the session on payment — payment details go out by SMS
  and confirmation returns asynchronously.
- **SMS (book + update):** two-way stateful conversation using `ai-service`, same
  natural flow as WhatsApp carried over plain text.
- **Notifications (out):** payment instructions, confirmations, reminders,
  reschedule/cancel, results-ready. USSD bookers receive **everything by SMS**
  (USSD can't push). This is the sender the backend's notification hooks call.

## Consumes

- `ai-service` (`docs/contracts/ai-service.md`) — for SMS conversation and the
  USSD free-text step.
- Booking API (`docs/contracts/booking-api.md`) — slots, holds, virtual-account
  payments (`POST /api/v1/payments/virtual-account`).

## Key rule

USSD is different: keep it a structured menu (session limit + short messages).
WhatsApp and SMS are the natural-conversation channels; USSD is speed and clarity.

## Sprint

Day 1 set up Africa's Talking + scaffold · Day 3 USSD flow · Day 4 SMS
conversational flow · Day 5 notifications + the USSD-to-SMS payment path.
