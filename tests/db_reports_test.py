"""Tests for part 16: admin reports, slice 1 (Inventory, Listing funnel). Fresh database.
Runs with the session time zone set to UTC, as on the live project, so the East Africa Time rules are really tested.
Reconciliation: every report number is checked against a separate hand-written count of the underlying rows."""
import json, psycopg2, admin_session, datetime as dt
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb", options="-c TimeZone=UTC"); conn.autocommit = True; cur = conn.cursor()
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
S1 = user("s1@x.test", "Sam One"); S2 = user("s2@x.test", "Sue Two"); B = user("b@x.test", "Bob Buyer"); B2 = user("b2@x.test", "Bea Buyer")
T = su("select (now() at time zone 'Africa/Kampala')::date")[0][0]          # today in Kampala
def eat(day_offset, hh=12, mm=0):                                             # a moment in Kampala, as UTC timestamptz text
    d = T + dt.timedelta(days=day_offset)
    return f"{d.isoformat()} {hh:02d}:{mm:02d}:00+03"
LONG = "x" * 200
n = 0
def listing(make, model, price, status, seller=None, saaz=False, photos=8, desc=LONG, created=-60, live=None, updated=None, sold=None):
    global n; n += 1
    vid = su("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTREPORT%09d" % n, make, model))[0][0]
    lid = su("""insert into listings (vehicle_id, seller_id, saaz_owned, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate,
                currency, price, description, photos, logbook_name_matches, owner_authorised, live_at, sold_at, created_at, updated_at)
                values (%s,%s,%s,'UG','Kampala',%s,%s,%s,2015,'Petrol','Automatic','Sedan','White','1.5',80000,%s,'UGX',%s,%s,%s,true,true,%s,%s,%s,%s) returning id""",
             (vid, None if saaz else seller, saaz, status, make, model, "UAR %03dR" % n, price, desc, ["p%d.webp" % i for i in range(photos)],
              eat(live) if live is not None else None, eat(sold) if sold is not None else None, eat(created), eat(updated if updated is not None else created)))[0][0]
    if live is not None: su("insert into audit_log (at, actor_role, entity, entity_id, action) values (%s,'admin','listing',%s,'approve')", (eat(live), str(lid)))
    return lid
L1 = listing("Toyota", "Premio", 30000000, "live", S1, live=-20, updated=-1)
L2 = listing("Toyota", "Premio", 45000000, "live", S1, photos=2, desc="Short.", live=-40, updated=-35)        # dear, few photos, stale
L3 = listing("Toyota", "Premio", 32000000, "sold", S2, live=-10, sold=-2, updated=-2)
L4 = listing("Toyota", "Premio", 33000000, "live", S2, live=-5, updated=-5)
L5 = listing("Subaru", "Forester", 60000000, "awaiting_approval", S2, created=-3)
L6 = listing("Nissan", "Note", 15000000, "draft", S1, photos=0, created=-1)
L7 = listing("Honda", "Fit", 25000000, "withdrawn", S1, live=-30, updated=-4)
su("insert into audit_log (at, actor_role, entity, entity_id, action) values (%s,'seller','listing',%s,'withdrawn')", (eat(-4), str(L7)))
L8 = listing("Mazda", "Atenza", 110000000, "re_review_due", saaz=True, live=-100, updated=-50)
L9 = listing("Toyota", "Premio", 31000000, "sold", S2, live=-25, sold=-12, updated=-12)                         # sold in the previous period
# views: one per viewer per day
for day, lid, k in [(-6, L1, 3), (-5, L1, 2), (-2, L1, 4), (0, L1, 1), (-7, L1, 9), (-3, L2, 5), (-2, L4, 2), (-1, L3, 1), (-9, L4, 4)]:
    for i in range(k): su("insert into listing_views (listing_id, viewer, day) values (%s,%s,%s)", (lid, f"v{i}", T + dt.timedelta(days=day)))
# saves
su("insert into saves (listing_id, user_id, created_at) values (%s,%s,%s), (%s,%s,%s)", (L1, B, eat(-3), L4, B, eat(-10)))
# offers (enquiries). One at 23:30 UTC the night before, which is 02:30 in Kampala: it belongs to the Kampala day, not the UTC day.
def deal(lid, buyer, at): su("insert into deals (listing_id, buyer_id, amount, last_by, status, created_at, updated_at) values (%s,%s,1000000,'buyer','closed',%s,%s)", (lid, buyer, at, at))
deal(L1, B, eat(-15)); deal(L1, B2, f"{(T + dt.timedelta(days=-3)).isoformat()} 23:30:00+00"); deal(L4, B, eat(-1)); deal(L3, B2, eat(-8)); deal(L9, B, eat(-20))
P_FROM, P_TO = T - dt.timedelta(days=6), T
def rep(report, filters=None, **kw):
    a = dict(p_report=report, p_from=P_FROM, p_to=P_TO, p_compare=kw.get("compare", False), p_filters=json.dumps(filters or {}), p_group=kw.get("group"),
             p_sort=kw.get("sort"), p_desc=kw.get("desc", True), p_page=kw.get("page", 1), p_size=kw.get("size", 25), p_export=kw.get("export", False))
    return as_(kw.get("who", A), "select admin_report(%(p_report)s,%(p_from)s,%(p_to)s,%(p_compare)s,%(p_filters)s::jsonb,%(p_group)s,%(p_sort)s,%(p_desc)s,%(p_page)s,%(p_size)s,%(p_export)s)", a)[0][0]
def kpi(r, k): return [x for x in r["kpis"] if x["key"] == k][0]
def refs(r): return sorted(x["ref"] for x in r["rows"])
ref = {lid: su("select ref from listings where id=%s", (lid,))[0][0] for lid in [L1, L2, L3, L4, L5, L6, L7, L8, L9]}

# ---------- access ----------
check("signed-out visitors can't run reports", err(None, "select admin_report('inventory', current_date, current_date)") is not None)
check("a seller can't run reports", "Admin" in (err(S1, "select admin_report('inventory', current_date, current_date)") or "") or err(S1, "select admin_report('inventory', current_date, current_date)") is not None)
check("nobody can read the facts function directly", err(A, "select * from rpt_listing_facts(current_date, current_date)") is not None)
check("an unknown report is refused", "Unknown report" in (err(A, "select admin_report('revenue', current_date, current_date)") or ""))
check("an unknown sort column is refused (no SQL from the browser)", "Unknown sort" in (err(A, "select admin_report('inventory', current_date, current_date, false, '{}', null, 'price; drop table listings')") or ""))

# ---------- Inventory, reconciled against hand counts ----------
inv = rep("inventory")
hand = lambda q: su(q)[0][0]
check("live now = hand count of live and reserved", kpi(inv, "live_now")["value"] == hand("select count(*) from listings where status in ('live','reserved')") == 3)
check("pending now = hand count", kpi(inv, "pending_now")["value"] == hand("select count(*) from listings where status in ('awaiting_review','review_booked','awaiting_approval','changes_requested')") == 1)
check("added in period = hand count (created on or after the start, Kampala dates)", kpi(inv, "added")["value"] == hand(f"select count(*) from listings where (created_at at time zone 'Africa/Kampala')::date between '{P_FROM}' and '{P_TO}'") == 2)
check("sold in period = hand count (L3 only; L9 sold before the period)", kpi(inv, "sold")["value"] == hand(f"select count(*) from listings where status='sold' and (sold_at at time zone 'Africa/Kampala')::date between '{P_FROM}' and '{P_TO}'") == 1)
check("removed in period = withdrawn L7", kpi(inv, "removed")["value"] == 1)
check("stale = L2 and L8 (not updated in 30 days, live/pending/expired)", kpi(inv, "stale")["value"] == hand("select count(*) from listings where status not in ('draft','sold','withdrawn','rejected') and updated_at < now() - interval '30 days'") == 2)
check("no photos = the draft L6", kpi(inv, "no_photos")["value"] == 1)
check("no price is 0 (price is required)", kpi(inv, "no_price")["value"] == 0)
check("every key number opens its rows: live", refs(rep("inventory", {"flag": "live_now"})) == sorted([ref[L1], ref[L2], ref[L4]]))
check("drill: stale", refs(rep("inventory", {"flag": "stale"})) == sorted([ref[L2], ref[L8]]))
check("drill: sold", refs(rep("inventory", {"flag": "sold"})) == [ref[L3]])
for g in ["status_group", "make", "price_band", "age_band"]:
    gr = rep("inventory", group=g)
    check(f"by {g}: the groups add up to all listings", sum(x["count"] for x in gr["groups"]) == gr["total"] == 9, gr["groups"])
gr = {x["value"]: x["count"] for x in rep("inventory", group="status_group")["groups"]}
check("by status: draft 1, pending 1, live 3, sold 2, expired 1, removed 1", gr == {"draft": 1, "pending": 1, "live": 3, "sold": 2, "expired": 1, "removed": 1}, gr)
mk = rep("inventory", group="make"); toy = [x for x in mk["groups"] if x["value"] == "Toyota"][0]["count"]
check("a group's count opens the same number of rows", rep("inventory", {"make": "Toyota"})["total"] == toy == 5)
check("by price band: Mazda is Over 100m", {x["value"]: x["count"] for x in rep("inventory", group="price_band")["groups"]}.get("Over 100m") == 1)
ages = {x["ref"]: x["age_days"] for x in rep("inventory", size=50)["rows"]}
check("days on site: live car counts from first live (L1: 20)", ages[ref[L1]] == 20, ages[ref[L1]])
check("days on site: sold car stops at sold (L3: 8)", ages[ref[L3]] == 8, ages[ref[L3]])
check("days on site: never-live draft counts from created (L6: 1)", ages[ref[L6]] == 1, ages[ref[L6]])
check("filter: Saaz-owned only", refs(rep("inventory", {"seller_type": "saaz"})) == [ref[L8]])
check("filters combine with drill-down", refs(rep("inventory", {"make": "Toyota", "flag": "stale"})) == [ref[L2]])

# sort and pages
p1 = rep("inventory", sort="price", desc=False, size=4, page=1); p3 = rep("inventory", sort="price", desc=False, size=4, page=3)
check("sorts by price, cheapest first", [x["price"] for x in p1["rows"]] == sorted(x["price"] for x in p1["rows"]) and p1["rows"][0]["ref"] == ref[L6])
check("pages: 9 rows in pages of 4, last page has 1", p1["total"] == 9 and len(p1["rows"]) == 4 and len(p3["rows"]) == 1 and p3["rows"][0]["ref"] == ref[L8])

# ---------- Listing funnel, reconciled ----------
fun = rep("funnel")
check("views in period = hand count of view rows (the day before the period is left out)", kpi(fun, "views")["value"] == hand(f"select count(*) from listing_views where day between '{P_FROM}' and '{P_TO}'") == 18)
check("saves in period = hand count", kpi(fun, "saves")["value"] == hand(f"select count(*) from saves where (created_at at time zone 'Africa/Kampala')::date between '{P_FROM}' and '{P_TO}'") == 1)
check("enquiries in period = hand count of offers", kpi(fun, "enquiries")["value"] == hand(f"select count(*) from deals where (created_at at time zone 'Africa/Kampala')::date between '{P_FROM}' and '{P_TO}'") == 2)
check("enquiry rate = enquiries per 100 views", float(kpi(fun, "enquiry_rate")["value"]) == round(2 * 100 / 18, 1))
day = T - dt.timedelta(days=2)  # the reconciliation day
tr = {x["day"]: x for x in fun["trend"]}
check(f"reconcile {day}: views that day", tr[day.isoformat()]["views"] == hand(f"select count(*) from listing_views where day = '{day}'") == 6, tr[day.isoformat()])
check(f"reconcile {day}: the 23:30 UTC offer is on the Kampala day {day}", tr[day.isoformat()]["enquiries"] == hand(f"select count(*) from deals where (created_at at time zone 'Africa/Kampala')::date = '{day}'") == 1)
check("trend has one point per day of the period", len(fun["trend"]) == 7)
check("trend totals equal the key numbers", sum(x["views"] for x in fun["trend"]) == kpi(fun, "views")["value"] and sum(x["enquiries"] for x in fun["trend"]) == kpi(fun, "enquiries")["value"])
rows = {x["ref"]: x for x in rep("funnel", size=50)["rows"]}
check("the funnel lists only cars that have been live (no draft, no pending)", ref[L5] not in rows and ref[L6] not in rows and len(rows) == 7, sorted(rows))
r1 = rows[ref[L1]]
check("per listing: L1 views 10, enquiries 1, rate 10.0", (r1["views"], r1["enquiries"], float(r1["enquiry_rate"])) == (10, 1, 10.0), r1)
check("days to first enquiry uses the first offer ever (L1: 5 days)", float(r1["days_to_first_enquiry"]) == 5.0, r1["days_to_first_enquiry"])
check("days to sold (L3: 8 days)", float(rows[ref[L3]]["days_to_close"]) == 8.0)
check("days to removed (L7: 26 days)", float(rows[ref[L7]]["days_to_close"]) == 26.0)
r2 = rows[ref[L2]]
med = hand(f"select percentile_cont(0.5) within group (order by price) from listings where make='Toyota' and model='Premio' and status in ('live','reserved','sold')")
check("price vs similar cars: L2 against the median of the Premio pool (32m)", float(r2["similar_median"]) == round(med) and float(r2["price_vs_similar"]) == round((45000000 / med - 1) * 100, 1), (r2["similar_median"], med))
check("the reason is visible: dear, 2 photos, short description", "above similar" in r2["reason"] and "2 photos" in r2["reason"] and "Short description" in r2["reason"], r2["reason"])
check("no reason shown when nothing stands out (L4)", rows[ref[L4]]["reason"] is None, rows[ref[L4]]["reason"])
check("Mazda: fewer than 3 similar cars, so no comparison", rows[ref[L8]]["similar_median"] is None and rows[ref[L8]]["price_vs_similar"] is None)
top = rep("funnel", sort="enquiry_rate", desc=True)["rows"]
check("top performers sort by enquiry rate, blanks last", float(top[0]["enquiry_rate"]) == max(float(x["enquiry_rate"]) for x in top if x["enquiry_rate"] is not None) and top[-1]["enquiry_rate"] is None)
check("drill: listings with enquiries in the period", refs(rep("funnel", {"flag": "has_enquiries"})) == sorted([ref[L1], ref[L4]]))
check("median days to sold over cars sold in the period (L3: 8)", float(kpi(fun, "median_days_to_sold")["value"]) == 8.0)

# compare with the previous period (same length, just before)
cmp = rep("funnel", compare=True)
check("previous period is the 7 days before", cmp["prev_to"] == (P_FROM - dt.timedelta(days=1)).isoformat() and cmp["prev_from"] == (P_FROM - dt.timedelta(days=7)).isoformat())
check("previous views = hand count", kpi(cmp, "views")["prev"] == hand(f"select count(*) from listing_views where day between '{P_FROM - dt.timedelta(days=7)}' and '{P_FROM - dt.timedelta(days=1)}'") == 13)
check("previous enquiries = hand count", kpi(cmp, "enquiries")["prev"] == hand(f"select count(*) from deals where (created_at at time zone 'Africa/Kampala')::date between '{P_FROM - dt.timedelta(days=7)}' and '{P_FROM - dt.timedelta(days=1)}'") == 1)
ci = rep("inventory", compare=True)
check("inventory: previous sold = L9", kpi(ci, "sold")["prev"] == 1 and "prev" not in kpi(ci, "live_now"))

# ---------- export ----------
before = hand("select count(*) from audit_log where action='report exported'")
ex = rep("inventory", {"make": "Toyota"}, export=True)
check("export returns every row with the filters applied", ex["total"] == len(ex["rows"]) == 5)
log = su("select actor_id, entity_id, detail from audit_log where action='report exported' order by id desc limit 1")[0]
check("who exported what and when is recorded", hand("select count(*) from audit_log where action='report exported'") == before + 1 and str(log[0]) == str(A) and log[1] == "inventory" and log[2]["filters"] == {"make": "Toyota"} and log[2]["rows"] == 5, log)
check("the glossary defines every column the reports show", all(c in su("select report_glossary()")[0][0] for c in rep("inventory")["columns"] + rep("funnel")["columns"] + [k["key"] for k in inv["kpis"] + fun["kpis"]]))
check("reports state the time zone", "East Africa Time" in inv["timezone"])
check("range guard: end before start is refused", "date range" in (err(A, "select admin_report('inventory', current_date, current_date - 1)") or ""))
print(f"\n{ok} passed, {bad} failed")
