import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { LauncherScreen } from "./screens/LauncherScreen";
import { DoctorScreen } from "./screens/DoctorScreen";
import { LabScreen } from "./screens/LabScreen";
import { CashierScreen } from "./screens/CashierScreen";
import "./styles.css";

// Every board is its own standalone screen — no shared shell, no sidebar.
// Each one is meant to be opened on its room's computer and left running.
const router = createBrowserRouter([
  { path: "/", element: <LauncherScreen /> },
  { path: "/doctor", element: <DoctorScreen /> },
  { path: "/lab", element: <LabScreen /> },
  { path: "/cashier", element: <CashierScreen /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
