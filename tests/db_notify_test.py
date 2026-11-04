"""Part 24 Notifications. Runs inside one transaction and rolls back, so the database is left as it was.
Checks: notices fan out to the outbox (SMS only to verified Ugandan mobiles that allow it and aren't opted out; every skip
kept with its reason; email held until a sender exists), admin channel overrides per kind, the sender's claim and result
(codes first, leases, retries 1/5/30 minutes, permanent failures, code text removed), phone check codes (rate, expiry,
tries, number changed, verified), preferences, announcements (audience, consent, quiet hours, cost estimate, full admins),
opt-outs, retry, and that visitors and other people can't reach any of it.
Run: python3 tests/db_notify_test.py  (after tests/stack/reset.sh)"""
import json, hashlib, psycopg2, admin_session, sys, datetime
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname=sys.argv[1] if len(sys.argv) > 1 else "sb")
cur = conn.cursor()
passed = failed = 0
def su(sql, args=()):
    cur.execute("reset role; select set_config('request.jwt.claims','',true)"); cur.execute(sql, args)
    return cur.fetchall() if cur.description else None
def as_(uid, sql, args=(), role=None):
    claims = json.dumps({"role": "service_role"}) if role == "service_role" else (admin_session.claims(cur, uid) if uid else "")
    cur.execute("reset role; select set_config('request.jwt.claims',%s,true)", (claims,))
    cur.execute("set local role " + (role or ("authenticated" if uid else "anon"))); cur.execute("savepoint s")
    try:
        cur.execute(sql, args); r = cur.fetchall() if cur.description else None; cur.execute("release savepoint s"); return r
    except psycopg2.Error:
        cur.execute("rollback to savepoint s"); raise
    finally:
        cur.execute("reset role")
def one(uid, sql, args=(), role=None): return as_(uid, sql, args, role)[0][0]
def err(uid, sql, args=(), role=None):
    try: as_(uid, sql, args, role); return None
    except psycopg2.Error as e: return e.diag.message_primary
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name, extra)
def user(email, name, mobile=None, verified=False):
    u = su("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s, %s, now()) returning id", (email, json.dumps({"name": name, "country": "UG"})))[0][0]
    su("update profiles set mobile=%s, phone_verified=%s where id=%s", (mobile, verified, u)); return u
SVC = lambda q, a=(): one(None, q, a, role="service_role")
def out(uid, kind=None): return su("select channel, status, reason, to_addr, body from outbox where user_id=%s" + (" and kind=%s" if kind else "") + " order by id", (uid, kind) if kind else (uid,))
def notice(uid, kind, body, ch): su("select notify(%s,%s,%s,null,%s)", (uid, kind, body, ch))

A = user("n-admin@saaz.test", "Ada Admin"); su("insert into admins (user_id, name) values (%s,'Ada Admin')", (A,))
ST = user("n-staff@saaz.test", "Sid Staff"); su("insert into admins (user_id, name, role) values (%s,'Sid Staff','staff')", (ST,))
V = user("n-verified@x.test", "Vera Verified", "0772 111111", True)
N = user("n-new@x.test", "Ned Notverified", "+256772222222", False)
K = user("n-kenya@x.test", "Kim Kenya", "+254712345678", True)
O = user("n-off@x.test", "Ola Off", "+256772333333", True)
X = user("n-out@x.test", "Xan Optout", "+256772444444", True)
Y = user("n-yes@x.test", "Yan Verified", "+256772666666", True)
su("delete from outbox")

# 1. Fan-out
one(O, "select set_notify_prefs(%s)", (json.dumps({"alerts_sms": False, "alerts_email": True}),))
su("insert into sms_optout (mobile, reason) values ('+256772444444', 'Called Saaz to stop SMS')")
for u in (V, N, K, O, X): notice(u, "offer_received", "New offer of UGX 40,000,000 on your Toyota (100% genuine)", "{app,sms}")
check("verified Ugandan mobile: SMS queued", out(V)[0][:2] == ("sms", "queued") and out(V)[0][3] == "+256772111111", out(V))
check("SMS text starts with Saaz and has no % sign", out(V)[0][4].startswith("Saaz: ") and "%" not in out(V)[0][4], out(V)[0][4])
check("unverified mobile: skipped, reason kept", out(N)[0][1] == "skipped" and "verified" in out(N)[0][2])
check("non-Ugandan mobile: skipped", out(K)[0][1] == "skipped" and "Ugandan" in out(K)[0][2])
check("SMS alerts turned off: skipped", out(O)[0][1] == "skipped" and "Turned off" in out(O)[0][2])
check("opted-out number: skipped", out(X)[0][1] == "skipped" and "opt-out" in out(X)[0][2])
notice(V, "garage_message", "A garage replied", "{app}")
check("app-only notice makes no outbox row", len(out(V, "garage_message")) == 0)
notice(V, "deal_agreed", "Deal agreed", "{app,email,sms}")
check("email copy held until an email sender exists", [r[1] for r in out(V, "deal_agreed")] == ["queued", "held"] and "No email sender" in out(V, "deal_agreed")[1][2])
notice(V, "review_date", "Inspection booked for Friday", "{app}")
check("override per kind adds SMS (review_date)", out(V, "review_date")[0][1] == "queued")
check("staff can't change channels", err(ST, "select admin_notify_kind('garage_message', '{app,sms}')") is not None)
one(A, "select admin_notify_kind('garage_message', '{app,sms}')")
notice(V, "garage_message", "A garage replied again", "{app}")
check("admin override takes effect", len(out(V, "garage_message")) == 1)
check("the notice itself records the channels used", su("select channels from notifications where body='A garage replied again'")[0][0] == ["app", "sms"])
one(A, "select admin_notify_kind('garage_message', null)")
notice(V, "garage_message", "Third reply", "{app}")
check("clearing the override goes back to the code's channels", len(out(V, "garage_message")) == 1)
check("an override must keep the app inbox", err(A, "select admin_notify_kind('offer_received', '{sms}')") is not None)
k = one(A, "select admin_notify_kinds()")
check("admin sees every kind with its channels", any(x["kind"] == "offer_received" and "sms" in x["seen"] for x in k))

# 2. The sender
check("a signed-in person can't claim the outbox", err(V, "select outbox_claim(10)") is not None)
check("a visitor can't claim the outbox", err(None, "select outbox_claim(10)") is not None)
check("nobody signed in can write a result", err(A, "select outbox_result(1, true, 'x', 'x', null, false)") is not None)
code_res = one(N, "select phone_send_code()")
check("phone code goes to the number on the account, masked in the reply", code_res["sent_to"] == "+256772***22", code_res)
claimed = SVC("select outbox_claim(10)")
check("sender takes the code first", claimed and "your code is" in claimed[0]["body"], claimed[:1])
check("sender takes only due SMS (queued), not skipped or held", all(su("select status from outbox where id=%s", (x["id"],))[0][0] == "sending" for x in claimed) and len(claimed) == su("select count(*) from outbox where status='sending'")[0][0])
check("a second claim gets nothing while leased", SVC("select outbox_claim(10)") == [])
cid = claimed[0]["id"]; code = claimed[0]["body"].split("code is ")[1][:6]
SVC("select outbox_result(%s, true, 'ATPid_1', 'UGX 30', null, false)", (cid,))
check("sent code: text removed from the outbox", su("select status, body from outbox where id=%s", (cid,))[0] == ("sent", "(code removed after sending)"))
o2 = claimed[1]["id"]
check("transient failure: back in the queue in 1 minute", SVC("select outbox_result(%s, false, null, null, 'InternalServerError', false)", (o2,)) == "queued"
      and su("select next_try_at > now() + interval '50 seconds' from outbox where id=%s", (o2,))[0][0])
su("update outbox set next_try_at = now() - interval '1 second' where id=%s", (o2,)); SVC("select outbox_claim(10)")
SVC("select outbox_result(%s, false, null, null, 'InternalServerError', false)", (o2,))
su("update outbox set next_try_at = now() - interval '1 second' where id=%s", (o2,)); SVC("select outbox_claim(10)")
check("third failure: failed for good", SVC("select outbox_result(%s, false, null, null, 'InternalServerError', false)", (o2,)) == "failed")
o3 = su("select id from outbox where status='sending' limit 1")
if o3: check("permanent failure (InvalidPhoneNumber) fails at once", SVC("select outbox_result(%s, false, null, null, 'InvalidPhoneNumber', true)", (o3[0][0],)) == "failed")
su("update outbox set lease_until = now() - interval '1 second' where status='sending'")
check("an expired lease is taken again", len(SVC("select outbox_claim(10)")) == su("select count(*) from outbox where status='sending'")[0][0])
check("staff can retry a failed SMS", one(ST, "select admin_outbox_retry(%s)", (o2,)) == "queued")
check("a buyer can't retry", err(V, "select admin_outbox_retry(%s)", (o2,)) is not None)
SVC("select outbox_run(false, 0, 0, 0, 'Africa''s Talking keys not set')")
ob = one(ST, "select admin_outbox()")
check("admin outbox shows the last run and hides codes", ob["last_run"]["configured"] is False and all("your code is" not in r["body"] for r in ob["rows"]))
check("a buyer can't open the admin outbox", err(V, "select admin_outbox()") is not None)

# 3. Phone check
wrong = "000000" if code != "000000" else "111111"
check("wrong code counts a try", one(N, "select phone_check_code(%s)", (wrong,))["ok"] is False and su("select tries from phone_codes where user_id=%s and used_at is null", (N,))[0][0] == 1)
check("a new code within a minute is refused", "minute" in (err(N, "select phone_send_code()") or ""))
check("someone else's code doesn't verify you", err(O, "select phone_check_code(%s)", (code,)) is not None)
r = one(N, "select phone_check_code(%s)", (code,))
check("right code verifies the number", r["ok"] and su("select phone_verified from profiles where id=%s", (N,))[0][0])
check("a used code doesn't work again", err(N, "select phone_check_code(%s)", (code,)) is not None)
check("already verified: no new code", "already" in (err(N, "select phone_send_code()") or ""))
one(N, "select update_profile('Ned Notverified','UG','+256772555555')")
check("changing the mobile clears the check", su("select phone_verified from profiles where id=%s", (N,))[0][0] is False)
su("update phone_codes set created_at = created_at - interval '2 minutes' where user_id=%s", (N,))
one(N, "select phone_send_code()")
su("update phone_codes set expires_at = now() - interval '1 second' where user_id=%s and used_at is null", (N,))
check("an expired code is refused", "expired" in (err(N, "select phone_check_code('123456')") or ""))
su("update phone_codes set created_at = created_at - interval '2 minutes' where user_id=%s", (N,))
one(N, "select phone_send_code()")
for i in range(5): one(N, "select phone_check_code('99999%d')" % i)
check("after 5 wrong tries the code stops working", "Too many" in (err(N, "select phone_check_code('999990')") or ""))
su("update phone_codes set created_at = now() - interval '2 minutes' where user_id=%s", (N,))
for i in range(2): su("insert into phone_codes (user_id, mobile, code_hash, expires_at) values (%s,'+256772555555','x',now())", (N,))
su("update phone_codes set created_at = now() - interval '2 minutes' where user_id=%s", (N,))
check("at most 5 codes a day", "Too many codes" in (err(N, "select phone_send_code()") or ""))
check("code stored only as a hash", su("select count(*) from phone_codes where code_hash ~ '^[0-9]{6}$'")[0][0] == 0)
su("update profiles set phone_verified=false where id=%s", (K,))
check("no Ugandan mobile: no code", "Ugandan" in (err(K, "select phone_send_code()") or ""))
check("a visitor can't ask for a code", err(None, "select phone_send_code()") is not None)

# 4. Preferences
p = one(V, "select my_notify_prefs()")
check("defaults: alerts on, news off", p["alerts_sms"] and p["alerts_email"] and not p["news_sms"] and not p["news_email"])
check("someone else can't read your settings directly", err(N, "select * from notify_prefs") is not None)

# 5. Announcements
check("staff can't announce", err(ST, "select admin_announce('all', null, '{app,sms}', 'Saaz is open this weekend.', null)") is not None)
check("a link must be a Saaz page", err(A, "select admin_announce('all', null, '{app}', 'Saaz is open this weekend.', 'https://evil.test')") is not None)
one(V, "select set_notify_prefs(%s)", (json.dumps({"news_sms": True}),))
pv = one(A, "select admin_announce_preview('all', null, '{app,sms}', 'Saaz is open this weekend.')")
check("preview counts people and opted-in SMS", pv["people"] >= 6 and pv["sms"] == 1, pv)
check("preview says why each of the rest gets no SMS", pv["sms"] + sum(pv["sms_not_sent"].values()) == pv["people"] and "Mobile not verified yet" in pv["sms_not_sent"], pv)
check("verified but not opted in: no SMS news (Yan, and Ola who also turned alerts off)", pv["sms_not_sent"].get("Not opted in to SMS news") == 2, pv)
check("no price set: cost shown as unknown", pv["cost_ugx"] is None and pv["price_ugx"] is None)
su("update settings set value='30'::jsonb where key='sms_price_ugx'")
check("with a price: cost = price x segments x SMS", one(A, "select admin_announce_preview('all', null, '{app,sms}', 'Saaz is open this weekend.')")["cost_ugx"] == 30)
one(O, "select set_notify_prefs(%s)", (json.dumps({"alerts_sms": False, "news_sms": True}),))
check("news on with alerts off still gets announcement SMS", one(A, "select admin_announce_preview('all', null, '{app,sms}', 'Saaz is open this weekend.')")["sms"] == 2)
one(O, "select set_notify_prefs(%s)", (json.dumps({"alerts_sms": False, "news_sms": False}),))
n_before = su("select count(*) from notifications where kind='announcement'")[0][0]
a = one(A, "select admin_announce('all', null, '{app,sms}', 'Saaz is open this weekend.', '#/browse')")
check("everyone in the audience gets it in the app", su("select count(*) from notifications where kind='announcement'")[0][0] - n_before == a["app"] == pv["people"])
check("SMS only to the one who opted in", a["sms"] == 1 and su("select user_id from outbox where kind='announcement' and status='queued'")[0][0] == V)
check("announcement SMS says how to stop", "Stop these" in su("select body from outbox where kind='announcement' and status='queued'")[0][0])
h = su("select extract(hour from next_try_at at time zone 'Africa/Kampala') from outbox where kind='announcement' and status='queued'")[0][0]
check("announcement SMS waits for 08:00 to 20:00 EAT", 8 <= h <= 19, h)
check("an announcement notice doesn't also fan out as an alert", su("select count(*) from outbox where kind='announcement' and purpose='alert'")[0][0] == 0)
night = su("select sms_send_window('2026-11-03 21:30:00+03'), sms_send_window('2026-11-04 06:00:00+03'), sms_send_window('2026-11-04 12:00:00+03')")[0]
check("quiet hours: 21:30 waits to 08:00 next day, 06:00 waits to 08:00, noon goes now", [str(x) for x in night] == ["2026-11-04 05:00:00+00:00", "2026-11-04 05:00:00+00:00", "2026-11-04 09:00:00+00:00"], night)
su("update settings set value='2'::jsonb where key='sms_max_audience'")
check("audience cap holds", "limit" in (err(A, "select admin_announce('all', null, '{app}', 'Saaz is open this weekend.', null)") or ""))
su("update settings set value='20000'::jsonb where key='sms_max_audience'")
check("announcement history kept", one(A, "select admin_announcements()")["list"][0]["counts"]["sms"] == 1)

# 6. Opt-out
one(A, "select admin_sms_optout('0772 111111', 'Called Saaz on 3 Nov to stop SMS', true)")
check("opting a number out stops its queued SMS", su("select count(*) from outbox where to_addr='+256772111111' and status='queued'")[0][0] == 0)
notice(V, "offer_received", "Another offer", "{app,sms}")
check("and new ones", out(V, "offer_received")[-1][1] == "skipped")

# 7. Outsiders
for who, uid in (("visitor", None), ("buyer", V)):
    for t in ("outbox", "notify_kinds", "announcements", "sms_optout", "phone_codes", "outbox_runs"):
        check(f"{who}: no direct read of {t}", err(uid, "select count(*) from " + t) is not None)

conn.rollback()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
