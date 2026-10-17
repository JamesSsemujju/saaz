"""Tests for part 10: admin access needs the pinned authenticator, used in this session, in the last 12 hours. Fresh database."""
import json, time, psycopg2, subprocess, os
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def with_claims(c, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (json.dumps(c),)); cur.execute("set role authenticated")
    try: cur.execute(q, a or None); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def err(c, q, a=()):
    try: with_claims(c, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
now = int(time.time())
def tok(uid, sid, aal="aal2", totp_at=now):
    amr = [{"method": "password", "timestamp": now}] + ([{"method": "totp", "timestamp": totp_at}] if totp_at else [])
    return {"sub": str(uid), "role": "authenticated", "session_id": str(sid) if sid else None, "aal": aal, "amr": amr}
def user(e): return su("insert into auth.users (email) values (%s) returning id", (e,))[0][0]
def factor(u, status="verified"): return su("insert into auth.mfa_factors (user_id, friendly_name, factor_type, status, secret) values (%s,'phone','totp',%s,'X') returning id", (u, status))[0][0]
def sess(u, aal="aal1", f=None): return su("insert into auth.sessions (user_id, aal, factor_id, ip, user_agent) values (%s,%s,%s,'41.210.1.2','Test browser') returning id", (u, aal, f))[0][0]
def isadmin(c): return with_claims(c, "select public.is_admin()")[0][0]

A = user("ssemujjujames@saazinvestmentsltd.com"); su("insert into admins (user_id, name) values (%s,'James')", (A,))
B = user("buyer@t")

s1 = sess(A)
check("admin with password only is not admin", isadmin(tok(A, s1, "aal1", None)) is False)
check("my_roles hides admin before the code", with_claims(tok(A, s1, "aal1", None), "select my_roles()->>'admin'")[0][0] == "false")
check("admin settings refused before the code", err(tok(A, s1, "aal1", None), "select admin_set_setting('garage_response', '\"2 days\"'::jsonb)") is not None)

F = factor(A); s2 = sess(A, "aal2", F)
check("authenticator used but not pinned yet: not admin", isadmin(tok(A, s2)) is False)

# pin script from the SQL Editor
pin = open(os.path.join(os.path.dirname(__file__), "..", "supabase", "marketplace_10b_pin_admin_authenticator.sql")).read()
su(pin)
check("pin script pins the one verified authenticator", su("select mfa_factor_id from admins where user_id=%s", (A,))[0][0] == F)
check("pin is in the audit log", su("select count(*) from audit_log where action='admin authenticator pinned from SQL Editor'")[0][0] == 1)

check("pinned authenticator, code just entered: admin", isadmin(tok(A, s2)) is True)
check("my_roles shows admin after the code", with_claims(tok(A, s2), "select my_roles()->>'admin'")[0][0] == "true")
check("code entered 13 hours ago: not admin", isadmin(tok(A, s2, totp_at=now - 13 * 3600)) is False)
check("token says aal2 but the session is aal1: not admin", isadmin(tok(A, s1)) is False)
check("no session id in the token: not admin", isadmin(tok(A, None)) is False)

T = factor(A); s3 = sess(A, "aal2", T)
check("thief adds their own authenticator: not admin", isadmin(tok(A, s3)) is False)
sb = sess(B, "aal2", factor(B))
check("someone else's session id: not admin", isadmin(tok(A, sb)) is False)
check("buyer with an authenticator is not admin", isadmin(tok(B, sb)) is False)

check("pin can't be read from the app", err(tok(A, s2), "select mfa_factor_id from admins") is not None)
check("pin can't be changed from the app, even by the admin", err(tok(A, s2), "update admins set mfa_factor_id=%s", (T,)) is not None)
check("admin can still list admins (no pin column)", with_claims(tok(A, s2), "select count(*) from admins")[0][0] >= 1)

with_claims(tok(A, s2), "select admin_signed_in()")
row = su("select detail from audit_log where action='admin signed in with authenticator'")
check("admin sign-in recorded with IP and browser", row and row[0][0].get("ip") == "41.210.1.2" and row[0][0].get("browser") == "Test browser", row)
check("admin sign-in refused without the code", err(tok(A, s1, "aal1", None), "select admin_signed_in()") is not None)
check("anon can't call admin_signed_in", su("select has_function_privilege('anon','public.admin_signed_in()','execute')")[0][0] is False)

# pin script refuses when there is more than one authenticator (the thief's one above)
su("update admins set mfa_factor_id=null where user_id=%s", (A,))
try: su(pin); refused = False
except psycopg2.Error as e: refused = "exactly 1" in e.diag.message_primary
check("pin script refuses with 2 authenticators", refused)
print(f"\n{ok} passed, {bad} failed")
