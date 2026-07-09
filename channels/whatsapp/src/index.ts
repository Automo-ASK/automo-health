import express, { Request, Response } from "express";
import cors from "cors";
import { config } from "./config.js";
import { ensureInstance, setWebhook, connect, connectionState, sendText } from "./evolution.js";
import { handleIncoming } from "./handler.js";

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

const log = (...a: unknown[]) => console.log("[whatsapp]", ...a);

// ---- health ---------------------------------------------------------------

app.get("/health", (_req, res) =>
  res.json({ status: "ok", service: "whatsapp-service", instance: config.instance })
);

// ---- Evolution provisioning (idempotent) ----------------------------------
// One call: create the instance, wire the webhook, and return the QR to scan.
app.post("/instance/setup", async (_req: Request, res: Response) => {
  try {
    await ensureInstance();
    await setWebhook();
    const qr = await connect();
    if (qr.base64) log("QR ready — GET /instance/qr or scan the terminal QR from `npm run provision`.");
    res.json({ instance: config.instance, webhook: config.webhookUrl, qr });
  } catch (err) {
    handleErr(res, err, "setup_failed");
  }
});

app.get("/instance/qr", async (_req, res) => {
  try {
    const qr = await connect();
    res.json(qr);
  } catch (err) {
    handleErr(res, err, "qr_failed");
  }
});

app.get("/instance/state", async (_req, res) => {
  try {
    res.json({ instance: config.instance, state: await connectionState() });
  } catch (err) {
    handleErr(res, err, "state_failed");
  }
});

// Manual send, for testing the outbound path.
app.post("/send", async (req: Request, res: Response) => {
  const { to, text } = req.body ?? {};
  if (!to || !text) return res.status(400).json({ error: "to and text required" });
  try {
    await sendText(String(to), String(text));
    res.json({ sent: true, to });
  } catch (err) {
    handleErr(res, err, "send_failed");
  }
});

// ---- Evolution webhook ----------------------------------------------------

app.post("/webhook/evolution", async (req: Request, res: Response) => {
  // Ack immediately; process async so Evolution never times out.
  res.sendStatus(200);
  try {
    const event = String(req.body?.event ?? "").toLowerCase().replace(/_/g, ".");
    if (event !== "messages.upsert") return;

    const payloads = Array.isArray(req.body.data) ? req.body.data : [req.body.data];
    for (const msg of payloads) {
      const parsed = parseMessage(msg);
      if (!parsed) continue;
      log("in <-", parsed.jid, JSON.stringify(parsed.text));
      const answer = await handleIncoming(parsed.jid, parsed.text);
      await sendText(parsed.jid, answer);
      log("out ->", parsed.jid, JSON.stringify(answer.slice(0, 60)));
    }
  } catch (err) {
    log("webhook error:", err instanceof Error ? err.message : err);
  }
});

interface ParsedMsg {
  jid: string;
  text: string;
}

function parseMessage(msg: any): ParsedMsg | null {
  const key = msg?.key ?? {};
  if (key.fromMe) return null;
  const jid: string = key.remoteJid ?? "";
  if (!jid || jid.endsWith("@g.us") || jid.includes("status@broadcast")) return null; // no groups/status
  const m = msg?.message ?? {};
  const text: string =
    m.conversation ??
    m.extendedTextMessage?.text ??
    m.ephemeralMessage?.message?.extendedTextMessage?.text ??
    m.ephemeralMessage?.message?.conversation ??
    "";
  if (!text.trim()) return null;
  return { jid, text };
}

function handleErr(res: Response, err: unknown, code: string) {
  const detail =
    (err as any)?.response?.data ?? (err instanceof Error ? err.message : String(err));
  console.error("[whatsapp]", code, detail);
  res.status(502).json({ error: code, detail });
}

app.listen(config.port, () => {
  log(`listening on http://localhost:${config.port}`);
  log(`evolution: ${config.evolutionUrl}  instance: ${config.instance}`);
  log(`backend:   ${config.backendUrl}`);
  log(`ai:        ${config.aiServiceUrl || "(local stub)"}`);
  log(`Provision WhatsApp with:  npm run provision  (or POST /instance/setup)`);
});
