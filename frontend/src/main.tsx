import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { AppShell } from "./AppShell";
import { DoctorScreen } from "./screens/DoctorScreen";
import { LabScreen } from "./screens/LabScreen";
import { CashierScreen } from "./screens/CashierScreen";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/doctor" replace /> },
      { path: "doctor", element: <DoctorScreen /> },
      { path: "lab", element: <LabScreen /> },
      { path: "cashier", element: <CashierScreen /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
