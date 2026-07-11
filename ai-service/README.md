# ai-service — shared conversational AI

**Owner: Adam** · Stack: Python (Gemini 2.5 Pro) · Port: served by the backend

> ⚠️ **Where the code actually lives:** Adam implemented this **inside the
> backend app**, not here — see `backend/app/services/ai_service.py`,
> `backend/app/schemas/ai_service.py`, and the route
> `backend/app/api/routes/ai_service.py` (`POST /api/v1/ai/interpret`). This
> directory is kept as the charter/spec only. The published contract is
> `docs/contracts/ai-service.md`.

> Charter for the shared AI service. Build it **once** — WhatsApp and SMS both
> call it. It is *not* built twice. Until it's live, `channels/whatsapp` uses a
> built-in stub client; point it here with `AI_SERVICE_URL` when ready.

## You own language, never the truth

Language detection, intent + entity extraction, and reply phrasing across
Nigerian languages. You do **not** own slots, fees, holds, payments, or
confirmations — you call the Booking API for real data and phrase what it returns.

- Multilingual: English, Pidgin, Yoruba, Hausa, Igbo (Lagos-first: en/pcm/yo).
  Detect per message, reply in the same language, handle code-switching.
- Natural, not a rigid menu. Tolerate slang, misspellings, out-of-order info.
- Ask for one missing thing at a time.
- **Guardrails:** never state availability/fees/confirmations not given in the
  data; no medical advice or triage; two failures → handoff or fallback menu.

## The contract you implement

`docs/contracts/ai-service.md` — **locked day 1**. Two endpoints:
`POST /ai/v1/interpret` (message → intent/entities/reply) and
`POST /ai/v1/render` (backend facts → phrased reply, so numbers are never invented).

## Consumed by

`channels/whatsapp` (Quadri) and `channels/ussd-sms` (Adam). Keep the contract
stable; both depend on it.

## Sprint

Day 1 define + publish the contract (done) · Day 2 build interpret/render,
multilingual, guardrails; test Yoruba + Pidgin and pick the model that handles them.
