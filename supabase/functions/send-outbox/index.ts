// send-outbox: sends the SMS waiting in the Saaz outbox through Africa's Talking (part 24).
// Runs on Supabase's servers. Called by the Saaz app after actions that create notices, and (optionally) every minute by
// Supabase Cron (supabase/marketplace_24b_send_outbox_schedule.sql). Calling it often is safe: each SMS is leased to one run.
// It sends only what the database queued (outbox_claim); callers can't choose numbers or text.
//
// Secrets (Supabase dashboard, Edge Functions, Secrets; never in code or chat):
//   AT_USERNAME   your Africa's Talking app username ("sandbox" uses the free test sandbox)
//   AT_API_KEY    that app's API key
//   AT_SENDER_ID  optional: the registered sender name (for example SAAZ). Without it Africa's Talking uses its default.
// Without AT_USERNAME and AT_API_KEY nothing is sent; SMS wait in the outbox and every notice is still in the app inbox.
import { createClient } from "npm:@supabase/supabase-js@2.50.0";   // same pinned version as invite-user

const SITE = (Deno.env.get("SAAZ_SITE_URL") ?? "https://jamesssemujju.github.io/saaz/").replace(/\/?$/, "/");
const cors = {
  "Access-Control-Allow-Origin": new URL(SITE).origin,
  "Vary": "Origin",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const reply = (status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

// Africa's Talking per-recipient status codes. Success: 100 Processed, 101 Sent, 102 Queued.
const OK = new Set([100, 101, 102]);
// The number itself can't receive: don't retry
const PERMANENT = new Set([403, 404, 406, 407, 409]);   // InvalidPhoneNumber, UnsupportedNumberType, UserInBlacklist, CouldNotRoute, DoNotDisturbRejection
// The account can't send right now (risk hold, sender name, balance, gateway): stop this run and put the rest back
const ACCOUNT = new Set([401, 402, 405, 500, 501, 502]);

type Row = { id: number; to: string; body: string; attempts: number };

export async function sendOne(row: Row, cfg: { user: string; key: string; from?: string; base: string }) {
  const form = new URLSearchParams({ username: cfg.user, to: row.to, message: row.body });
  if (cfg.from) form.set("from", cfg.from);
  let res: Response;
  try {
    res = await fetch(cfg.base + "/version1/messaging", {
      method: "POST",
      headers: { apiKey: cfg.key, Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
      signal: AbortSignal.timeout(15000),
    });
  } catch (e) {
    return { ok: false, permanent: false, account: true, error: "Network: " + String((e as Error).message ?? e).slice(0, 120) };
  }
  const text = await res.text();
  if (res.status === 401) return { ok: false, permanent: false, account: true, error: "Africa's Talking refused the API key (401)" };
  if (!res.ok) return { ok: false, permanent: false, account: true, error: `Africa's Talking HTTP ${res.status}` };
  let data: { SMSMessageData?: { Message?: string; Recipients?: { statusCode: number; status: string; messageId?: string; cost?: string }[] } };
  try { data = JSON.parse(text); } catch { return { ok: false, permanent: false, account: true, error: "Africa's Talking sent a reply that isn't JSON" }; }
  const r = data.SMSMessageData?.Recipients?.[0];
  if (!r) return { ok: false, permanent: false, account: true, error: "No recipient in reply: " + String(data.SMSMessageData?.Message ?? "").slice(0, 120) };
  if (OK.has(r.statusCode)) return { ok: true, id: r.messageId ?? null, cost: r.cost ?? null };
  return { ok: false, permanent: PERMANENT.has(r.statusCode), account: ACCOUNT.has(r.statusCode), error: `${r.statusCode} ${r.status}` };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return reply(405, { error: "POST only." });
  const server = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
  const user = Deno.env.get("AT_USERNAME") ?? "", key = Deno.env.get("AT_API_KEY") ?? "";
  if (!user || !key) {
    await server.rpc("outbox_run", { p_configured: false, p_claimed: 0, p_sent: 0, p_failed: 0, p_note: "Africa's Talking keys not set" });
    return reply(200, { configured: false });
  }
  const cfg = {
    user, key, from: Deno.env.get("AT_SENDER_ID") || undefined,
    // Test hook: AT_BASE_URL points at a local stand-in in tests. Unset in Supabase.
    base: Deno.env.get("AT_BASE_URL") ?? (user === "sandbox" ? "https://api.sandbox.africastalking.com" : "https://api.africastalking.com"),
  };
  const { data: rows, error } = await server.rpc("outbox_claim", { p_limit: 50 });
  if (error) { console.error("send-outbox claim:", error.message); return reply(500, { error: "Couldn't read the outbox." }); }
  let sent = 0, failed = 0, note: string | null = null;
  const list = (rows ?? []) as Row[];
  for (let i = 0; i < list.length; i++) {
    const r = await sendOne(list[i], cfg);
    if (r.ok) { sent++; await server.rpc("outbox_result", { p_id: list[i].id, p_ok: true, p_provider_id: r.id, p_cost: r.cost, p_error: null, p_permanent: false }); continue; }
    failed++;
    await server.rpc("outbox_result", { p_id: list[i].id, p_ok: false, p_provider_id: null, p_cost: null, p_error: r.error, p_permanent: r.permanent });
    if (r.account) {   // no point sending the rest now: put them back untouched
      note = "Stopped: " + r.error;
      const rest = list.slice(i + 1).map((x) => x.id);
      if (rest.length) await server.rpc("outbox_release", { p_ids: rest });
      break;
    }
  }
  await server.rpc("outbox_run", { p_configured: true, p_claimed: list.length, p_sent: sent, p_failed: failed, p_note: note });
  return reply(200, { configured: true, claimed: list.length, sent, failed, note });
});
