// Cashier screen — scaffolded for day 1. Full flow (who came / who is expected,
// owed vs cleared, daily revenue) is built later in the sprint.
import { useEffect, useState } from "react";
import { naira } from "../api";

export function CashierScreen() {
  const [services, setServices] = useState<Array<{ id: string; name: string; fee: number }>>([]);

  useEffect(() => {
    fetch("/api/v1/services")
      .then((r) => (r.ok ? r.json() : []))
      .then(setServices)
      .catch(() => setServices([]));
  }, []);

  return (
    <div className="screen">
      <header className="screen-head">
        <div>
          <h1>Cashier</h1>
          <p className="muted">Who came, who is expected, what has cleared</p>
        </div>
      </header>

      <section className="list">
        <div className="list-head">Facility price list</div>
        {services.length === 0 && <div className="empty">No services loaded — is the stub running on :3002?</div>}
        {services.map((s) => (
          <div className="row" key={s.id}>
            <span className="row-name">{s.name}</span>
            <span className="row-time">{naira(s.fee)}</span>
          </div>
        ))}
      </section>
      <p className="hint">
        Consultation revenue and reconciliation land here later. The Automo platform fee is separate and not shown to the facility.
      </p>
    </div>
  );
}
