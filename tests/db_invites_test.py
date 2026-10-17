"""Tests for part 9: invites that can be revoked, and the team list with invite times. Fresh database."""
import json, psycopg2, admin_session
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a); return cur.fetchall() if cur.description else None
def as_(uid, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, uid),)); cur.execute("set role authenticated")
    try: cur.execute(q, a); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def err(uid, q, a=()):
    try: as_(uid, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def user(e, n): return su("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("a@t", "Ann"); su("insert into admins values (%s,'Ann')", (A,)); O = user("o@t", "Owner")
g = as_(A, "select admin_add_garage(%s,'o@t','Owner','','test')", (json.dumps({"name": "Musa Body", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "x", "phone": "1", "registration_no": "r"}),))[0][0]
as_(O, "select garage_sign_in()")
check("owner active", su("select status from garage_members where user_id=%s", (O,))[0][0] == "active")
check("add member without account", as_(O, "select add_garage_member('new@t','New','','inspector')")[0][0] == "invite_waiting_for_signup")
team = [r[0] for r in as_(O, "select garage_team(null)")]
inv = [t for t in team if t["email"] == "new@t"][0]
check("team shows invite as not_sent", inv["kind"] == "invite" and inv["status"] == "not_sent")
own = [t for t in team if t["email"] == "o@t"][0]
check("team member row has expiry field", "link_expires_at" in own)
I = user("i@t", "Insp"); su("insert into garage_members (garage_id,user_id,role,status) values (%s,%s,'inspector','active')", (g, I))
check("inspector can't revoke", "owner can revoke" in (err(I, "select revoke_garage_invite(%s)", (inv["id"],)) or ""))
as_(O, "select revoke_garage_invite(%s)", (inv["id"],))
check("revoked invite leaves the team list", not [t for t in (r[0] for r in as_(O, "select garage_team(null)")) if t["email"] == "new@t"])
check("revoking twice is refused", "no longer waiting" in (err(O, "select revoke_garage_invite(%s)", (inv["id"],)) or ""))
N = user("new@t", "New")
check("sign-up after revoke makes no membership", su("select count(*) from garage_members where user_id=%s", (N,))[0][0] == 0)
check("revoke is in the audit log", su("select count(*) from audit_log where action='invite revoked'")[0][0] == 1)
as_(O, "select add_garage_member('later@t','Later','','inspector')")
inv2 = [t for t in (r[0] for r in as_(A, "select garage_team(%s)", (g,))) if t["email"] == "later@t"][0]
as_(A, "select revoke_garage_invite(%s)", (inv2["id"],))
check("admin can revoke", su("select revoked_at is not null from garage_invites where id=%s", (inv2["id"],))[0][0])
check("anon can't call revoke", su("select has_function_privilege('anon','public.revoke_garage_invite(uuid)','execute')")[0][0] is False)
print(f"\n{ok} passed, {bad} failed")
