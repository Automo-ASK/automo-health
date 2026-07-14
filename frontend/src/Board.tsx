import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export type Role = "doctor" | "lab" | "cashier";

const FACILITY = "Lagos General";

/**
 * Chrome shared by the standalone boards: a full-width role-colour band that
 * identifies the screen from across the room, then the board's own content.
 * The band's colour comes from the `board--{role}` modifier in styles.css.
 */
export function Board({
  role,
  title,
  count,
  countLabel,
  bandExtra,
  children,
}: {
  role: Role;
  title: string;
  count: ReactNode;
  countLabel: string;
  bandExtra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`board board--${role}`}>
      <header className="band">
        <Link to="/" className="band-brand" aria-label="Back to all boards">
          <img src="/automo-mark-white.png" alt="" className="band-mark" />
          <span className="band-brand-text">
            <span className="band-brand-name">Automo Health</span>
            <span className="band-brand-sub">{FACILITY}</span>
          </span>
        </Link>
        <span className="band-rule" role="presentation" />
        <h1 className="band-title">{title}</h1>
        <div className="band-right">
          {bandExtra}
          <div className="band-count">
            <span className="band-count-num">{count}</span>
            <span className="band-count-label">{countLabel}</span>
          </div>
        </div>
      </header>
      <main className="board-main">{children}</main>
    </div>
  );
}

export const todayLong = () =>
  new Date().toLocaleDateString("en-NG", { weekday: "long", day: "numeric", month: "long" });

export const ticketNo = (position: number) => String(position).padStart(2, "0");
