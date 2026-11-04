"""Part 25: Custom audience for Announcements (BA-0013). Runs inside one transaction and rolls back.
Checks each filter (roles, verified, active, joined, makes, models), that filters combine (all must hold), that named people
are added on top, people alone, suspended accounts left out, bad input refused, the preview's sample names, that a custom
announcement records its filter and reaches exactly that audience, SMS rules unchanged, and that only full admins can use it.
Run: python3 tests/db_custom_audience_test.py  (after tests/stack/reset.sh)"""
import json, psycopg2, admin_session, sys
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname=sys.argv[1] if len(sys.argv) > 1 else "sb")
cur = conn.cursor()
passed = failed = 0
def su(sql, args=()):
    cur.execute("reset role; select set_config('request.jwt.claims','',true)"); cur.execute(sql, args)
    return cur.fetchall() if cur.description else None
def as_(uid, sql, args=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,true)", (admin_session.claims(cur, uid) if uid else "",))
    cur.execute("set local role " + ("authenticated" if uid else "anon")); cur.execute("savepoint s")
    try:
        cur.execute(sql, args); r = cur.fetchall() if cur.description else None; cur.execute("release savepoint s"); return r
    except psycopg2.Error:
        cur.execute("rollback to savepoint s"); raise
    finally:
        cur.execute("reset role")
def one(uid, sql, args=()): return as_(uid, sql, args)[0][0]
def err(uid, sql, args=()):
    try: as_(uid, sql, args); return None
    except psycopg2.Error as e: return e.diag.message_primary
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name, extra)
def user(email, name, mobile=None, verified=False, days_old=0, signed_in_days=None):
    u = su("insert into auth.users (email, raw_user_meta_data, email_confirmed_at, last_sign_in_at) values (%s,%s,now(),%s) returning id",
           (email, json.dumps({"name": name, "country": "UG"}), None))[0][0]
    if signed_in_days is not None: su("update auth.users set last_sign_in_at = now() - make_interval(days => %s) where id=%s", (signed_in_days, u))
    su("update profiles set mobile=%s, phone_verified=%s, created_at = now() - make_interval(days => %s) where id=%s", (mobile, verified, days_old, u)); return u
def listing(seller, make, model, i):
    v = su("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTCUST%011d" % i, make, model))[0][0]
    return su("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
       description, photos, logbook_name_matches, owner_authorised) values (%s,%s,'UG','Kampala','live',%s,%s,2015,'Petrol','Automatic','SUV','White','2.0',80000,%s,'UGX',50000000,'Clean car',%s,true,true) returning id""",
       (v, seller, make, model, "UBC %03dC" % i, ["a.webp"]))[0][0]

A = user("ca-admin@saaz.test", "Ada Admin"); su("insert into admins (user_id, name) values (%s,'Ada Admin')", (A,))
ST = user("ca-staff@saaz.test", "Sid Staff"); su("insert into admins (user_id, name, role) values (%s,'Sid Staff','staff')", (ST,))
S1 = user("ca-s1@x.test", "Sam Harrier Seller", "+256772100001", True, days_old=5, signed_in_days=1)
S2 = user("ca-s2@x.test", "Sue Premio Seller", "+256772100002", False, days_old=200, signed_in_days=90)
B1 = user("ca-b1@x.test", "Bob Harrier Saver", "+256772100003", True, days_old=3, signed_in_days=2)
B2 = user("ca-b2@x.test", "Bea Nobody", "+256772100004", True, days_old=400)
X = user("ca-x@x.test", "Xan Suspended", "+256772100005", True, days_old=1, signed_in_days=1)
su("update profiles set suspended=true where id=%s", (X,))
L1 = listing(S1, "Toyota", "Harrier", 1); L2 = listing(S2, "Toyota", "Premio", 2); L3 = listing(X, "Toyota", "Harrier", 3)
su("insert into saves (listing_id, user_id) values (%s,%s)", (L1, B1))
OURS = {S1, S2, B1, B2, X}
def aud(f):
    r = su("select distinct user_id from announce_audience('custom', null, %s)", (json.dumps(f),))
    return {x[0] for x in r} & OURS if r else set()
check("roles: sellers", aud({"roles": ["sellers"]}) == {S1, S2})
check("roles: buyers (saved or offered)", aud({"roles": ["buyers"]}) == {B1})
check("roles: sellers or buyers", aud({"roles": ["sellers", "buyers"]}) == {S1, S2, B1})
check("verified only", aud({"verified": True}) == {S1, B1, B2})
check("active in the last 7 days", aud({"active_days": 7}) == {S1, B1})
check("joined in the last 30 days", aud({"joined_days": 30}) == {S1, B1})
check("make listed or saved (any case)", aud({"makes": ["toyota"]}) == {S1, S2, B1})
check("model listed or saved", aud({"models": ["Harrier"]}) == {S1, B1})
check("filters combine: sellers + verified + Harrier", aud({"roles": ["sellers"], "verified": True, "models": ["harrier"]}) == {S1})
check("named people added on top of filters", aud({"models": ["harrier"], "people": [str(B2)]}) == {S1, B1, B2})
check("named people alone", aud({"people": [str(B2), str(S2)]}) == {B2, S2})
check("suspended accounts never included (even named)", X not in aud({"models": ["harrier"], "people": [str(X)]}))
check("no filter and no people refused", "at least one" in (err(A, "select admin_announce_preview('custom', null, '{app}', 'Saaz test message here.', '{}'::jsonb)") or ""))
check("unknown role refused", err(A, "select admin_announce_preview('custom', null, '{app}', 'Saaz test message here.', %s)", (json.dumps({"roles": ["hackers"]}),)) is not None)
check("silly day count refused", err(A, "select admin_announce_preview('custom', null, '{app}', 'Saaz test message here.', %s)", (json.dumps({"active_days": 0}),)) is not None)
check("custom without a filter refused", err(A, "select admin_announce('custom', null, '{app}', 'Saaz test message here.', null, null)") is not None)

su("insert into notify_prefs (user_id, news_sms) values (%s, true), (%s, true)", (S1, B2))
f = {"models": ["harrier"], "people": [str(B2)]}
pv = one(A, "select admin_announce_preview('custom', null, '{app,sms}', 'New Harriers on Saaz this week.', %s)", (json.dumps(f),))
check("preview counts the custom audience", pv["people"] == 3, pv)
check("preview shows sample names", set(pv["sample"]) == {"Sam Harrier Seller", "Bob Harrier Saver", "Bea Nobody"}, pv["sample"])
check("SMS rules unchanged: opted-in and verified only", pv["sms"] == 2 and pv["sms_not_sent"].get("Not opted in to SMS news") == 1, pv)
r = one(A, "select admin_announce('custom', null, '{app,sms}', 'New Harriers on Saaz this week.', '#/browse', %s)", (json.dumps(f),))
got = {x[0] for x in su("select user_id from notifications where kind='announcement' and body='New Harriers on Saaz this week.'")}
check("sent to exactly the custom audience", got == {S1, B1, B2} and r["app"] == 3, (got, r))
check("SMS queued for the opted-in, verified ones", {x[0] for x in su("select user_id from outbox where kind='announcement' and status='queued'")} == {S1, B2})
check("the filter is recorded with the announcement", one(A, "select admin_announcements()")["list"][0]["filter"] == f)
check("the filter is in the audit trail", su("select count(*) from audit_log where action='announcement sent' and detail->'filter' is not null")[0][0] >= 1)
check("existing audiences still work", one(A, "select admin_announce_preview('sellers', null, '{app}', 'Saaz test message here.')")["people"] >= 2)

s = one(A, "select admin_people_search('harrier')")
check("people search by name", {x["name"] for x in s} == {"Sam Harrier Seller", "Bob Harrier Saver"}, s)
check("people search by mobile", [x["name"] for x in one(A, "select admin_people_search('100004')")] == ["Bea Nobody"])
check("people search leaves out suspended accounts", all(x["name"] != "Xan Suspended" for x in one(A, "select admin_people_search('ca-')")))
check("one letter returns nothing", one(A, "select admin_people_search('a')") == [])
for who, uid in (("staff", ST), ("buyer", B1), ("visitor", None)):
    check(f"{who} can't search people", err(uid, "select admin_people_search('harrier')") is not None)
    check(f"{who} can't preview a custom audience", err(uid, "select admin_announce_preview('custom', null, '{app}', 'Saaz test message here.', %s)", (json.dumps(f),)) is not None)
    check(f"{who} can't call the audience helper", err(uid, "select * from custom_audience(%s)", (json.dumps(f),)) is not None)
conn.rollback()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
