# AI Conversation Service Contract — v1 (LOCKED Day 1)

Owner: **Adam**. Consumed by: WhatsApp service (Quadri) and SMS service (Adam).

> Built once, called twice. WhatsApp and SMS both send raw patient text here and
> get back structured intent + entities + a suggested reply. **The AI never owns
> the truth** — slots, fees, holds, payments, and confirmations come from the
> Booking API. The model handles language and phrasing only.
>
> During days 1–2 the WhatsApp service codes against the **stub client** baked
> into `apps/whatsapp-service` (deterministic canned interpretation). Day 2 Adam
> publishes the real service at the paths below and we swap the client's base URL.

Base URL (real service): `http://localhost:3003` (TBD by Adam)
Prefix: `/ai/v1`

---

## Interpret a message

`POST /ai/v1/interpret`

Request:

```json
{
  "channel": "whatsapp",
  "message": "abeg I wan see doctor tomorrow morning",
  "conversation": {
    "id": "conv_123",
    "language": "pcm",
    "state": { "intent": "book", "entities": { "service": "consultation" } },
    "history": [
      { "role": "user", "text": "hello" },
      { "role": "assistant", "text": "Hi! How can I help you today?" }
    ]
  }
}
```

- `conversation` may be `null` on the first message.
- `channel` ∈ `whatsapp | sms | ussd`.

Response:

```json
{
  "language": "pcm",
  "intent": "book",
  "confidence": 0.91,
  "entities": {
    "service": "consultation",
    "provider": null,
    "preferred_day": "2026-07-10",
    "preferred_time": "morning",
    "patient_name": null
  },
  "missing": ["patient_name"],
  "reply": "No wahala 👍 Which name I go put for the booking?",
  "needs_backend": false,
  "handoff": false
}
```

Field meanings:

- `intent` ∈ `book | reschedule | cancel | question | greeting | unknown`.
- `language` — BCP-47-ish: `en | pcm (Pidgin) | yo | ha | ig`. Detected per
  message; supports code-switching. Reply is in the **same** language.
- `entities` — extracted so far; `null` where not yet known.
- `missing` — ordered list of entities still needed to complete the intent. The
  channel asks for **one at a time**, in this order.
- `reply` — human, warm, plain phrasing to send back. **Ask for at most one
  missing thing.** May be overridden by the channel when it needs to inject real
  backend data (slots/fees) — see next section.
- `needs_backend` — `true` when the next step requires real data (e.g. show
  slots, quote a fee). The channel then calls the Booking API and calls
  `render` below to phrase the result.
- `handoff` — `true` when the model failed twice / user asked for a human.

---

## Render a reply from backend facts

When `needs_backend` is true, the channel fetches real data and asks the AI to
phrase it (so numbers are never invented):

`POST /ai/v1/render`

```json
{
  "language": "pcm",
  "template": "offer_slots",
  "data": {
    "service": "General Consultation",
    "slots": [
      { "label": "Tomorrow 9:00am", "id": "slot_a1" },
      { "label": "Tomorrow 9:20am", "id": "slot_a2" }
    ]
  }
}
```

`template` ∈ `offer_slots | quote_fee | payment_link | payment_account |
confirmed | slot_taken | expired | reschedule_done | cancelled | fallback_menu`.

Response: `{ "reply": "I see two times tomorrow: 9:00am or 9:20am. Which one?" }`

---

## Guardrails (enforced by the service)

- Never state availability, a fee, or a confirmation that did not come from
  `render` `data`. No fabricated slots, prices, or "you're booked".
- No medical advice or triage. Scheduling only.
- On low confidence twice in a row → `handoff: true` or a `fallback_menu`.
- If the service is down, the channel falls back to a minimal guided path;
  booking must still work.

---

## Stub behaviour (Quadri's local client, days 1–2)

The WhatsApp service ships a stub implementing this contract deterministically:
greeting → `greeting`; anything with "book/appointment/see doctor" → `book` with
`needs_backend: true`; otherwise `unknown`. This lets the WhatsApp flow be built
before Adam's model is live, then swapped by pointing `AI_SERVICE_URL` at the
real service.
