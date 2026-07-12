# frontend — staff dashboards

**Owner: Quadri** · Stack: React + Vite + TypeScript · Port: `5173`

The three thin staff web screens: **doctor**, **lab**, **cashier**. One screen
per role, per the PRD §9. This is not an EMR — scheduling and flow only.

## Responsibility

- Doctor: the day's queue, who is next, close a visit with the three states
  (Done / Follow-up booked / Admitted), queue advances on Done.
- Lab: incoming tests, mark ready, set collection date.
- Cashier: who came / who is expected, owed vs cleared, daily revenue.

## Consumes

Only the **Booking API** (`docs/contracts/booking-api.md`). No direct DB access,
no channel logic. In dev, Vite proxies `/api` → the stub on `:3002`
(`vite.config.ts`). Point at Koded's real backend by setting `BACKEND_URL`.

## Layout

```
src/
├── main.tsx           router + routes
├── AppShell.tsx       sidebar nav shell
├── api.ts             Booking API client (the ONE place that fetches)
├── styles.css         design tokens + components
└── screens/           DoctorScreen · LabScreen · CashierScreen
```

## Run

```bash
npm run dev -w frontend       # or `npm run dev` at root for everything
```

## Sprint

Day 1 scaffold ✅ · Day 5 doctor screen on the real API · Day 6 lab + cashier.
