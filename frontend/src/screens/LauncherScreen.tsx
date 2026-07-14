import { Link } from "react-router-dom";
import { IconArrowRight } from "../icons";

const BOARDS = [
  {
    to: "/doctor",
    role: "doctor",
    name: "Doctor",
    desc: "Today's consultation queue — who is in the chair, who is next.",
  },
  {
    to: "/lab",
    role: "lab",
    name: "Laboratory",
    desc: "Paid tests in arrival order — mark results ready to collect.",
  },
  {
    to: "/cashier",
    role: "cashier",
    name: "Cashier",
    desc: "Payments cleared today — reconciled automatically, exact-amount only.",
  },
];

export function LauncherScreen() {
  return (
    <div className="launcher">
      <div className="launcher-inner">
        <img src="/automo-mark.png" alt="Automo Health" className="launcher-mark" />
        <h1 className="launcher-title">Automo Health</h1>
        <p className="launcher-sub">Lagos General · Staff boards</p>

        <nav className="launcher-boards" aria-label="Boards">
          {BOARDS.map((b) => (
            <Link key={b.to} to={b.to} className={`board-card board-card--${b.role}`}>
              <span className="board-card-text">
                <span className="board-card-name">{b.name}</span>
                <span className="board-card-desc">{b.desc}</span>
              </span>
              <IconArrowRight className="board-card-arrow" />
            </Link>
          ))}
        </nav>

        <p className="launcher-foot">
          Each board is its own screen. Open it on the room's computer and leave it running —
          bookings from WhatsApp and USSD arrive on their own.
        </p>
      </div>
    </div>
  );
}
