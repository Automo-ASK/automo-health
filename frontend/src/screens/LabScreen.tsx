// Lab screen — scaffolded for day 1. Full flow (incoming tests, mark ready,
// set collection date) is built later in the sprint.
export function LabScreen() {
  return (
    <div className="screen">
      <header className="screen-head">
        <div>
          <h1>Lab</h1>
          <p className="muted">Incoming tests and results</p>
        </div>
      </header>
      <div className="empty">
        <p>Lab queue lands here: incoming tests with details attached, mark a test ready, set the collection date.</p>
        <p className="muted">Scaffolded on day 1 · built out later in the sprint.</p>
      </div>
    </div>
  );
}
