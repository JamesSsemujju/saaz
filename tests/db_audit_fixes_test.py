"""Tests for the audit fixes (part 6) on a fresh database."""
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
A = user("a@t", "Ann"); su("insert into admins values (%s,'Ann')", (A,)); S = user("s@t", "Sam"); O = user("o@t", "Owner")
car = {"vin": "JTMBFREV3HD123456", "make": "Toyota", "model": "RAV4", "year": 2017, "fuel": "Petrol", "gearbox": "Automatic", "body": "SUV", "colour": "White",
       "mileage": 60000, "plate": "UBA 123X", "country": "UG", "region": "Kampala", "price": 80000000, "description": "Clean RAV4 with full service history in Kampala.",
       "photos": ["a", "b", "c", "d"], "logbook_name_matches": True}
check("F-03 Kenya listing refused", "Uganda only" in (err(S, "select save_listing(%s)", (json.dumps({**car, "country": "KE", "region": "Nairobi", "plate": "KDA 123X"}),)) or ""))
try: su("insert into auth.users (email, raw_user_meta_data) values ('k@t', %s)", (json.dumps({"name": "K", "country": "KE"}),)); kok = False
except psycopg2.Error as e: kok = "Uganda only" in e.diag.message_primary
check("F-03 Kenya profile refused", kok)
# Garage added directly; owner has no account yet, so no Active member
g = as_(A, "select admin_add_garage(%s,'o2@t','O2','','test')", (json.dumps({"name": "Musa Body", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "x", "phone": "1", "registration_no": "r"}),))[0][0]
L = as_(S, "select save_listing(%s)", (json.dumps(car),))[0][0]; as_(S, "select submit_listing(%s)", (L,))
check("F-04 garage with no Active member not put in play", su("select line_empty from listings where id=%s", (L,))[0][0] is True and su("select count(*) from conversations")[0][0] == 0)
check("F-05 seller told once, admin told once", su("select count(*) from notifications where kind='line_empty'")[0][0] == 2)
O2 = user("o2@t", "O2")  # owner signs up: invited
check("invited owner alone still doesn't count", su("select line_empty from listings where id=%s", (L,))[0][0] is True)
as_(O2, "select garage_sign_in()")  # first garage sign-in: Active -> car gets the garage
check("F-06 car gets the garage when its first member signs in", su("select count(*) from conversations where listing_id=%s and status='in_play'", (L,))[0][0] == 1 and su("select line_empty from listings where id=%s", (L,))[0][0] is False)
# Saaz-owned car: admins told once each
as_(A, "select admin_decide_garage(%s,'suspended','test')", (g,))
as_(A, "select admin_add_import(%s)", (json.dumps({"vin": "ZSU60-0012345", "make": "Toyota", "model": "Harrier", "year": 2016, "fuel": "Petrol", "gearbox": "Automatic", "body": "SUV", "engine": "2.0", "import_mileage": 61000}),))
LS = as_(A, "select save_listing(%s)", (json.dumps({**car, "vin": "ZSU60-0012345", "plate": "UBB 222Y", "mileage": 62000, "saaz_owned": True}),))[0][0]
n0 = su("select count(*) from notifications where user_id=%s and kind='line_empty'", (A,))[0][0]
as_(A, "select submit_listing(%s)", (LS,))
check("F-05 Saaz-owned car: each admin told once", su("select count(*) from notifications where user_id=%s and kind='line_empty'", (A,))[0][0] == n0 + 1)
as_(A, "select admin_decide_garage(%s,'reinstate')", (g,))
check("F-06 reinstated garage picks up waiting cars", su("select count(*) from conversations where listing_id=%s and status='in_play'", (LS,))[0][0] == 1)
check("F-07 review dates use East Africa Time", su("select proconfig::text from pg_proc where proname='issue_review'")[0][0].find("Africa/Kampala") > 0)
check("internal helpers not callable", "permission denied" in (err(S, "select requeue_empty_lines()") or ""))
print(f"\n{ok} passed, {bad} failed")
