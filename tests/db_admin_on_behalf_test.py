"""Tests for part 11: an admin acts for a seller or buyer, with a reason, and it is all in the history. Fresh database."""
import json, psycopg2, admin_session
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def as_(uid, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, uid),)); cur.execute("set role authenticated")
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
def act(kind, target, reason, p=None): return as_(A, "select admin_act(%s,%s,%s,%s)", (kind, target, reason, json.dumps(p or {})))[0][0]
def act_err(kind, target, reason, p=None, who=None): return err(who or A, "select admin_act(%s,%s,%s,%s)", (kind, target, reason, json.dumps(p or {})))
WHY = "Seller called, can't use the app on their phone"

A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name) values (%s,'Ann Admin')", (A,))
S = user("seller@x.test", "Sam Seller"); B = user("buyer@x.test", "Bob Buyer"); B2 = user("buyer2@x.test", "Bea Buyer")
car = {"vin": "JTEBU3FJ10K123456", "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic",
       "body": "SUV", "colour": "White", "engine": "2.0", "mileage": 84000, "plate": "UBA 123X", "country": "UG", "region": "Kampala",
       "price": 95000000, "description": "Clean Harrier, one owner in Uganda, full service history.",
       "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
L = as_(S, "select save_listing(%s)", (json.dumps(car),))[0][0]

# Guards
check("a reason is required", "reason" in (act_err("price", L, "short", {"price": 90000000}) or ""))
check("sellers can't use admin_act", act_err("price", L, WHY, {"price": 1}, who=S) == "Admins only.")
check("admin can't change a seller's price without admin_act", "Not your listing" in (err(A, "select change_price(%s,%s)", (L, 90000000)) or ""))
cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, B),))
cur.execute("select set_config('saaz.acting',%s,false)", (json.dumps({"listing": str(L), "side": "seller", "for": str(S), "reason": "x"}),)); cur.execute("set role authenticated")
try: cur.execute("select change_price(%s,%s)", (L, 1000000)); forged = True
except psycopg2.Error: forged = False
cur.execute("reset role; select set_config('saaz.acting','',false)")
check("a buyer who forges the acting setting gets nothing", not forged and su("select price from listings where id=%s", (L,))[0][0] == 95000000)

# Price, for the seller
act("price", L, WHY, {"price": 90000000})
check("admin changed the price for the seller", su("select price from listings where id=%s", (L,))[0][0] == 90000000)
row = su("select actor_id, actor_role, detail from audit_log where entity='listing' and entity_id=%s and action='price changed'", (str(L),))[0]
check("price row: actor is the admin, role admin, for the seller, with reason", row[0] == A and row[1] == "admin" and row[2]["for_user"] == str(S) and row[2]["reason"] == WHY and row[2]["before"] == 95000000, row)
check("summary row says the team acted for the seller", su("select count(*) from audit_log where action like 'Saaz team acted for the seller: changed the asking price%%'")[0][0] == 1)
n = su("select body from notifications where user_id=%s and kind='admin_acted'", (S,))
check("seller told, with the reason", n and WHY in n[0][0] and "90,000,000" in n[0][0], n)
h = as_(S, "select who, action from listing_history(%s)", (L,))
check("seller sees it in the car's history with the reason", any(w == "Our team" and "price changed" in a and WHY in a for w, a in h), h)
check("the rules still apply: minimum price", "lowest asking price" in (act_err("price", L, WHY, {"price": 5}) or ""))

# Offer rules and stage moves, for the seller
act("offer_rules", L, WHY, {"rules": {"min_pct": 80, "auto_reject": False}})
check("offer rules changed for the seller", su("select rule_min_pct from listings where id=%s", (L,))[0][0] == 80)
act("submit", L, WHY)
check("admin moved the car to inspection for the seller", su("select status from listings where id=%s", (L,))[0][0] == "awaiting_review")
G = su("insert into garages (name,business_type,country,region,address,phone,registration_no,specialties,honest_declaration,status) values ('Kampala Motors','garage','UG','Kampala','x','1','r','{}',true,'certified') returning id")[0][0]
C = su("insert into conversations (listing_id, garage_id, status, assigned_by_admin, round, opened_at, garage_first_message_at) values (%s,%s,'in_play',false,1,now(),now()) returning id", (L, G))[0][0]
su("update conversations set status='closed' where listing_id=%s and id<>%s", (L, C))
act("garage_agree", C, WHY)
check("admin agreed to the garage for the seller", su("select status from listings where id=%s", (L,))[0][0] == "review_booked")
check("the conversation row is stamped too", su("select actor_id from audit_log where entity='conversation' and entity_id=%s and action='agreed'", (str(C),))[0][0] == A)

# Deals
su("update listings set status='live' where id=%s", (L,))
D = as_(B, "select make_offer(%s,%s,false,'')", (L, 80000000))[0][0]["deal"]
act("deal_seller", D, WHY, {"action": "counter", "amount": 88000000})
e = su("select by_side, admin_id, admin_reason, amount from deal_events where deal_id=%s order by created_at desc limit 1", (D,))[0]
check("counter for the seller: event shows the admin and reason", e == ("seller", A, WHY, 88000000), e)
check("buyer told about the new figure", su("select count(*) from notifications where user_id=%s and kind='deal_counter'", (B,))[0][0] == 1)
check("admin can't accept a figure an admin entered", "other side must confirm" in (act_err("deal_buyer", D, WHY, {"action": "accept"}) or ""))
as_(B, "select deal_action(%s,'counter',%s)", (D, 86000000))
act("deal_seller", D, WHY, {"action": "accept"})
check("admin accepted the buyer's real counter for the seller: agreed", su("select status from deals where id=%s", (D,))[0][0] == "agreed")
check("car reserved", su("select status from listings where id=%s", (L,))[0][0] == "reserved")
v = as_(B, "select deal_view(%s)", (D,))[0][0]
check("buyer's deal page shows the admin's reason", any(x.get("admin_reason") == WHY for x in v["events"]))
h = as_(S, "select action from listing_history(%s)", (L,))
check("car history includes the deal steps", any("counter" in a[0] for a in h) and any("accept" in a[0] for a in h), h)

L2 = as_(S, "select save_listing(%s)", (json.dumps({**car, "vin": "JTEBU3FJ10K654321", "plate": "UBB 456Y"}),))[0][0]
su("update listings set status='live' where id=%s", (L2,))
D2 = as_(B2, "select make_offer(%s,%s,false,'')", (L2, 70000000))[0][0]["deal"]
check("buyer action needs a valid action", "can counter, accept or withdraw" in (act_err("deal_buyer", D2, WHY, {"action": "reject"}) or ""))
D3 = as_(B, "select make_offer(%s,%s,false,'')", (L2, 72000000))[0][0]["deal"]
act("deal_buyer", D3, "Buyer phoned to withdraw, travelling", {"action": "withdraw"})
check("admin withdrew an offer for the buyer", su("select status from deals where id=%s", (D3,))[0][0] == "withdrawn")
check("buyer told, with the reason", "travelling" in su("select body from notifications where user_id=%s and kind='admin_acted' order by created_at desc limit 1", (B,))[0][0])
check("admin can't withdraw a buyer's offer without admin_act", "withdraw only an open offer" in (err(A, "select deal_action(%s,'withdraw')", (D2,)) or ""))
act("withdraw", L2, WHY)
check("admin withdrew the car for the seller", su("select status from listings where id=%s", (L2,))[0][0] == "withdrawn")
check("acting setting is cleared after each action", su("select coalesce(current_setting('saaz.acting', true),'')")[0][0] == "")
check("every admin row in the log names who it was for", su("select count(*) from audit_log where actor_id=%s and actor_role='admin' and not (detail ? 'for_user')", (A,))[0][0] == 0)
print(f"\n{ok} passed, {bad} failed")
