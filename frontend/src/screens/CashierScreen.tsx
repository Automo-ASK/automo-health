import { useEffect, useState, useCallback } from "react";
import { api, naira, timeOf, type PaymentRow, type DayRow } from "../api";
import { Board, todayLong } from "../Board";

const REFRESH_MS = 5000;

const SEEN = new Set(["done", "admitted"]);
const EXPECTED = new Set(["confirmed", "checked_in", "in_progress"]);

// The facility sees its own money. Platform fees are never shown here.
export function CashierScreen() {
  const [rows, setRows] = useState<PaymentRow[]>([]);
  const [day, setDay] = useState<DayRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [payments, dayRows] = await Promise.all([api.payments(), api.day()]);
      setRows(payments);
      setDay(dayRows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load payments");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const revenue = rows.reduce((sum, r) => sum + r.consultation_fee, 0);
  const seen = day.filter((d) => SEEN.has(d.status));
  const expected = day.filter((d) => EXPECTED.has(d.status));
  const owing = day.filter((d) => d.status === "pending_payment");
  const owed = owing.reduce((sum, d) => sum + d.consultation_fee, 0);

  return (
    <Board
      role="cashier"
      title="Cashier"
      count={naira(revenue)}
      countLabel={`${rows.length} paid today`}
    >
      <p className="context-line">
        <span className="context-date">{todayLong()}</span> — payments clear automatically via the
        webhook, on exact-amount match only. No manual checking.
      </p>

      {error && (
        <div className="banner-error" role="alert">
          Backend not reachable — {error}. Is the stub running on :3002?
        </div>
      )}

      {loading && (
        <div className="skeleton-list" aria-hidden="true">
          <i /><i /><i />
        </div>
      )}

      {!loading && !error && (
        <div className="stat-strip">
          <div className="stat">
            <span className="stat-num">{seen.length}</span>
            <span className="stat-label">came through</span>
          </div>
          <div className="stat">
            <span className="stat-num">{expected.length}</span>
            <span className="stat-label">still expected</span>
          </div>
          <div className="stat">
            <span className="stat-num">{owing.length ? naira(owed) : "—"}</span>
            <span className="stat-label">
              {owing.length
                ? `awaiting payment · ${owing.length} held`
                : "awaiting payment · none"}
            </span>
          </div>
        </div>
      )}

      {!loading && !error && (expected.length > 0 || owing.length > 0) && (
        <section className="panel" aria-label="Still expected">
          <div className="panel-head">Still expected</div>
          {[...expected, ...owing].map((d) => (
            <div className="qrow" key={d.id}>
              <span className="qrow-time">{timeOf(d.slot_time)}</span>
              <span className="qrow-name">{d.patient_name}</span>
              <span className="qrow-service">{d.service_name}</span>
              {d.status === "pending_payment" ? (
                <>
                  <span className="qrow-owes">owes {naira(d.consultation_fee)}</span>
                  <span className="chip chip-pending_payment">awaiting transfer</span>
                </>
              ) : (
                <span className={`chip chip-${d.status}`}>{d.status.replace("_", " ")}</span>
              )}
            </div>
          ))}
        </section>
      )}

      {!loading && !error && rows.length === 0 && (
        <div className="empty">
          No cleared payments yet today. They reconcile on their own — nothing to chase.
        </div>
      )}

      {rows.length > 0 && (
        <section className="panel" aria-label="Cleared payments">
          <div className="panel-head">Cleared today</div>
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Patient</th>
                  <th>Service</th>
                  <th>Method</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.payment_id}>
                    <td className="mono">{r.paid_at ? timeOf(r.paid_at) : "—"}</td>
                    <td className="strong">{r.patient_name}</td>
                    <td className="muted">{r.service_name}</td>
                    <td>
                      <span className="chip">{r.method === "link" ? "pay link" : "bank transfer"}</span>
                    </td>
                    <td className="num">{naira(r.consultation_fee)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={4}>Facility revenue</td>
                  <td className="num">{naira(revenue)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>
      )}

      <p className="foot-note">
        Amounts shown are the facility's consultation revenue.
      </p>
    </Board>
  );
}
