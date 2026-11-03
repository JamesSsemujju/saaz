"""Part 23 Promotions (prize draw). Runs inside one transaction and rolls back, so the database is left as it was.
Checks: the master switch, who may do what, the permit gate, entry rules (one per account, Saaz team out, confirmed email,
T&C version, mobile, codes, sources), fraud flags, locked entries, the draw (once, closed only, valid entries only, reproducible
from the seed), reserves stepping up, the winner notice, export logged, the report, personal details cleared after retention,
and that visitors and other people can't read any of it.
Run: python3 tests/db_promotions_test.py  (after tests/stack/reset.sh)"""
import json, hashlib, psycopg2, admin_session, sys
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname=sys.argv[1] if len(sys.argv) > 1 else "sb")
cur = conn.cursor()  # not autocommit: rolled back at the end
passed = failed = 0
def su(sql, args=()):
    cur.execute("reset role; select set_config('request.jwt.claims','',true); select set_config('request.headers','',true)"); cur.execute(sql, args)
    return cur.fetchall() if cur.description else None
def as_(uid, sql, args=(), ip="10.0.0.1"):
    claims = admin_session.claims(cur, uid) if uid else ""
    cur.execute("reset role; select set_config('request.jwt.claims',%s,true); select set_config('request.headers',%s,true)", (claims, json.dumps({"x-forwarded-for": ip})))
    cur.execute("set local role " + ("authenticated" if uid else "anon")); cur.execute("savepoint s")
    try:
        cur.execute(sql, args); r = cur.fetchall() if cur.description else None; cur.execute("release savepoint s"); return r
    except psycopg2.Error:
        cur.execute("rollback to savepoint s"); raise
    finally:
        cur.execute("reset role")
def one(uid, sql, args=(), ip="10.0.0.1"): return as_(uid, sql, args, ip)[0][0]
def err(uid, sql, args=(), ip="10.0.0.1"):
    try: as_(uid, sql, args, ip); return None
    except psycopg2.Error as e: return e.diag.message_primary
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name, extra)
def user(email, name, confirmed=True):
    return su("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s, %s, %s) returning id",
              (email, json.dumps({"name": name, "country": "UG", "mobile": "+256700000000"}), "2026-11-01" if confirmed else None))[0][0]

A = user("pr-admin@saaz.test", "Ada Admin"); su("insert into public.admins (user_id, name) values (%s,'Ada Admin')", (A,))
ST = user("pr-staff@saaz.test", "Sid Staff"); su("insert into public.admins (user_id, name, role) values (%s,'Sid Staff','staff')", (ST,))
B = [user("pr-b%d@x.test" % i, "Buyer %d" % i) for i in range(8)]
U = user("pr-unconfirmed@x.test", "Una Unconfirmed", confirmed=False)
enter = lambda uid, slug, p, ip="10.0.0.1": err(uid, "select promotion_enter(%s, %s)", (slug, json.dumps(p)), ip)
def entry(i, **k):
    d = {"name": "Buyer Number %d" % i, "mobile": "0772 12345%d" % i, "current_car": "Toyota Premio", "dream_car": "Toyota Harrier",
         "terms_version": "v1", "terms": True, "marketing_ok": i % 2 == 0, "whatsapp_ok": True, "source": "radio"}
    d.update(k); return d

# 1. The switch starts off, and only full admins can change it
check("switch starts off", one(None, "select promotion_public('current')") == {"running": False})
check("staff can't switch promotions on", err(ST, "select admin_promotion_switch(true, null)") is not None)
check("a buyer can't switch promotions on", err(B[0], "select admin_promotion_switch(true, null)") is not None)
check("a visitor can't call admin functions", err(None, "select admin_promotions()") is not None)
check("staff can't open the Promotions admin (entries are personal data)", err(ST, "select admin_promotions()") is not None)

# 2. A full admin builds a draft; it can't open without the permit and terms
P = one(A, "select admin_promotion_save(null, %s)", (json.dumps({"slug": "win-a-car", "title": "Win a car"}),))
check("a draft is created", P is not None)
check("can't open without a permit number", "permit" in (err(A, "select admin_promotion_status(%s,'open',null)", (P,)) or ""))
one(A, "select admin_promotion_save(%s, %s)", (P, json.dumps({"permit_no": "LGRB-TEST-1"})))
check("can't open without terms", "terms" in (err(A, "select admin_promotion_status(%s,'open',null)", (P,)) or ""))
one(A, "select admin_promotion_save(%s, %s)", (P, json.dumps({"terms": "Test terms.", "terms_version": "v1", "prize": "A Toyota Premio (placeholder)",
      "opens_at": "2026-11-01T00:00:00+03:00", "closes_at": "2030-01-01T00:00:00+03:00", "winners": 1, "reserves": 2})))
check("a bad slug is refused", err(A, "select admin_promotion_save(null, %s)", (json.dumps({"slug": "Bad Slug!", "title": "X car"}),)) is not None)
DR = one(A, "select admin_promotion_save(null, %s)", (json.dumps({"slug": "secret-draft", "title": "Draft only"}),))
one(A, "select admin_promotion_link(%s,'radio','CBS radio spot')", (P,))
C = one(A, "select admin_promotion_code(%s,'GARAGE1','Kampala Motors',2,true)", (P,))
check("staff can't edit a promotion", err(ST, "select admin_promotion_save(%s, %s)", (P, json.dumps({"title": "Hacked"}))) is not None)
check("opens with everything in place", one(A, "select admin_promotion_status(%s,'open',null)", (P,)) == "open")
check("switch still off: nothing public", one(None, "select promotion_public('current')") == {"running": False})
check("switch still off: entries refused", "No promotion" in (enter(B[0], "win-a-car", entry(0)) or ""))
check("switching off needs no state change error when already off", err(A, "select admin_promotion_switch(false, 'reason long enough')") is not None)
one(A, "select admin_promotion_switch(true, null)")
pub = one(None, "select promotion_public('current')")
check("switch on: the open promotion is public", pub.get("running") and pub["promotion"]["slug"] == "win-a-car" and pub["promotion"]["open"])
check("a draft is not public even with the switch on", one(None, "select promotion_public('secret-draft')") == {"running": False})
check("public view carries no admin fields", not any(k in json.dumps(pub) for k in ("created_by", "retention", "LGRB-TEST-1x")) and "permit_no" in pub["promotion"])
check("only summary and a later close can change once open", err(A, "select admin_promotion_save(%s, %s)", (P, json.dumps({"terms": "Changed"}))) is not None
      and err(A, "select admin_promotion_save(%s, %s)", (P, json.dumps({"summary": "Enter by 31 Dec."}))) is None)

# 3. Entry rules
check("a visitor can't enter", err(None, "select promotion_enter('win-a-car', '{}')") is not None)
check("Saaz team can't enter", "team" in (enter(A, "win-a-car", entry(0)) or ""))
check("unconfirmed email can't enter", "Confirm" in (enter(U, "win-a-car", entry(0)) or ""))
check("T&C must be ticked", "terms" in (enter(B[0], "win-a-car", entry(0, terms=False)) or ""))
check("old T&C version refused", "terms changed" in (enter(B[0], "win-a-car", entry(0, terms_version="v0")) or ""))
check("a bad mobile is refused", "mobile" in (enter(B[0], "win-a-car", entry(0, mobile="12345")) or ""))
check("dream car is required", "next" in (enter(B[0], "win-a-car", entry(0, dream_car="")) or ""))
check("a wrong code is refused", "code" in (enter(B[0], "win-a-car", entry(0, code="NOPE")) or ""))
check("a valid entry is accepted", enter(B[0], "win-a-car", entry(0, code="garage1")) is None)
check("mobile stored in +256 form", su("select mobile from promo_entries where user_id=%s", (B[0],))[0][0] == "+256772123450")
check("one entry per account", "already" in (enter(B[0], "win-a-car", entry(0)) or ""))
check("their own entry shows on the page", one(B[0], "select promotion_public('win-a-car')")["my_entry"]["status"] == "entered")
check("someone else's page shows no entry", one(B[1], "select promotion_public('win-a-car')")["my_entry"] is None)
check("an unknown source is stored as direct", enter(B[1], "win-a-car", entry(1, source="evil<script>"), ip="10.0.0.2") is None
      and su("select source from promo_entries where user_id=%s", (B[1],))[0][0] == "direct")
check("code use limit holds", enter(B[2], "win-a-car", entry(2, code="GARAGE1"), ip="10.0.0.3") is None and "used up" in (enter(B[3], "win-a-car", entry(3, code="GARAGE1"), ip="10.0.0.4") or ""))
for i in (3, 4): enter(B[i], "win-a-car", entry(i), ip="10.0.0.9")
check("two entries from one address are not flagged", su("select count(*) from promo_entries where status='flagged'")[0][0] == 0)
enter(B[5], "win-a-car", entry(5), ip="10.0.0.9"); enter(B[6], "win-a-car", entry(6), ip="10.0.0.9")
check("the 4th entry from one address is flagged", su("select count(*) from promo_entries where status='flagged'")[0][0] == 1)
check("network address stored only as a hash", su("select count(*) from promo_entries where ip_hash like '%%10.0.0%%'")[0][0] == 0)

# 4. Nobody but full admins reads entries
for who, uid in (("visitor", None), ("buyer", B[1]), ("staff", ST)):
    check(f"{who}: no direct read of entries", err(uid, "select count(*) from promo_entries") is not None)
    check(f"{who}: no direct read of promotions, codes or the salt", all(err(uid, "select count(*) from " + t) is not None for t in ("promotions", "promo_codes", "promo_secret", "promo_results")))
    check(f"{who}: no admin view of the entries", err(uid, "select admin_promotion(%s)", (P,)) is not None)
    check(f"{who}: can't change an entry", err(uid, "select admin_promotion_entry(e.id,'invalid','reason long enough') from promo_entries e limit 1") is not None)
check("a buyer can't write an entry directly", err(B[7], "insert into promo_entries (promotion_id, user_id, name, terms_version) values (%s, auth.uid(), 'x', 'v1')", (P,)) is not None)

# 5. Admin view, export, flags
v = one(A, "select admin_promotion(%s, null, null, null, 1, 50, false)", (P,))
check("admin sees every entry", v["total"] == 7, v["total"])
check("search by name works", one(A, "select admin_promotion(%s, 'Number 5')", (P,))["total"] == 1)
check("filter by source works", one(A, "select admin_promotion(%s, null, null, 'radio')", (P,))["total"] == 6)
n_audit = su("select count(*) from audit_log where action='promotion entries exported'")[0][0]
one(A, "select admin_promotion(%s, null, null, null, 1, 50, true)", (P,))
check("export is logged", su("select count(*) from audit_log where action='promotion entries exported'")[0][0] == n_audit + 1)
check("links and codes show their counts", v["links"][0]["entries"] == 6 and v["codes"][0]["uses"] == 2)
check("can't draw while open", "Close" in (err(A, "select admin_promotion_draw(%s,'Witness Name')", (P,)) or ""))
one(A, "select admin_promotion_status(%s,'closed',null)", (P,))
check("closed: entries refused", "not open" in (enter(B[7], "win-a-car", entry(7), ip="10.0.0.7") or ""))
check("can't draw with flagged entries left", "flagged" in (err(A, "select admin_promotion_draw(%s,'Witness Name')", (P,)) or ""))
FL = su("select id from promo_entries where status='flagged'")[0][0]
check("changing an entry needs a reason", err(A, "select admin_promotion_entry(%s,'invalid','short')", (FL,)) is not None)
one(A, "select admin_promotion_entry(%s,'invalid','Same household as entry 4, checked by phone')", (FL,))
check("the draw needs a witness", err(A, "select admin_promotion_draw(%s,'')", (P,)) is not None)

# 6. The draw
d = one(A, "select admin_promotion_draw(%s,'LGRB supervisor (test)')", (P,))
check("draw runs on valid entries only", d["entries_in_draw"] == 6, d)
check("draw runs once", err(A, "select admin_promotion_draw(%s,'Witness Name')", (P,)) is not None and su("select count(*) from promo_draws where promotion_id=%s", (P,))[0][0] == 1)
res = su("select r.rank, r.role, r.entry_id from promo_results r where r.promotion_id=%s order by rank", (P,))
check("1 winner and 2 reserves picked", [r[1] for r in res] == ["winner", "reserve", "reserve"], res)
ids = sorted([str(r[0]) for r in su("select id from promo_entries where promotion_id=%s and status='valid'", (P,))], key=lambda i: (hashlib.md5((d["seed"] + i).encode()).hexdigest(), i))
check("anyone with the seed and the entry list gets the same order", [str(r[2]) for r in res] == ids[:3])
check("the invalid entry was not drawn", FL not in [r[2] for r in res])
try:
    su("savepoint t"); su("update promo_draws set seed='x'"); check("draw row locked against edits", False)
except psycopg2.Error:
    cur.execute("rollback to savepoint t"); check("draw row locked against edits", True)
W = su("select id, entry_id from promo_results where promotion_id=%s and rank=1", (P,))[0]
wuser = su("select user_id from promo_entries where id=%s", (W[1],))[0][0]
check("drawing doesn't tell the winner yet", su("select count(*) from notifications where user_id=%s and kind='promotion_winner'", (wuser,))[0][0] == 0)
one(A, "select admin_promotion_result(%s,'contacted',null)", (W[0],))
check("contacting sends the in-app notice", su("select count(*) from notifications where user_id=%s and kind='promotion_winner'", (wuser,))[0][0] == 1)
check("stepping down needs a note", err(A, "select admin_promotion_result(%s,'no_reply','x')", (W[0],)) is not None)
one(A, "select admin_promotion_result(%s,'no_reply','No reply after 14 days, called 3 times')", (W[0],))
roles = [r[0] for r in su("select role from promo_results where promotion_id=%s order by rank", (P,))]
check("first reserve steps up when a winner doesn't reply", roles == ["stepped_down", "winner", "reserve"], roles)
check("a reserve can't be moved directly", err(A, "select admin_promotion_result(id,'contacted',null) from promo_results where promotion_id=%s and rank=3" % ("'" + str(P) + "'",)) is not None)
check("entries lock after the draw", err(A, "select admin_promotion_entry(%s,'valid','Changing after the draw')", (FL,)) is not None)
check("a drawn promotion can't be edited", err(A, "select admin_promotion_save(%s, %s)", (P, json.dumps({"summary": "x"}))) is not None)

# 7. Report
r = one(A, "select admin_promotion_report(%s)", (P,))
check("report counts reconcile", r["total"] == 7 and r["valid"] == 6 and r["invalid"] == 1 and sum(x["n"] for x in r["by_source"]) == 7 and sum(x["n"] for x in r["by_day"]) == 7, r)
check("report counts consent separately", r["marketing_ok"] == su("select count(*) from promo_entries where promotion_id=%s and marketing_ok", (P,))[0][0])
check("report shows dream cars", r["top_dream_cars"][0]["car"] == "Toyota Harrier")

# 8. Retention
su("update promotions set opens_at = now() - interval '230 days', closes_at = now() - interval '200 days', updated_at = now() - interval '200 days' where id=%s", (P,))
one(A, "select admin_promotions()")
check("personal details cleared after the retention period", su("select count(*) from promo_entries where promotion_id=%s and (name <> '' or mobile is not null or email is not null)", (P,))[0][0] == 0)
check("counts survive the clearing", one(A, "select admin_promotion_report(%s)", (P,))["total"] == 7)

# 9. Switching off
check("switching off needs a reason", err(A, "select admin_promotion_switch(false, '')") is not None)
one(A, "select admin_promotion_switch(false, 'Paused while the permit is renewed')")
check("switch off: page says nothing is running", one(None, "select promotion_public('win-a-car')") == {"running": False})
check("switch history kept", len(one(A, "select admin_promotions()")["toggles"]) == 2)
try:
    su("savepoint t"); su("update promo_toggles set enabled = true"); check("switch history can't be edited", False)
except psycopg2.Error:
    cur.execute("rollback to savepoint t"); check("switch history can't be edited", True)

conn.rollback()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
