"""Part 26, open marketplace (6 Nov 2026), on a fresh database. The switch off keeps today's rule; on: a seller lists without
an inspection, Saaz approves it, it goes live Not inspected; a buyer asks for a Saaz inspection, the garage line runs while
the car stays on sale, the report shows for everyone; a safety Fail stays on the car with its history; an expired
inspection no longer takes the car off sale."""
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
def st(l): return su("select status from listings where id=%s", (l,))[0][0]
def notes(u, kind): return su("select body from notifications where user_id=%s and kind=%s order by created_at", (u, kind))
def market(on): su("update settings set value=%s::jsonb where key='open_market'", ("true" if on else "false",))

A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
S = user("seller@x.test", "Sam Seller"); B = user("buyer@x.test", "Bea Buyer"); B2 = user("buyer2@x.test", "Ben Buyer")
O = user("owner@g.test", "Olga Owner")
g = as_(O, "select apply_garage(%s)", (json.dumps({"name": "Ntinda Motors", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "Plot 1",
        "phone": "+256 700 111222", "registration_no": "r", "honest_declaration": True}),))[0][0]
as_(A, "select admin_decide_garage(%s,'approve')", (g,))
KEYS = ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']
def car(i, plate):
    return {"vin": "JTEBU3FJ10K%06d" % i, "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic", "body": "SUV", "colour": "White",
            "engine": "2.0", "mileage": 84000, "plate": plate, "country": "UG", "region": "Kampala", "price": 95000000,
            "description": "Clean Harrier, one owner in Uganda, full service history.", "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
def inspect(l, fail=False):
    c = su("select id from conversations where listing_id=%s and status='in_play'", (l,))[0][0]
    as_(O, "select send_message(%s,'Hello, we can inspect Tuesday')", (c,)); as_(S, "select seller_respond(%s,true)", (c,))
    r = as_(O, "select start_review(%s)", (l,))[0][0]
    checks = {k: "pass" for k in KEYS}
    if fail: checks["brakes"] = "fail"
    as_(O, "select save_review(%s,%s)", (r, json.dumps({"checks": checks, "odometer": 84500, "in_person": True, "notes": "Brake pads worn through, discs scored." if fail else ""})))
    return as_(O, "select issue_review(%s)", (r,))[0][0]

# ---- switch off: today's rule ----
check("the switch starts off, and visitors can read it", as_(None, "select value from settings where key='open_market'")[0][0] is False)
L1 = as_(S, "select save_listing(%s)", (json.dumps(car(1, "UBA 001A")),))[0][0]
check("off: listing without an inspection is refused", "needs a Saaz inspection" in (err(S, "select submit_listing(%s, false)", (L1,)) or ""))
check("off: submitting still asks for an inspection", as_(S, "select submit_listing(%s)", (L1,)) is not None and st(L1) == "awaiting_review")
res = inspect(L1); as_(A, "select admin_decide_listing(%s,'approve')", (L1,))
check("off: the usual path still goes live", st(L1) == "live")
check("off: buyers can't ask for inspections", "not open yet" in (err(B, "select buyer_request_inspection(%s)", (L1,)) or ""))

# ---- switch on ----
market(True)
check("visitors can read the switch", as_(None, "select value from settings where key='open_market'")[0][0] is True)
L2 = as_(S, "select save_listing(%s)", (json.dumps(car(2, "UBA 002A")),))[0][0]
as_(S, "select submit_listing(%s, false)", (L2,))
check("on: list now goes to Saaz approval, no garage line", st(L2) == "awaiting_approval" and su("select count(*) from conversations where listing_id=%s", (L2,))[0][0] == 0
      and su("select count(*) from reviews where listing_id=%s", (L2,))[0][0] == 0)
check("Saaz is told a car waits, not inspected", any("not inspected" in n[0] for n in notes(A, "listing_submitted")))
check("not public before approval", as_(None, "select count(*) from browse_listings('UG')")[0][0] == 1)
as_(A, "select admin_decide_listing(%s,'approve')", (L2,))
check("approved: live, with no inspection", st(L2) == "live" and su("select current_review_id from listings where id=%s", (L2,))[0][0] is None)
cards = {c[0]["ref"]: c[0] for c in as_(None, "select browse_listings('UG')")}
ref2 = su("select ref from listings where id=%s", (L2,))[0][0]
check("the card says no inspection and none requested", cards[ref2]["review"] is None and cards[ref2]["inspection_requested"] is False, cards[ref2])
check("a buyer can make an offer on a Not inspected car", as_(B2, "select make_offer(%s, 90000000, false, 'As it is')", (L2,))[0][0]["status"] == "negotiating")

# A buyer asks for a Saaz inspection
check("visitors can't ask", err(None, "select buyer_request_inspection(%s)", (L2,)) is not None)
check("the seller can't ask as a buyer", "your car" in (err(S, "select buyer_request_inspection(%s)", (L2,)) or ""))
q = as_(B, "select buyer_request_inspection(%s)", (L2,))[0][0]
check("buyer asks: an inspection ID", q["inspection_id"].startswith("SZR-"), q)
check("the car stays on sale", st(L2) == "live")
check("the card shows an inspection on its way", [c[0] for c in as_(None, "select browse_listings('UG')") if c[0]["ref"] == ref2][0]["inspection_requested"] is True)
check("asking twice is refused", "already on its way" in (err(B2, "select buyer_request_inspection(%s)", (L2,)) or ""))
check("the seller is told, and that the buyer pays", any("buyer pays" in n[0] for n in notes(S, "buyer_inspection_requested")))
c = su("select garage_id from conversations where listing_id=%s and status='in_play'", (L2,))
check("a garage is put in play while the car is on sale", c and c[0][0] == g, c)
check("the garage is told the buyer pays", any("pays your fee" in n[0] for n in notes(O, "garage_in_play")))
check("the buyer's name is in no notice to the garage or seller", not any("Bea" in n[0] for n in notes(O, "garage_in_play") + notes(S, "buyer_inspection_requested")))
check("other buyers can't see who asked", as_(B2, "select count(*) from reviews where requested_by is not null")[0][0] == 0)

# Safety Fail on a car on sale: stays on sale, report on the car, history shows it
res = inspect(L2, fail=True)
check("the buyer learns which garage and its number when the seller books", any("+256 700 111222" in n[0] and "pay the garage" in n[0] for n in notes(B, "buyer_inspection_booked")), notes(B, "buyer_inspection_booked"))
check("booking keeps the car on sale", st(L2) == "live")
check("issued: Fail", res["verdict"] == "fail", res)
check("a Fail does not take the car off sale", st(L2) == "live")
card2 = [c[0] for c in as_(None, "select browse_listings('UG')") if c[0]["ref"] == ref2][0]
check("the report shows on the car for everyone", card2["review"] and card2["review"]["verdict"] == "fail" and card2["inspection_requested"] is False, card2)
check("the buyer who asked is told the result", any("is ready: Fail" in n[0] for n in notes(B, "buyer_inspection_ready")))
check("Saaz is told a car on sale has a new report", any("on sale (Fail)" in n[0] for n in notes(A, "review_issued")))
h = [x[0] for x in as_(None, "select car_history(%s)", (L2,))]
check("visitors see the car's history with the Fail", len(h) == 1 and h[0]["verdict"] == "fail" and h[0]["current"] and "requested_by" not in h[0], h)
check("the open offer is untouched", su("select status from deals where listing_id=%s", (L2,))[0][0] == "negotiating")
check("a buyer can't ask again while the report is valid", "already has a Saaz inspection" in (err(B2, "select buyer_request_inspection(%s)", (L2,)) or ""))

# Seller's own inspection that fails, then approval: shown, not blocked
L3 = as_(S, "select save_listing(%s)", (json.dumps(car(3, "UBA 003A")),))[0][0]
as_(S, "select submit_listing(%s)", (L3,)); inspect(L3, fail=True)
check("on: Saaz can approve a car whose report failed", err(A, "select admin_decide_listing(%s,'approve')", (L3,)) is None and st(L3) == "live")

# Expiry: on, the car stays on sale; a buyer may then ask again
su("update reviews set valid_until = current_date - 1 where id = (select current_review_id from listings where id=%s)", (L1,))
as_(B, "select tick()")
check("on: an expired inspection leaves the car on sale", st(L1) == "live")
check("on: a buyer may ask for a new inspection once it expired", as_(B2, "select buyer_request_inspection(%s)", (L1,))[0][0]["inspection_id"])
su("update reviews set status='cancelled' where listing_id=%s and status='requested'", (L1,))
market(False); as_(B, "select tick()")
check("off again: an expired inspection takes the car off sale, as before", st(L1) == "re_review_due")

# Not public: history of a draft car
L4 = as_(S, "select save_listing(%s)", (json.dumps(car(4, "UBA 004A")),))[0][0]
check("history of a car not on sale is empty for visitors", as_(None, "select count(*) from car_history(%s)", (L4,))[0][0] == 0)
check("the seller sees their own car's history", err(S, "select car_history(%s)", (L4,)) is None)
# Sellers read their own cars' vehicle record (Edit needs the VIN); nobody else does
check("the seller reads their own car's VIN", as_(S, "select count(*) from vehicles v join listings l on l.vehicle_id = v.id where l.id=%s", (L4,))[0][0] == 1)
check("a buyer reads no vehicle records", as_(B, "select count(*) from vehicles")[0][0] == 0)
check("visitors read no vehicle records", as_(None, "select count(*) from vehicles")[0][0] == 0)
print(f"\n{ok} passed, {bad} failed")
