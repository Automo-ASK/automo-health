import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dashboards call the booking backend. In dev we proxy /api to the stub (3002)
// to avoid CORS; in prod this points at Koded's service.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.BACKEND_URL ?? "http://localhost:3002",
        changeOrigin: true,
      },
    },
  },
});
