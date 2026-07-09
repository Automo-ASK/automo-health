# channels/whatsapp — WhatsApp channel

**Owner: Quadri** · Stack: Node + TypeScript + Express · Port: `3001`

The WhatsApp booking channel. Runs on **Evolution API** (Baileys, self-hosted)
— not WhatsApp Cloud API, for now. Receives inbound messages via webhook,
sends replies, and drives the natural booking conversation.

## Responsibility

- Receive Evolution webhooks, keep per-thread conversation state.
- Ask `ai-service` to interpret each message (intent + entities + reply).
- Call the **Booking API** for real services, slots, holds, pay links.
- Send the in-chat pay link; fold the payment confirmation back into the thread.

The AI phrases; the backend is the truth. Never invent a slot, fee, or "you're booked".

## Consumes

- `ai-service` (`docs/contracts/ai-service.md`) — via `AI_SERVICE_URL`. Empty →
  built-in local stub client (`src/aiClient.ts`) so this works before Adam's
  service is live.
- Booking API (`docs/contracts/booking-api.md`) — via `BACKEND_URL` (stub on day 1).
- Evolution API — via `EVOLUTION_API_URL` + `EVOLUTION_API_KEY`.

## Layout

```
src/
├── index.ts          Express server: /webhook/evolution, /send, /instance/*
├── config.ts         env
├── evolution.ts      Evolution API v2 client (create instance, QR, send)
├── provision.ts      `npm run provision` — link the WhatsApp number (QR)
├── aiClient.ts       AI service client + local stub
├── backend.ts        Booking API client
├── conversation.ts   per-thread state (in-memory, day 1)
└── handler.ts        the message flow
```

## Run

```bash
cp .env.example .env          # set EVOLUTION_API_KEY to match root .env
npm run evolution:up          # (root) start Evolution + Postgres + Redis
npm run dev -w channels/whatsapp
npm run provision             # (root) scan the QR to link the number
```

WhatsApp Web version is pinned in the root `.env` (`WA_WEB_VERSION`) to avoid
Baileys connection bugs. See root README for the no-phone webhook test.

## Sprint

Day 1 connect + echo/menu ✅ · Day 2 conversation state + intent · Day 3 booking
happy path · Day 4 pay link + webhook back into thread.
