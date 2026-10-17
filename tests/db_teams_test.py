"""Tests for part 13: owner and inspector access inside a garage, Saaz support/objection instead of edits,
Saaz team roles (Admin, Staff), and inspection IDs. Fresh database."""
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

A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name) values (%s,'Ann Admin')", (A,))
S = user("seller@x.test", "Sam Seller"); O = user("owner@g.test", "Olga Owner"); I = user("ian@g.test", "Ian Inspector"); J = user("jo@g.test", "Jo Inspector")
gid = as_(O, "select apply_garage(%s)", (json.dumps({"name": "Ntinda Motors", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "x", "phone": "1", "registration_no": "r", "honest_declaration": True}),))[0][0]
as_(A, "select admin_decide_garage(%s,'approve')", (gid,))
for u in (I, J): su("insert into garage_members (garage_id,user_id,role,status,accepted_at) values (%s,%s,'inspector','active',now())", (gid, u))
car = {"vin": "JTEBU3FJ10K123456", "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic",
       "body": "SUV", "colour": "White", "engine": "2.0", "mileage": 84000, "plate": "UBA 123X", "country": "UG", "region": "Kampala",
       "price": 95000000, "description": "Clean Harrier, one owner in Uganda, full service history.", "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
L = as_(S, "select save_listing(%s)", (json.dumps(car),))[0][0]; as_(S, "select submit_listing(%s)", (L,))
C = su("select id from conversations where listing_id=%s and status='in_play'", (L,))[0][0]

# ----- Garage: owner and inspector -----
check("owner sees the offered job", len(as_(O, "select garage_jobs()")) == 1)
check("inspector sees no jobs until given one", len(as_(I, "select garage_jobs()")) == 0)
check("inspector can't read the job or the car", as_(I, "select count(*) from conversations")[0][0] == 0 and as_(I, "select count(*) from listings where id=%s", (L,))[0][0] == 0)
check("inspector can't message the seller on someone else's job", "not part of this conversation" in (err(I, "select send_message(%s,'hi')", (C,)) or ""))
check("inspector can't see the team", "Only the garage owner" in (err(I, "select garage_team(null)") or "") and as_(I, "select count(*) from garage_members")[0][0] == 1)
check("only the owner gives out jobs", "owner can give out jobs" in (err(I, "select assign_job(%s,%s)", (C, I)) or ""))
as_(O, "select assign_job(%s,%s)", (C, I))
check("inspector told about the job", su("select count(*) from notifications where user_id=%s and kind='job_assigned'", (I,))[0][0] == 1)
check("inspector now sees exactly that job", len(as_(I, "select garage_jobs()")) == 1 and len(as_(J, "select garage_jobs()")) == 0)
as_(I, "select send_message(%s,'Hello, when can you bring the car?')", (C,))
as_(S, "select send_message(%s,'Tuesday works')", (C,))
check("seller's message reaches the owner and the job's inspector, not other inspectors",
      su("select count(*) from notifications where kind='seller_message' and user_id in (%s,%s)", (O, I))[0][0] == 2 and su("select count(*) from notifications where kind='seller_message' and user_id=%s", (J,))[0][0] == 0)
check("other inspector can't read the messages", as_(J, "select count(*) from messages")[0][0] == 0)
check("only the owner declines", "Only the garage owner can decline" in (err(I, "select garage_respond(%s,'decline')", (C,)) or ""))
as_(S, "select seller_respond(%s,true)", (C,))
as_(I, "select garage_respond(%s,'set_date','2026-10-22')", (C,))
check("inspector sets the inspection date on their job", su("select review_date from conversations where id=%s", (C,))[0][0] is not None)
check("owner can't start a report on a job given to an inspector", "given to someone else" in (err(O, "select start_review(%s)", (L,)) or ""))
check("other inspector can't start it", "not booked with your garage" in (err(J, "select start_review(%s)", (L,)) or "") or "given to someone else" in (err(J, "select start_review(%s)", (L,)) or ""))

# ----- Inspection IDs -----
R = as_(I, "select start_review(%s)", (L,))[0][0]
doc = su("select doc_no from reviews where id=%s", (R,))[0][0]
check("the inspection gets its ID when it starts", doc and doc.startswith("SZR-") and len(doc) == 15, doc)
check("inspector opens it by its ID", as_(I, "select open_inspection(%s)", (doc.lower(),))[0][0]["id"] == str(R))
check("other inspector can't open it by ID", "isn't linked to your account" in (err(J, "select open_inspection(%s)", (doc,)) or ""))
check("owner can open it by ID", as_(O, "select open_inspection(%s)", (doc,))[0][0]["id"] == str(R))
check("owner can't change the inspector's draft", "Only the inspector who started" in (err(O, "select save_review(%s,'{}')", (R,)) or ""))
check("reassigning while a draft exists is refused", "is writing this inspection report" in (err(O, "select assign_job(%s,%s)", (C, J)) or ""))
keys = ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']
as_(I, "select save_review(%s,%s)", (R, json.dumps({"checks": {k: "pass" for k in keys}, "odometer": 84100, "in_person": True})))
res = as_(I, "select issue_review(%s)", (R,))[0][0]
check("the issued report keeps the inspection ID", res["doc_no"] == doc, res)
check("inspector sees their report; the other inspector doesn't", as_(I, "select count(*) from reviews where id=%s", (R,))[0][0] == 1 and as_(J, "select count(*) from reviews where id=%s", (R,))[0][0] == 0)
check("owner sees every report of the garage", as_(O, "select count(*) from reviews where id=%s", (R,))[0][0] == 1)
ins = as_(A, "select car_inspections(%s)", (L,))
check("car's inspection list: each with its ID and garage", len(ins) == 1 and ins[0][0]["doc_no"] == doc and ins[0][0]["garage"] == "Ntinda Motors", ins)
check("seller sees the car's inspection list", len(as_(S, "select car_inspections(%s)", (L,))) == 1)
check("other inspector sees none of it", len(as_(J, "select car_inspections(%s)", (L,))) == 0)

# ----- Saaz never edits a report; it supports or objects, with a reason -----
fp = su("select fingerprint, checks, score from reviews where id=%s", (R,))[0]
check("Saaz can't void a report any more", "does not change inspection reports" in (err(A, "select admin_void_review(%s,'bad report here')", (R,)) or ""))
check("an objection needs a reason", "reason" in (err(A, "select review_opinion(%s,'object','short')", (R,)) or ""))
as_(A, "select review_opinion(%s,'object',%s)", (R, "Tyre photos don't match the advisory"))
check("report content unchanged after the objection", su("select fingerprint, checks, score from reviews where id=%s", (R,))[0] == fp)
check("approval blocked while Saaz objects", "Saaz objected" in (err(A, "select admin_decide_listing(%s,'approve')", (L,)) or ""))
check("garage told about the objection, with the reason", su("select count(*) from notifications where kind='review_object' and user_id in (%s,%s) and body like '%%Tyre photos%%'", (O, I))[0][0] == 2)
check("seller told about the objection", su("select count(*) from notifications where kind='review_object' and user_id=%s", (S,))[0][0] == 1)
check("other inspector can't reply", "owner or the report's author" in (err(J, "select garage_reply_opinion(%s,'We checked the tyres again')", (R,)) or ""))
as_(I, "select garage_reply_opinion(%s,%s)", (R, "Photos were from before the front tyres were swapped"))
doc_view = as_(S, "select review_document(%s)", (res["verify_code"],))[0][0]
check("the report shows Saaz's objection and the garage's reply", doc_view["saaz_stance"] == "object" and [o["stance"] for o in doc_view["opinions"]] == ["object", "garage_reply"], doc_view["opinions"])
v = as_(B := user("pub@x.test", "Pat"), "select verify_review(%s)", (res["verify_code"],))[0][0]
check("the public check shows the objection too", v["saaz_stance"] == "object" and v["intact"] is True, v)
as_(A, "select review_opinion(%s,'support',%s)", (R, "Garage sent new tyre photos, all fine"))
as_(A, "select admin_decide_listing(%s,'approve')", (L,))
check("after Saaz supports the report, approval works", su("select status from listings where id=%s", (L,))[0][0] == "live")
as_(A, "select review_opinion(%s,'object',%s)", (R, "Buyer reported a gearbox fault on test drive"))
check("objecting to a live car takes it off sale", su("select status from listings where id=%s", (L,))[0][0] == "awaiting_approval")
check("nobody can write opinions directly", err(A, "insert into review_opinions (review_id, stance, reason) values (%s,'support','sneaky support')", (R,)) is not None)

# ----- Saaz team: Admin and Staff -----
T = user("tom@saaz.test", "Tom Staff")
check("staff added by an admin", err(A, "select admin_add_staff('tom@saaz.test','staff')") is None)
check("unknown email refused", "No Saaz account" in (err(A, "select admin_add_staff('nobody@x.test','staff')") or ""))
check("new staff told how to start", su("select count(*) from notifications where user_id=%s and kind='saaz_team_added'", (T,))[0][0] == 1)
r = as_(T, "select my_roles()")[0][0]  # helper gives every admins row a pinned factor and aal2 session
check("staff: admin access, not full admin", r["admin"] is True and r["full_admin"] is False and r["admin_role"] == "staff", r)
check("staff can't change settings", "Only a Saaz admin" in (err(T, "select admin_set_setting('garage_response','\"2 days\"'::jsonb)") or ""))
check("staff can't add staff", "Only a Saaz admin" in (err(T, "select admin_add_staff('seller@x.test','staff')") or ""))
check("staff can't suspend accounts", "Only a Saaz admin" in (err(T, "select admin_set_user(%s,'suspended',true)", (S,)) or ""))
check("staff can mark a seller trusted", err(T, "select admin_set_user(%s,'trusted',true)", (S,)) is None)
check("staff can support or object to reports", err(T, "select review_opinion(%s,'support',%s)", (R, "Checked the gearbox report, fine")) is None)
check("nobody makes admins through account flags any more", "Saaz team page" in (err(A, "select admin_set_user(%s,'admin',true)", (S,)) or ""))
lst = as_(A, "select admin_staff_list()")
check("team list shows role and authenticator state", any(x[0]["email"] == "tom@saaz.test" and x[0]["role"] == "staff" for x in lst), lst)
as_(A, "select admin_set_staff_role(%s,'admin')", (T,))
check("admin promotes staff to admin", su("select role from admins where user_id=%s", (T,))[0][0] == "admin")
check("you can't change your own role", "own role" in (err(A, "select admin_set_staff_role(%s,'staff')", (A,)) or ""))
U = user("una@saaz.test", "Una New"); as_(A, "select admin_add_staff('una@saaz.test','staff')")
check("approving an authenticator needs exactly one on the account", "Expected exactly 1" in (err(A, "select admin_pin_staff_authenticator(%s)", (U,)) or ""))
f = su("insert into auth.mfa_factors (user_id, friendly_name, factor_type, status, secret) values (%s,'phone','totp','verified','X') returning id", (U,))[0][0]
as_(A, "select admin_pin_staff_authenticator(%s)", (U,))
check("admin approves a staff authenticator in the app", su("select mfa_factor_id from admins where user_id=%s", (U,))[0][0] == f)
check("you can't approve your own authenticator", "Another admin" in (err(A, "select admin_pin_staff_authenticator(%s)", (A,)) or ""))
su("insert into auth.sessions (user_id, aal, factor_id) values (%s,'aal2',%s)", (U, f))
check("removing staff needs a reason", "reason" in (err(A, "select admin_remove_staff(%s,'x')", (U,)) or ""))
as_(A, "select admin_remove_staff(%s,%s)", (U, "Left Saaz on 18 Oct"))
check("removed staff: off the team and every session ended", su("select count(*) from admins where user_id=%s", (U,))[0][0] == 0 and su("select count(*) from auth.sessions where user_id=%s", (U,))[0][0] == 0)
check("team changes are in the activity log", su("select count(*) from audit_log where action in ('added to the Saaz team','Saaz team role changed','authenticator approved','removed from the Saaz team')")[0][0] == 5)
print(f"\n{ok} passed, {bad} failed")
