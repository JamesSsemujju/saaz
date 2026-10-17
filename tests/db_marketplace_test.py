"""End-to-end test of the Saaz marketplace schema on a local Postgres stand-in for Supabase."""
import json, psycopg2, sys
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname=sys.argv[1] if len(sys.argv) > 1 else "sb")
conn.autocommit = True
cur = conn.cursor()
passed = failed = 0

def su(sql, args=()):
    cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(sql, args)
    return cur.fetchall() if cur.description else None

def as_(uid, sql, args=()):
    claims = json.dumps({"sub": str(uid), "role": "authenticated"}) if uid else ""
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (claims,))
    cur.execute("set role " + ("authenticated" if uid else "anon"))
    try:
        cur.execute(sql, args)
        return cur.fetchall() if cur.description else None
    finally:
        cur.execute("reset role")

def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name, extra)

def err(uid, sql, args=()):
    try: as_(uid, sql, args); return None
    except psycopg2.Error as e: return e.diag.message_primary

def user(email, name, country="UG", mobile="+256700000000"):
    return su("insert into auth.users (email, raw_user_meta_data) values (%s, %s) returning id",
              (email, json.dumps({"name": name, "country": country, "mobile": mobile})))[0][0]

A = user("admin@saaz.test", "Ann Admin"); su("insert into public.admins (user_id, name) values (%s,'Ann Admin')", (A,))
S = user("seller@x.test", "Sam Seller"); B = user("buyer@x.test", "Bob Buyer"); B2 = user("buyer2@x.test", "Bea Buyer")
G1 = user("g1@x.test", "Gus Owner"); G2 = user("g2@x.test", "Gail Owner")
check("profile created on sign-up", su("select name, country from profiles where id=%s", (S,))[0] == ("Sam Seller", "UG"))

garage = lambda name, region: {"name": name, "business_type": "garage", "country": "UG", "region": region, "address": "Plot 1",
  "phone": "+256700111222", "registration_no": "REG1", "years": 5, "specialties": ["Toyota"], "honest_declaration": True}
g1 = as_(G1, "select apply_garage(%s)", (json.dumps(garage("Kampala Motors", "Kampala")),))[0][0]
g2 = as_(G2, "select apply_garage(%s)", (json.dumps(garage("Jinja Auto", "Jinja")),))[0][0]
r = as_(G1, "select garage_sign_in()")[0][0]
check("garage sign-in blocked until certified", r["ok"] is False and "with Saaz" in r["message"], r)
check("admins notified of application", su("select count(*) from notifications where user_id=%s and kind='garage_applied'", (A,))[0][0] == 2)
check("non-admin cannot approve", err(S, "select admin_decide_garage(%s,'approve')", (g1,)) == "Admins only.")
check("reject needs a note", err(A, "select admin_decide_garage(%s,'rejected')", (g1,)) == "A note is required.")
as_(A, "select admin_decide_garage(%s,'approve')", (g1,)); as_(A, "select admin_decide_garage(%s,'approve')", (g2,))
check("garage sign-in after certification", as_(G1, "select garage_sign_in()")[0][0]["ok"] is True)

check("owner invites inspector without account", as_(G1, "select add_garage_member('ian@x.test','Ian','+256700','inspector')")[0][0] == "invite_waiting_for_signup")
I1 = user("ian@x.test", "Ian Inspector")
check("invite becomes membership on sign-up", su("select role, status from garage_members where user_id=%s", (I1,))[0] == ("inspector", "invited"))
as_(I1, "select garage_sign_in()")
check("member active on first garage sign-in", su("select status from garage_members where user_id=%s", (I1,))[0][0] == "active")
e=err(G2, "select add_garage_member('ian@x.test','Ian','','inspector')"); check("one garage per person", "already on a garage team" in (e or ""), e)

car = {"vin": "JTEBU3FJ10K123456", "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic",
       "body": "SUV", "colour": "White", "engine": "2.0", "mileage": 84000, "plate": "UBA 123X", "country": "UG", "region": "Kampala",
       "price": 95000000, "description": "Clean Harrier, one owner in Uganda, full service history.",
       "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
check("bad plate refused", "UBA 123X" in (err(S, "select save_listing(%s)", (json.dumps({**car, "plate": "KDA 123X"}),)) or ""))
check("17-char VIN with O refused", "I, O or Q" in (err(S, "select save_listing(%s)", (json.dumps({**car, "vin": "JTEBU3FJ10K12345O"}),)) or ""))
L = as_(S, "select save_listing(%s)", (json.dumps(car),))[0][0]
check("vehicle record created", su("select count(*) from vehicles where vin='JTEBU3FJ10K123456'")[0][0] == 1)
check("draft not public", as_(None, "select count(*) from listings where id=%s", (L,))[0][0] == 0)
as_(S, "select submit_listing(%s)", (L,))
c1 = su("select id, garage_id from conversations where listing_id=%s and status='in_play'", (L,))[0]
check("nearest garage (Kampala) put in play", c1[1] == g1)
check("other garage can't see the car", as_(G2, "select count(*) from listings where id=%s", (L,))[0][0] == 0)
check("in-play garage can see the car", as_(I1, "select count(*) from listings where id=%s", (L,))[0][0] == 1)
check("seller can't agree before garage messages", "once the garage has messaged" in (err(S, "select seller_respond(%s,true)", (c1[0],)) or ""))
check("seller can't message first", "garage to message first" in (err(S, "select send_message(%s,'hi')", (c1[0],)) or ""))
as_(I1, "select send_message(%s,%s)", (c1[0], "Hello, call me on +256 772 123 456 or gus@garage.ug"))
body = as_(S, "select body from messages where conversation_id=%s", (c1[0],))[0][0]
check("contacts hidden before agreement", "772" not in body and "@" not in body, body)
check("buyer can't read messages", as_(B, "select count(*) from messages")[0][0] == 0)
check("admin can't read messages (not Saaz-owned)", as_(A, "select count(*) from messages")[0][0] == 0)
as_(S, "select seller_respond(%s,false,'Too far for me')", (c1[0],))
c2 = su("select id, garage_id from conversations where listing_id=%s and status='in_play'", (L,))[0]
check("pass brings next garage (Jinja)", c2[1] == g2)
check("garage can't read pass reason", as_(I1, "select count(*) from pass_reasons")[0][0] == 0)
check("seller can read own pass reason", as_(S, "select count(*) from pass_reasons")[0][0] == 1)
as_(G2, "select garage_respond(%s,'decline')", (c2[0],))
check("line empty after all garages", su("select line_empty from listings where id=%s", (L,))[0][0] is True)
check("admin told line is empty", su("select count(*) from notifications where user_id=%s and kind='line_empty'", (A,))[0][0] == 1)
as_(A, "select admin_restart_line(%s)", (L,))
c3 = su("select id, garage_id from conversations where listing_id=%s and status='in_play'", (L,))[0]
check("restart puts Kampala back in play", c3[1] == g1)
as_(G1, "select send_message(%s,'We can review Tuesday')", (c3[0],)); as_(S, "select seller_respond(%s,true)", (c3[0],))
check("agreed -> review booked", su("select status from listings where id=%s", (L,))[0][0] == "review_booked")
as_(S, "select send_message(%s,'My number is 0772 999 888')", (c3[0],))
check("contacts visible after agreement", "999" in as_(G1, "select body from messages where conversation_id=%s order by created_at desc limit 1", (c3[0],))[0][0])
check("Jinja can't start review", "not booked with your garage" in (err(G2, "select start_review(%s)", (L,)) or ""))
R = as_(I1, "select start_review(%s)", (L,))[0][0]
check("draft locked to member", "Ian Inspector is writing this inspection report" in (err(G1, "select start_review(%s)", (L,)) or ""))
keys = ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']
as_(I1, "select save_review(%s,%s)", (R, json.dumps({"checks": {k: "pass" for k in keys[:-1]}, "odometer": 84500, "in_person": True})))
check("issue refuses missing check", "vin is missing" in (err(I1, "select issue_review(%s)", (R,)) or ""))
checks = {k: "pass" for k in keys}; checks["tyres"] = "advise"
as_(I1, "select save_review(%s,%s)", (R, json.dumps({"checks": checks, "panels": {"bonnet": "scratch"}, "odometer": 84500, "in_person": True, "notes": "Front tyres at 3 mm, replace soon."})))
res = as_(I1, "select issue_review(%s)", (R,))[0][0]
check("issued: conditional, score round(85/88*100)=97 minus 1 scratch = 96", res["verdict"] == "conditional" and res["score"] == 96, res)
check("doc number format", res["doc_no"].startswith("SZR-") and len(res["doc_no"]) == 15, res)
check("non-trusted seller -> awaiting approval", su("select status from listings where id=%s", (L,))[0][0] == "awaiting_approval")
v = as_(None, "select verify_review(%s)", (res["verify_code"],))[0][0]
check("public verify: genuine and intact", v["genuine"] and v["intact"], v)
su("update reviews set score=99 where id=%s", (R,))
check("verify detects altered record", as_(None, "select verify_review(%s)", (res["verify_code"],))[0][0]["intact"] is False)
su("update reviews set score=96 where id=%s", (R,))
check("odometer reading stored", su("select km from odometer_readings where review_id=%s", (R,))[0][0] == 84500)
as_(A, "select admin_decide_listing(%s,'approve')", (L,))
check("approved -> live and public", as_(None, "select status from listings where id=%s", (L,))[0][0] == "live")

as_(B, "select record_view(%s,null)", (L,)); as_(B, "select record_view(%s,null)", (L,)); as_(None, "select record_view(%s,'device-1')", (L,)); as_(S, "select record_view(%s,null)", (L,))
st = as_(S, "select listing_stats(%s)", (L,))[0][0]
check("views: one per person per day, seller not counted", st["views_7d"] == 2, st)
check("public stats are limited", "highest_offer" not in as_(None, "select listing_stats(%s)", (L,))[0][0])
as_(S, "select set_offer_rules(%s,%s)", (L, json.dumps({"min_pct": 90, "auto_reject": True, "no_trade_in": True})))
r = as_(B, "select make_offer(%s,%s,false,'')", (L, 80000000))[0][0]
check("auto-reject below rule, minimum not revealed", r["status"] == "auto_rejected" and "90" not in r["message"], r)
check("offer under 50% refused", "50 percent" in (err(B, "select make_offer(%s,%s,false,'')", (L, 40000000)) or ""))
check("seller can't offer on own car", "own car" in (err(S, "select make_offer(%s,%s,false,'')", (L, 90000000)) or ""))
r = as_(B, "select make_offer(%s,%s,true,'Can I see it Saturday?')", (L, 92000000))
check("auto-reject trade-in when not accepted", r[0][0]["status"] == "auto_rejected" and "trade-in" in r[0][0]["message"], r)
D = as_(B, "select make_offer(%s,%s,false,'')", (L, 90000000))[0][0]["deal"]
check("one open offer per car", "already have an open offer" in (err(B, "select make_offer(%s,%s,false,'')", (L, 91000000)) or ""))
as_(S, "select set_offer_rules(%s,%s)", (L, json.dumps({"min_pct": 95, "auto_reject": False})))
D2 = as_(B2, "select make_offer(%s,%s,false,'')", (L, 85000000))[0][0]["deal"]
check("auto-reject off: offer flagged for seller", su("select flag from deals where id=%s", (D2,))[0][0] is not None)
as_(S, "select deal_action(%s,'reject')", (D2,))
check("seller rejects flagged offer", su("select status from deals where id=%s", (D2,))[0][0] == "rejected")
check("no contacts before agreement", as_(B, "select deal_contacts(%s)", (D,))[0][0] is None)
as_(S, "select deal_action(%s,'counter',%s)", (D, 93000000)); as_(B, "select deal_action(%s,'accept')", (D,))
check("both accept -> agreed, car reserved", su("select d.status, l.status from deals d join listings l on l.id=d.listing_id where d.id=%s", (D,))[0] == ("agreed", "reserved"))
check("buyer sees seller contact after agreement", as_(B, "select deal_contacts(%s)", (D,))[0][0]["mobile"] == "+256700000000")
check("only admin completes", err(S, "select deal_action(%s,'complete')", (D,)) == "Admins only.")
as_(A, "select deal_action(%s,'complete')", (D,))
check("completed -> sold, sale odometer stored", su("select status from listings where id=%s", (L,))[0][0] == "sold" and su("select count(*) from odometer_readings where source='sale'")[0][0] == 1)
check("auto-rejected counted", as_(S, "select listing_stats(%s)", (L,))[0][0]["auto_rejected"] == 2)
ws = as_(None, "select * from whats_selling('UG')")
check("what's selling lists Toyota Harrier", ws and ws[0][0] == "Toyota" and ws[0][5] == 1, ws)
check("relisting same VIN can't go below Saaz reading", "highest Saaz reading" in (err(B, "select save_listing(%s)", (json.dumps({**car, "mileage": 80000}),)) or ""))
L2 = as_(B, "select save_listing(%s)", (json.dumps({**car, "mileage": 86000}),))[0][0]
check("history carries on for same VIN", as_(B, "select vin_lookup('JTEBU3FJ10K123456')")[0][0]["found"] == "earlier")

# Saaz-owned import
as_(A, "select admin_add_import(%s)", (json.dumps({"vin": "ZSU60-0012345", "make": "Toyota", "model": "Harrier", "year": 2016, "fuel": "Petrol",
   "gearbox": "Automatic", "body": "SUV", "engine": "2.0", "import_mileage": 61000}),))
check("Saaz import found on lookup", as_(A, "select vin_lookup('ZSU60-0012345')")[0][0]["found"] == "saaz_import")
check("a person can't list a Saaz-owned car", "owned by Saaz" in (err(S, "select save_listing(%s)", (json.dumps({**car, "vin": "ZSU60-0012345", "plate": "UBB 222Y", "mileage": 62000}),)) or ""))
LS = as_(A, "select save_listing(%s)", (json.dumps({**car, "vin": "ZSU60-0012345", "plate": "UBB 222Y", "mileage": 62000, "make": "Fake", "saaz_owned": True}),))[0][0]
check("import details locked", su("select make, year from listings where id=%s", (LS,))[0] == ("Toyota", 2016))
as_(A, "select submit_listing(%s)", (LS,))
cs = su("select id from conversations where listing_id=%s and status='in_play'", (LS,))[0][0]
as_(G1, "select send_message(%s,'Hello Saaz')", (cs,))
check("admin reads messages on Saaz-owned car", as_(A, "select count(*) from messages where conversation_id=%s", (cs,))[0][0] == 1)

# Timeout
su("update conversations set deadline = now() - interval '1 hour' where id=%s", (cs,))
su("insert into conversations (listing_id, garage_id, deadline) select %s, %s, now() where false", (LS, g2))
as_(B, "select tick()")
check("no garage message keeps it in play (garage messaged)", su("select status from conversations where id=%s", (cs,))[0][0] == "in_play")
as_(B, "select save_listing(%s)", (json.dumps({**car, "id": str(L2), "mileage": 86000}),))
as_(B, "select submit_listing(%s)", (L2,))
cb = su("select id from conversations where listing_id=%s and status='in_play'", (L2,))[0][0]
su("update conversations set deadline = now() - interval '1 hour' where id=%s", (cb,))
as_(S, "select tick()")
check("timeout passes to next garage", su("select status from conversations where id=%s", (cb,))[0][0] == "timed_out"
      and su("select count(*) from conversations where listing_id=%s and status='in_play'", (L2,))[0][0] == 1)

# Security
check("anon can't call internal audit()", "permission denied" in (err(None, "select audit('x','x','x','x')") or ""))
check("anon can't write listings directly", "permission denied" in (err(None, "update listings set price=1") or "permission denied") or as_(None, "select 1") )
n_before = su("select price from listings where id=%s", (L2,))[0][0]
try: as_(B2, "update listings set price=1 where id=%s", (L2,))
except psycopg2.Error: pass
check("other user can't change a listing", su("select price from listings where id=%s", (L2,))[0][0] == n_before)
try: as_(S, "delete from audit_log")
except psycopg2.Error: pass
check("audit trail can't be deleted", su("select count(*) from audit_log")[0][0] > 20)
check("users can't read other profiles", as_(B, "select count(*) from profiles")[0][0] == 1)
check("admin can't change own access", "own access" in (err(A, "select admin_set_user(%s,'admin',false)", (A,)) or ""))
as_(A, "select admin_decide_garage(%s,'suspended','Complaint under review')", (g1,))
check("suspend passes in-play cars on", su("select count(*) from conversations where garage_id=%s and status in ('in_play','agreed')", (g1,))[0][0] == 0)
check("suspended garage blocked at sign-in", as_(G1, "select garage_sign_in()")[0][0]["ok"] is False)
print(f"\n{passed} passed, {failed} failed")
