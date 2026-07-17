import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dashboards call the booking backend. In dev we proxy /api to the real FastAPI
// backend (8000) so the frontend talks to one service; override with BACKEND_URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.BACKEND_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
