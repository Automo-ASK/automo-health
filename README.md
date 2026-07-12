# Automo Health — V1

Scheduling and patient-flow for Nigerian hospitals over **WhatsApp, USSD, and SMS**.
No app, no smartphone required. Patients book, pay, and arrive only at their slot.

This is the build-sprint monorepo. It is organised **by domain**, and every
directory has a README charter stating who owns it and what goes there.

## Who owns what

| Area | Path | Owner |
|------|------|-------|
| Staff dashboards (doctor / lab / cashier) | [`frontend/`](frontend/) | **Quadri** |
| WhatsApp channel (Evolution API) | [`channels/whatsapp/`](channels/whatsapp/) | **Quadri** |
| USSD + SMS + notifications | [`channels/ussd-sms/`](channels/ussd-sms/) | **Adam** |
| Shared conversational AI | [`ai-service/`](ai-service/) | **Adam** |
| Backend core + payments (FastAPI) | [`backend/`](backend/) | **Koded** |
| Booking API dev stub | [`backend-stub/`](backend-stub/) | shared |
| Locked API contracts | [`docs/contracts/`](docs/contracts/) | shared |

**New here? Read [`docs/architecture.md`](docs/architecture.md)** — the one-page
map of how these connect and where the demo data flows. Then open the README in
your own directory.

## The rule that keeps three people unblocked

Everyone builds against the two **locked contracts**, not against each other's
running code:

- [`docs/contracts/booking-api.md`](docs/contracts/booking-api.md) — Koded's
  backend. `backend-stub/` implements it today; `backend/` replaces it later at
  the same paths.
- [`docs/contracts/ai-service.md`](docs/contracts/ai-service.md) — Adam's AI
  service. Channels use a stub client until it's live.

Changing a contract? Raise it at standup and update the doc **first**.

## Directory tree

```
automo-health/
├── docker-compose.yml          # Evolution API + Postgres + Redis (WhatsApp gateway)
├── CODEOWNERS                  # path -> owner (set real GitHub handles)
├── docs/
│   ├── architecture.md         # the system map — start here
│   └── contracts/              # the two LOCKED contracts (source of truth)
├── frontend/                   # [Quadri] React staff dashboards            :5173
├── channels/
│   ├── whatsapp/               # [Quadri] Evolution API WhatsApp service     :3001
│   └── ussd-sms/               # [Adam]   Africa's Talking USSD + SMS        :3004
├── ai-service/                 # [Adam]   shared conversational AI           :3003
├── backend/                    # [Koded]  FastAPI core, slots, payments      :8000
└── backend-stub/               # [shared] dev stub of the Booking API        :3002
```

Node/TS apps (`frontend`, `channels/whatsapp`, `backend-stub`) are npm workspaces.
`backend`, `ai-service`, `channels/ussd-sms` are Python and run on their own.

## Prerequisites

- Node ≥ 20, npm ≥ 10
- Docker + Docker Compose (for Evolution API)
- A spare WhatsApp number to link as the demo line

## Setup

```bash
npm install                                            # all JS workspaces

cp .env.example .env                                   # docker / Evolution
cp channels/whatsapp/.env.example channels/whatsapp/.env
cp backend-stub/.env.example backend-stub/.env
#   -> set EVOLUTION_API_KEY to the same value in .env and channels/whatsapp/.env
```

## Run (the day-1 slice)

```bash
npm run evolution:up          # start Evolution + Postgres + Redis
npm run evolution:logs        # wait for "ready"

npm run dev                   # backend-stub :3002, whatsapp :3001, frontend :5173

npm run provision             # create the Evolution instance + print a QR to link
```

- Dashboard → http://localhost:5173
- WhatsApp health → http://localhost:3001/health
- Backend stub → http://localhost:3002/health

The WhatsApp Web version is pinned via `WA_WEB_VERSION=2.3000.1041645497` in
`.env` to avoid the Baileys connection bugs on newer WhatsApp builds.

After scanning the QR (WhatsApp → Linked devices), message the number — you get a
welcome listing the real services from the backend stub. That proves the loop:

```
patient ─▶ Evolution ─▶ /webhook/evolution ─▶ AI interpret (stub)
        ─▶ booking backend (stub) ─▶ reply ─▶ Evolution ─▶ patient
```

## Test without a phone

Simulate an inbound WhatsApp message straight to the webhook:

```bash
curl -X POST http://localhost:3001/webhook/evolution \
  -H 'Content-Type: application/json' \
  -d '{"event":"messages.upsert","instance":"automo","data":{"key":{"remoteJid":"2348012345678@s.whatsapp.net","fromMe":false,"id":"X"},"message":{"conversation":"I want to book an appointment"},"pushName":"Test"}}'
```

(The outbound send fails until a number is linked — expected; the receive → AI →
backend path still runs and logs.)

Simulate a payment confirmation (drives an appointment to `confirmed`):

```bash
curl -X POST http://localhost:3002/api/v1/payments/pay_001/simulate-webhook \
  -H 'Content-Type: application/json' -d '{"amount":510000}'
```

## Sprint at a glance

Day 1 contracts + scaffolds + WhatsApp connect ✅ · Day 2 conversation state + AI
service · Day 3 booking happy path + multilingual · Day 4 payments + webhooks ·
Day 5 doctor screen on real API · Day 6 full end-to-end · Day 7 polish + record.

## Notes

- The Postgres/Redis in `docker-compose.yml` belong to **Evolution only**. Koded's
  `backend/` runs its own Postgres.
- Money is in **kobo** (int); times in **WAT (+01:00)**.
- Use **sandbox / test** payment keys for the demo. Never real transfers on camera.
