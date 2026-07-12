# AI Conversation Service Contract — v1 (as published by Adam)

Owner: **Adam**. Consumed by: WhatsApp service (Quadri) and SMS (Adam).

> Built once, called by both channels. The AI owns language + intent + phrasing;
> the booking backend is the single source of truth for slots, fees, and payment
> confirmation. Reference implementation: `backend/app/services/ai_service.py`
> (Gemini 2.5 Pro) and schema `backend/app/schemas/ai_service.py`.
>
> The AI service is currently mounted **inside the backend** app, so its base URL
> is the backend base URL. WhatsApp uses a local stub with the same shape until
> `AI_SERVICE_URL` is pointed at it.

Endpoint: `POST {base}/api/v1/ai/interpret`

## Request

```json
{
  "message": "abeg I wan see doctor tomorrow morning",
  "channel": "whatsapp",
  "conversation_id": "wa_2348012345678",
  "history": [
    { "role": "user", "content": "hello" },
    { "role": "assistant", "content": "Hi! How can I help you today?" }
  ],
  "language_hint": null
}
```

- `channel` ∈ `whatsapp | sms | ussd`.
- `history` — prior turns, most recent last, capped ~10 by the caller.
- `language_hint` — optional prior language (e.g. a USSD language choice); else `null`.

## Response

```json
{
  "intent": "book",
  "language": "pidgin",
  "entities": {
    "service_type": "consultation",
    "provider_name": null,
    "preferred_day": "tomorrow",
    "preferred_time": "morning",
    "patient_name": null,
    "appointment_id": null
  },
  "reply": "No wahala 👍 Which name I go put for the booking?",
  "confidence": 0.91,
  "needs_clarification": true,
  "suggested_action": "show_slots"
}
```

Field meanings:

- `intent` ∈ `book | reschedule | cancel | query | unknown`.
- `language` ∈ `en | pidgin | yo` (Lagos-first; more added later). Detected per
  message; the reply is in the same language. Handles code-switching.
- `entities` — extracted so far; `null` where unknown. `service_type` ∈
  `consultation | lab_test | virtual`.
- `reply` — warm, concise message to send back, in the detected language. Never
  contains an invented slot time, fee, or payment confirmation.
- `confidence` — 0.0–1.0.
- `needs_clarification` — `true` when the reply asks for more info before acting.
- `suggested_action` — hint to the channel for the next step (may be `null`):
  `show_services | show_slots | confirm_booking | awaiting_payment | reschedule |
  cancel_booking | human_handoff`.

## Guardrails (enforced in the service)

- Never invents/assumes/confirms a slot; never states a fee not returned by the
  backend; never confirms a payment (only the webhook does); no medical advice.
- On failure the service returns a safe fallback reply with
  `suggested_action: "human_handoff"` — it never raises, so channels never hang.

## How the channel uses it

1. Send the inbound message + recent history → get `intent`, `entities`, `reply`.
2. If `suggested_action` needs real data (`show_services`, `show_slots`, …),
   call the **Booking API** for the facts, then send them (Day 3+). Until then,
   send `reply` as-is.
3. Persist the turn to conversation state so the patient never repeats themselves.
