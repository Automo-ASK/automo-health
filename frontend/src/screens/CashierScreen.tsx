import { useEffect, useState, useCallback } from "react";
import { api, naira, timeOf, type PaymentRow } from "../api";

const REFRESH_MS = 5000;

// The facility sees its own money. Platform fees are never shown here.
export function CashierScreen() {
  const [rows, setRows] = useState<PaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setRows(await api.payments());
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
  const today = new Date().toLocaleDateString("en-NG", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="screen">
      <header className="screen-head">
        <div>
          <h1>Cashier</h1>
          <p className="muted">{today} · cleared automatically via the payment webhook</p>
        </div>
        <div className="count-pill">
          <span className="count-num">{naira(revenue)}</span>
          <span className="count-label">facility revenue · {rows.length} paid</span>
        </div>
      </header>

      {loading && <p className="muted">Loading today&apos;s payments…</p>}
      {error && <div className="banner error">Backend not reachable — {error}. Is the stub running on :3002?</div>}

      {!loading && !error && rows.length === 0 && (
        <div className="empty">No cleared payments yet today. They reconcile on their own — no manual checking.</div>
      )}

      {rows.length > 0 && (
        <section className="list">
          <div className="list-head">Cleared today</div>
          {rows.map((r) => (
            <div className="row" key={r.payment_id}>
              <span className="row-name">{r.patient_name}</span>
              <span className="row-service muted">{r.service_name}</span>
              <span className="row-time">{r.paid_at ? timeOf(r.paid_at) : "—"}</span>
              <span className="tag">{r.method === "link" ? "pay link" : "bank transfer"}</span>
              <span className="row-amount">{naira(r.consultation_fee)}</span>
            </div>
          ))}
        </section>
      )}
      <p className="hint">Amounts shown are the facility&apos;s consultation revenue. Payments confirm only on exact-amount match.</p>
    </div>
  );
}
