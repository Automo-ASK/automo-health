import "dotenv/config";

// AI_SERVICE_URL points at the *base* of Adam's AI service. His service is
// currently mounted inside the backend, so this is the backend base URL
// (e.g. http://localhost:8000); the client appends /api/v1/ai/interpret.
// Leave it empty to use the built-in local stub (deterministic, offline).
export const config = {
  port: Number(process.env.PORT ?? 3001),
  evolutionUrl: (process.env.EVOLUTION_API_URL ?? "http://localhost:8080").replace(/\/$/, ""),
  evolutionKey: process.env.EVOLUTION_API_KEY ?? "change-me-automo-evolution-key",
  instance: process.env.EVOLUTION_INSTANCE ?? "automo",
  webhookUrl: process.env.PUBLIC_WEBHOOK_URL ?? "http://host.docker.internal:3001/webhook/evolution",
  backendUrl: (process.env.BACKEND_URL ?? "http://localhost:3002").replace(/\/$/, ""),
  aiServiceUrl: (process.env.AI_SERVICE_URL ?? "").replace(/\/$/, ""),
  aiMaxHistoryTurns: Number(process.env.AI_MAX_HISTORY_TURNS ?? 10),
};
