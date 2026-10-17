"""Tests for part 12: live session needed for writes, admin needs fresh password + pinned authenticator,
admin entry flag, failed checks logged, garage invite stages separate from certification. Fresh database."""
import json, time, psycopg2, admin_session
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def with_claims(c, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (c if isinstance(c, str) else json.dumps(c),)); cur.execute("set role authenticated")
    try: cur.execute(q, a or None); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def as_(uid, q, a=()): return with_claims(admin_session.claims(cur, uid), q, a)
def err(uid, q, a=()):
    try: as_(uid, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def cerr(c, q, a=()):
    try: with_claims(c, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def user(e, n): return su("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
now = int(time.time())

A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name) values (%s,'Ann Admin')", (A,))
S = user("seller@x.test", "Sam Seller"); B = user("buyer@x.test", "Bob Buyer")

# Sign-out ends access: the session row is gone, the token stops working for every write
sc = json.loads(admin_session.claims(cur, B))
check("buyer with a live session can write", cerr(sc, "select update_profile('Bob Buyer','UG','')") is None)
su("delete from auth.sessions where user_id=%s", (B,))  # what sign-out does
check("after sign-out the same token can't write", cerr(sc, "select update_profile('Bob B','UG','')") == "Your session ended. Sign in again.")
check("token with no session id can't write", cerr({"sub": str(S), "role": "authenticated"}, "select update_profile('Sam','UG','')") == "Your session ended. Sign in again.")

# Admin needs a fresh password AND the pinned authenticator in this session
ac = json.loads(admin_session.claims(cur, A))
check("admin after password + code: admin", with_claims(ac, "select is_admin()")[0][0] is True)
old = dict(ac, amr=[{"method": "totp", "timestamp": now}, {"method": "password", "timestamp": now - 13 * 3600}])
check("admin whose password was entered 13 hours ago: not admin", with_claims(old, "select is_admin()")[0][0] is False)
sid = ac["session_id"]; su("delete from auth.sessions where id=%s", (sid,))
check("admin after sign-out: not admin, even with the old token", with_claims(ac, "select is_admin()")[0][0] is False)
check("admin after sign-out: admin functions refused", cerr(ac, "select admin_set_setting('garage_response','\"2 days\"'::jsonb)") is not None)

# The admin entry in the menu: shown to admin accounts only, gives no access by itself
s1 = su("insert into auth.sessions (user_id, aal) values (%s,'aal1') returning id", (A,))[0][0]
pw_only = {"sub": str(A), "role": "authenticated", "session_id": str(s1), "aal": "aal1", "amr": [{"method": "password", "timestamp": now}]}
r = with_claims(pw_only, "select my_roles()")[0][0]
check("admin signed in as seller: admin_account true, admin false", r["admin_account"] is True and r["admin"] is False, r)
check("seller: no admin_account", as_(S, "select my_roles()")[0][0]["admin_account"] is False)
check("admin signed in as seller can't use admin functions", cerr(pw_only, "select admin_act('price', gen_random_uuid(), 'reason long enough', '{}'::jsonb)") == "Admins only.")
check("seller can't call admin functions", err(S, "select admin_decide_garage(gen_random_uuid(),'approve')") == "Admins only.")
check("seller can't read the activity log", as_(S, "select count(*) from audit_log")[0][0] == 0)

# Failed admin checks are recorded, for admin accounts only
with_claims(pw_only, "select admin_verify_failed('code')"); as_(S, "select admin_verify_failed('code')")
check("failed code recorded for the admin account", su("select count(*) from audit_log where action='admin check failed: code' and actor_id=%s", (A,))[0][0] == 1)
check("nothing recorded for a non-admin", su("select count(*) from audit_log where action like 'admin check failed%%' and actor_id=%s", (S,))[0][0] == 0)

# Garages: approval before permissions; invite stages separate from certification
O = user("owner@g.test", "Olga Owner")
gid = as_(O, "select apply_garage(%s)", (json.dumps({"name": "Ntinda Motors", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "x", "phone": "1", "registration_no": "r", "honest_declaration": True}),))[0][0]
check("owner of a garage waiting for approval can't add members", "certified garage" in (err(O, "select add_garage_member('ian@g.test','Ian','','inspector')") or ""))
check("owner of a garage waiting for approval has no garage access", as_(O, "select my_garage_id()")[0][0] is None)
as_(A, "select admin_decide_garage(%s,'approve')", (gid,))
check("certified owner can add members", as_(O, "select add_garage_member('ian@g.test','Ian','','inspector')")[0][0] == "invite_waiting_for_signup")
I = user("ian@g.test", "Ian Inspector")
t = [x[0] for x in as_(O, "select garage_team(null)") if x[0]["email"] == "ian@g.test"][0]
check("new member: Invited, not accepted, garage certified shown separately", t["status"] == "invited" and t["accepted_at"] is None and t["garage_status"] == "certified", t)
as_(I, "select accept_garage_invite()")
t = [x[0] for x in as_(O, "select garage_team(null)") if x[0]["email"] == "ian@g.test"][0]
check("after setting a password: Accepted", t["accepted_at"] is not None, t)
check("acceptance is in the activity log", su("select count(*) from audit_log where action='accepted the invite'")[0][0] == 1)

O2 = user("owner2@g.test", "Otto Owner")
g2 = as_(A, "select admin_add_garage(%s,'m@g.test','Mia','','direct add for test')", (json.dumps({"name": "Kira Auto", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "x", "phone": "1", "registration_no": "r"}),))[0][0]
su("update garages set status='applied' where id=%s", (g2,))  # a garage that is not certified
M = user("m@g.test", "Mia")
r = as_(M, "select garage_sign_in()")[0][0]
check("accepting an invite to an uncertified garage gives no access", r["ok"] is False and as_(M, "select my_garage_id()")[0][0] is None, r)
check("but the acceptance itself is recorded", su("select accepted_at is not null from garage_members where user_id=%s", (M,))[0][0])
check("anon can't call accept_garage_invite", su("select has_function_privilege('anon','public.accept_garage_invite()','execute')")[0][0] is False)
print(f"\n{ok} passed, {bad} failed")
