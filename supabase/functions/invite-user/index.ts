// invite-user: sends a Saaz invite email ("set your password") to someone added as a garage owner or member.
// Called from the Saaz app. Runs on Supabase's servers; the service key never leaves them.
// Allowed callers: an admin signed in with their authenticator, or the active owner of a certified garage the invite belongs to.
import { createClient } from "npm:@supabase/supabase-js@2.50.0";   // pinned (30 Oct 2026): same version as the site, past GHSA-8r88-6cj9-9fh5

// 30 Oct 2026: browsers may call this only from the Saaz site (the token is still what authorises the call).
const SITE = (Deno.env.get("SAAZ_SITE_URL") ?? "https://jamesssemujju.github.io/saaz/").replace(/\/?$/, "/");
const cors = {
  "Access-Control-Allow-Origin": new URL(SITE).origin,
  "Vary": "Origin",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const reply = (status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return reply(405, { error: "POST only." });

  const url = Deno.env.get("SUPABASE_URL")!;
  const asCaller = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const server = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });

  const { data: who } = await asCaller.auth.getUser();
  if (!who?.user) return reply(401, { error: "Please sign in first." });

  let body: { email?: string; redirectTo?: string };
  try { body = await req.json(); } catch { return reply(400, { error: "Send JSON." }); }
  const email = String(body.email ?? "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return reply(400, { error: "Enter a valid email." });

  // Find what is waiting for this email: an invite with no account yet, or a member who hasn't started yet (status invited).
  const { data: invite } = await server.from("garage_invites").select("id, garage_id, name").eq("email", email).eq("used", false)
    .is("revoked_at", null).order("created_at", { ascending: false }).limit(1).maybeSingle();
  const { data: profile } = await server.from("profiles").select("id, name").eq("email", email).maybeSingle();
  const { data: member } = profile
    ? await server.from("garage_members").select("garage_id").eq("user_id", profile.id).eq("status", "invited").maybeSingle()
    : { data: null };
  const garageId = invite?.garage_id ?? member?.garage_id;
  if (!garageId) return reply(404, { error: "No waiting invite for this email." });
  // Admin only counts when this session passed the admin's pinned authenticator: the database decides (is_admin, part 10)
  const { data: isAdmin } = await asCaller.rpc("is_admin");
  const admin = isAdmin === true;
  // Owners can send invites only once Saaz has certified their garage (same rule as add_garage_member, part 12)
  const { data: garage } = await server.from("garages").select("status").eq("id", garageId).maybeSingle();
  const { data: ownerRow } = await server.from("garage_members").select("id").eq("user_id", who.user.id)
    .eq("garage_id", garageId).eq("role", "owner").eq("status", "active").maybeSingle();
  const owner = ownerRow && garage?.status === "certified";
  if (!admin && !owner) return reply(403, { error: "Only an admin, or the owner of a certified garage, can send this invite." });

  // 30 Oct 2026 (security): the email link may only lead back to Saaz. Anything else is dropped and Supabase uses the Site URL.
  const redirectTo = typeof body.redirectTo === "string" && body.redirectTo.startsWith(SITE) ? body.redirectTo : undefined;
  // At most 20 invite emails an hour per person sending them (each one is a real email; Supabase also caps emails project-wide)
  const since = new Date(Date.now() - 3600_000).toISOString();
  const { count: sentLastHour } = await server.from("audit_log").select("id", { count: "exact", head: true })
    .eq("actor_id", who.user.id).in("action", ["invite email sent", "set-password email sent"]).gte("at", since);
  if ((sentLastHour ?? 0) >= 20) return reply(429, { error: "Too many invites in the last hour. Try again later." });
  let kind = "invite";
  let { error } = await server.auth.admin.inviteUserByEmail(email, { data: { name: invite?.name ?? profile?.name ?? "" }, redirectTo });
  if (error && member && /already been registered|already exists/i.test(error.message)) {
    // The account exists and its email is confirmed, but they never set up: send a set-password (recovery) link instead
    kind = "password_link";
    ({ error } = await server.auth.resetPasswordForEmail(email, { redirectTo }));
  }
  if (error) {
    const exists = /already been registered|already exists/i.test(error.message);
    if (!exists) console.error("invite-user:", error.message);   // details stay in the function logs, not in the page
    return reply(exists ? 409 : 500, { error: exists ? "This email already has a Saaz account. Ask them to sign in." : "The invite email couldn't be sent. Try again in a few minutes." });
  }
  await server.from("audit_log").insert({ actor_id: who.user.id, actor_role: admin ? "admin" : "garage", entity: "member",
    entity_id: email, action: kind === "invite" ? "invite email sent" : "set-password email sent", detail: { garage: garageId } });
  return reply(200, { sent: true, kind });
});
