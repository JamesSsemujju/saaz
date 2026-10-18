"""Tests for part 15: one card source for marketplace and admin; admin sees every status; nothing becomes public. Fresh database."""
import json, psycopg2, admin_session
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def as_(uid, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, uid) if uid else "",)); cur.execute("set role " + ("authenticated" if uid else "anon"))
    try: cur.execute(q, a or None); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def err(uid, q, a=()):
    try: as_(uid, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def user(e, n): return su("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name) values (%s,'Ann Admin')", (A,))
S = user("seller@x.test", "Sam Seller"); B = user("buyer@x.test", "Bob Buyer")
car = {"vin": "JTEBU3FJ10K123456", "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic",
       "body": "SUV", "colour": "White", "engine": "2.0", "mileage": 84000, "plate": "UBA 123X", "country": "UG", "region": "Kampala",
       "price": 95000000, "description": "Clean Harrier, one owner in Uganda, full service history.", "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
D = as_(S, "select save_listing(%s)", (json.dumps(car),))[0][0]                                             # draft
L = as_(S, "select save_listing(%s)", (json.dumps({**car, "vin": "JTEBU3FJ10K654321", "plate": "UBB 456Y", "photos": ["a.webp"]}),))[0][0]
su("update listings set status='live', live_at=now() where id=%s", (L,))                                     # live (test shortcut)
adm = [x[0] for x in as_(A, "select admin_listings(null)")]
check("admin sees every car, any status", {x["id"] for x in adm} == {str(D), str(L)})
pub = [x[0] for x in as_(None, "select browse_listings('UG')")]
check("the marketplace shows only the live car", [x["id"] for x in pub] == [str(L)])
a_live = [x for x in adm if x["id"] == str(L)][0]; p_live = pub[0]
check("same card data for the live car in both (one source)", {k: v for k, v in a_live.items() if k != "public"} == p_live, set(k for k in a_live if a_live.get(k) != p_live.get(k)))
check("public card has no private fields", not any(k in p_live for k in ("seller_id", "admin_note", "rule_min_pct", "public")))
d = [x for x in adm if x["id"] == str(D)][0]
check("admin card marks the draft as not public", d["public"] is False and a_live["public"] is True)
check("'not public' filter", [x[0]["id"] for x in as_(A, "select admin_listings('not_public')")] == [str(D)])
check("buyers can't use the admin list", err(B, "select admin_listings(null)") == "Admins only.")
check("anon can't use the admin list", err(None, "select admin_listings(null)") is not None)
check("a buyer opening the draft directly gets nothing", as_(B, "select count(*) from listings where id=%s", (D,))[0][0] == 0)
check("signed-out visitors opening the draft directly get nothing", as_(None, "select count(*) from listings where id=%s", (D,))[0][0] == 0)
check("admin preview of the draft doesn't make it public", as_(A, "select count(*) from listings where id=%s", (D,))[0][0] == 1 and len(as_(None, "select browse_listings('UG')")) == 1)
su("update listings set status='withdrawn' where id=%s", (L,))
check("status change: withdrawn car leaves the marketplace", len(as_(None, "select browse_listings('UG')")) == 0)
check("status change: admin still sees it, marked not public", [x[0]["public"] for x in as_(A, "select admin_listings('withdrawn')")] == [False])
print(f"\n{ok} passed, {bad} failed")
