# backend-stub — dev stub of the Booking API

**Shared** (Quadri seeded it; Koded keeps it honest) · Node + TS · Port: `3002`

A throwaway, in-memory implementation of `docs/contracts/booking-api.md`. It
exists so the channels and frontend can build during days 1–4 without waiting
for Koded's real backend. **It is retired once `backend/` is live** — same paths,
so consumers don't change.

- No database, no real payments — data resets on restart.
- Includes a dev-only helper `POST /api/v1/payments/:id/simulate-webhook` to fake
  the processor and drive an appointment to `confirmed`.
- Seeds a small doctor queue for "today" so the dashboard has something to show.

If you change this, change `docs/contracts/booking-api.md` too — and tell Koded.

## Run

```bash
npm run dev -w backend-stub    # http://localhost:3002/health
```
