"""Test helper: the token a signed-in person has. Admins get a session that passed their pinned authenticator (aal2),
like the real staff sign-in, so admin tests keep working with part 10. Everyone else gets a plain password session."""
import json, time
def claims(cur, uid):
    if not uid: return ""
    c = {"sub": str(uid), "role": "authenticated", "aal": "aal1", "amr": [{"method": "password", "timestamp": int(time.time())}]}
    cur.execute("reset role; select set_config('request.jwt.claims','',false)")
    cur.execute("select mfa_factor_id from public.admins where user_id=%s", (str(uid),)); r = cur.fetchone()
    if r is not None:
        f = r[0]
        if f is None:
            cur.execute("insert into auth.mfa_factors (user_id, friendly_name, factor_type, status, secret) values (%s,'test','totp','verified','X') returning id", (str(uid),)); f = cur.fetchone()[0]
            cur.execute("update public.admins set mfa_factor_id=%s where user_id=%s", (f, str(uid)))
        cur.execute("select id from auth.sessions where user_id=%s and factor_id=%s limit 1", (str(uid), f)); s = cur.fetchone()
        if not s: cur.execute("insert into auth.sessions (user_id, aal, factor_id) values (%s,'aal2',%s) returning id", (str(uid), f)); s = cur.fetchone()
        c.update(session_id=str(s[0]), aal="aal2", amr=[{"method": "totp", "timestamp": int(time.time())}, c["amr"][0]])
    return json.dumps(c)
