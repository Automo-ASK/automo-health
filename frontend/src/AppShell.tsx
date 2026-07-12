import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/doctor", label: "Doctor", icon: "🩺" },
  { to: "/lab", label: "Lab", icon: "🧪" },
  { to: "/cashier", label: "Cashier", icon: "🧾" },
];

export function AppShell() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">A</span>
          <div>
            <div className="brand-name">Automo Health</div>
            <div className="brand-sub">Staff · V1</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}
            >
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">Lagos General · Single facility</div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
