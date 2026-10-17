"""Tests for part 14: inspection IDs from the request, lookup / access / start as separate steps, one inspector per
inspection, scoped inspections, and a race to start. Fresh database."""
import json, threading, psycopg2, admin_session
DSN = dict(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb")
conn = psycopg2.connect(**DSN); conn.autocommit = True; cur = conn.cursor()
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
def status(doc): return su("select status from reviews where doc_no=%s", (doc,))[0][0]

A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name) values (%s,'Ann Admin')", (A,))
S = user("seller@x.test", "Sam Seller"); S2 = user("other@x.test", "Other Seller")
O = user("owner@g.test", "Olga Owner"); I = user("ian@g.test", "Ian Engine"); E = user("eve@g.test", "Eve Electrics")
O2 = user("owner2@h.test", "Hal Owner")
def garage(owner, name):
    g = as_(owner, "select apply_garage(%s)", (json.dumps({"name": name, "business_type": "garage", "country": "UG", "region": "Kampala", "address": "x", "phone": "1", "registration_no": "r", "honest_declaration": True}),))[0][0]
    as_(A, "select admin_decide_garage(%s,'approve')", (g,)); return g
gid = garage(O, "Ntinda Motors"); gid2 = garage(O2, "Other Garage")
for u in (I, E): su("insert into garage_members (garage_id,user_id,role,status,accepted_at) values (%s,%s,'inspector','active',now())", (gid, u))
car = {"vin": "JTEBU3FJ10K123456", "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic",
       "body": "SUV", "colour": "White", "engine": "2.0", "mileage": 84000, "plate": "UBA 123X", "country": "UG", "region": "Kampala",
       "price": 95000000, "description": "Clean Harrier, one owner in Uganda, full service history.", "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
L = as_(S, "select save_listing(%s)", (json.dumps(car),))[0][0]
as_(S, "select submit_listing(%s)", (L,))
gen = su("select doc_no from reviews where listing_id=%s and scope='general'", (L,))[0][0]
check("sending the car for inspection gives the seller an inspection ID", gen.startswith("SZR-") and status(gen) == "requested", gen)
extra = [x[0] for x in as_(S, "select request_inspections(%s, array['engine','electrics'])", (L,))]
eng = [x for x in extra if x["scope"] == "engine"][0]["inspection_id"]; ele = [x for x in extra if x["scope"] == "electrics"][0]["inspection_id"]
check("seller adds scoped inspections, each with its own ID", len({gen, eng, ele}) == 3)
check("asking again for an open scope doesn't make a second one", len(as_(S, "select request_inspections(%s, array['engine'])", (L,))) == 0)
check("another seller can't request inspections on this car", "Not your listing" in (err(S2, "select request_inspections(%s, array['body'])", (L,)) or ""))

# 1-2, 8: lookup, before signing in
check("lookup of an existing ID: found, nothing else", as_(None, "select lookup_inspection(%s)", (gen.lower(),))[0][0] == {"found": True})
check("lookup of a made-up ID: not found, nothing else", as_(None, "select lookup_inspection('SZR-2026-999999')")[0][0] == {"found": False})
check("signed-out visitors can't open an inspection", err(None, "select inspection_access(%s)", (gen,)) is not None)
check("signed-out visitors can't read inspections", as_(None, "select count(*) from reviews where doc_no=%s", (gen,))[0][0] == 0)
check("knowing the ID gives another seller nothing", "isn't linked to your account" in (err(S2, "select inspection_access(%s)", (gen,)) or ""))
check("lookup changes nothing", status(gen) == "requested")

# 3: the seller, after signing in
a = as_(S, "select inspection_access(%s)", (gen,))[0][0]
check("seller sees their inspection: status and car, no start button", a["relation"] == "seller" and a["status"] == "requested" and a["car"]["ref"] and a["can_start"] is False, a)

# Garage line: Ntinda gets the car; the seller agrees
C = su("select id, garage_id from conversations where listing_id=%s and status='in_play'", (L,))[0]
if C[1] != gid:  # make sure our garage is the one in play
    su("update conversations set garage_id=%s where id=%s", (gid, C[0]))
C = C[0]
check("before the seller agrees, the owner can't start", "not booked with your garage" in (err(O, "select start_inspection(%s)", (gen,)) or ""))
as_(O, "select send_message(%s,'Hello, we can inspect Tuesday')", (C,)); as_(S, "select seller_respond(%s,true)", (C,))

# 5: authorization
check("a member of another garage can't start it", "not booked with your garage" in (err(O2, "select start_inspection(%s)", (gen,)) or ""))
check("an inspector not given the inspection can't start it", "given to someone else" in (err(I, "select start_inspection(%s)", (eng,)) or "") or "isn't" in (err(I, "select start_inspection(%s)", (eng,)) or ""))
rid_eng = su("select id from reviews where doc_no=%s", (eng,))[0][0]; rid_ele = su("select id from reviews where doc_no=%s", (ele,))[0][0]
check("only the owner gives out inspections", "Only the owner" in (err(I, "select assign_inspection(%s,%s)", (rid_eng, I)) or ""))
as_(O, "select assign_inspection(%s,%s)", (rid_eng, I)); as_(O, "select assign_inspection(%s,%s)", (rid_ele, E))
check("the booked garage's owner sees the car's requested inspections", as_(O, "select count(*) from reviews where listing_id=%s and status='requested'", (L,))[0][0] == 3)
check("each inspector is told their inspection ID", su("select count(*) from notifications where kind='inspection_assigned' and user_id in (%s,%s)", (I, E))[0][0] == 2)
check("electrics inspector can't start the engine inspection", "given to someone else" in (err(E, "select start_inspection(%s)", (eng,)) or ""))
check("engine inspector can open their inspection, can start", as_(I, "select inspection_access(%s)", (eng,))[0][0]["can_start"] is True)
check("engine inspector sees only their inspection of the car", [x[0]["scope"] for x in as_(I, "select car_inspections(%s)", (L,))] == ["engine"])

# 4 + 7 + race: one inspector starts; the start re-checks; two at once -> one wins
results = []
def start(uid):
    c2 = psycopg2.connect(**DSN); c2.autocommit = True; k = c2.cursor()
    k.execute("select set_config('request.jwt.claims',%s,false)", (admin_session.claims(k, uid),)); k.execute("set role authenticated")
    try: k.execute("select start_inspection(%s)", (gen,)); results.append(("ok", uid))
    except psycopg2.Error as e: results.append((e.diag.message_primary, uid))
    c2.close()
as_(O, "select assign_inspection(%s, %s)", (su("select id from reviews where doc_no=%s", (gen,))[0][0], I))  # general to Ian too
ts = [threading.Thread(target=start, args=(u,)) for u in (I, I, I, O)]
[t.start() for t in ts]; [t.join() for t in ts]
check("four starts at once (double taps and the owner): the inspector gets it, the owner is refused", sorted(r for r in results if r[1] == I) == [("ok", I)] * 3 and [r for r in results if r[1] == O][0][0] != "ok", results)
check("the start is recorded once", su("select count(*) from audit_log where action='inspection started' and entity_id=(select id::text from reviews where doc_no=%s)", (gen,))[0][0] == 1)
check("started: in progress, with one inspector", su("select status, member_id from reviews where doc_no=%s", (gen,))[0] == ("draft", I))
check("the same inspector starting again just continues (no sign-in again)", as_(I, "select start_inspection(%s)", (gen,))[0][0] == su("select id from reviews where doc_no=%s", (gen,))[0][0])
check("nobody else can start an inspection already in progress", "already started" in (err(O, "select start_inspection(%s)", (gen,)) or ""))
check("the owner can't hand an inspection in progress to someone else", "stays with the inspector" in (err(O, "select assign_inspection(%s, %s)", (su("select id from reviews where doc_no=%s", (gen,))[0][0], E)) or ""))
as_(E, "select start_inspection(%s)", (ele,))
check("two inspectors work on two scopes of the same car", su("select count(*) from reviews where listing_id=%s and status='draft'", (L,))[0][0] == 2)

# Scoped issue: only the scope's checks; doesn't make the car live; booking stays open while others are open
ele_id = su("select id from reviews where doc_no=%s", (ele,))[0][0]
check("electrics report needs only its checks", "engine is missing" not in (err(E, "select issue_review(%s)", (ele_id,)) or ""))
as_(E, "select save_review(%s,%s)", (ele_id, json.dumps({"checks": {"electrics": "advise", "odometer": "pass", "vin": "pass"}, "notes": "Rear window motor slow.", "odometer": 84100, "in_person": True})))
r = as_(E, "select issue_review(%s)", (ele_id,))[0][0]
check("electrics report issued with its own ID", r["doc_no"] == ele and r["scope"] == "electrics" and r["live"] is False, r)
check("a scoped report doesn't change the car's status", su("select status from listings where id=%s", (L,))[0][0] == "review_booked")
check("booking stays open while other inspections are open", su("select status from conversations where id=%s", (C,))[0][0] == "agreed")
check("an issued inspection can't be started again", "already completed" in (err(E, "select start_inspection(%s)", (ele,)) or ""))
d = as_(S, "select review_document(%s)", (r["verify_code"],))[0][0]
check("the report names its scope", d["scope"]["key"] == "electrics" and d["intact"] is True, d["scope"])

# Stopping an inspection keeps the ID with the same inspector
gid_rev = su("select id from reviews where doc_no=%s", (gen,))[0][0]
as_(I, "select discard_review(%s)", (gid_rev,))
check("stopping puts it back to requested, same ID, same inspector", su("select status, inspector_id, member_id from reviews where doc_no=%s", (gen,))[0] == ("requested", I, None))

# 6: cancelled inspections can't be started; withdrawing cancels the open ones
as_(S, "select withdraw_listing(%s)", (L,))
check("withdrawing the car cancels its open inspections", status(gen) == "cancelled" and status(eng) == "cancelled" and status(ele) == "issued")
check("a cancelled inspection can't be started", "cancelled" in (err(I, "select start_inspection(%s)", (gen,)) or ""))
a = as_(S, "select inspection_access(%s)", (gen,))[0][0]
check("the seller sees why: cancelled, with the reason", a["status"] == "cancelled" and "withdrawn" in (a["cancel_reason"] or ""), a)

# 9: every change is in the history
acts = [x[0] for x in su("select action from audit_log where entity='review' and entity_id=%s order by at", (str(gid_rev),))]
check("the inspection's history: requested, given, started, stopped, cancelled", acts[:1] == ["inspection requested"] and "inspection started" in acts and "inspection cancelled" in acts and any(x.startswith("inspection given to") for x in acts), acts)
print(f"\n{ok} passed, {bad} failed")
