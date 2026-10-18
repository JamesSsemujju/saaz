"""Tests for part 17: Inspections and garages, Deals and sales (with the learned agreement gap). Fresh database, session time zone UTC.
Every number is reconciled against a hand count worked out below from the rows inserted."""
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
S = user("s@x.test", "Sam Seller"); BUY = [user(f"b{i}@x.test", f"Buyer {i}") for i in range(8)]
T = su("select (now() at time zone 'Africa/Kampala')::date")[0][0]
def eat(d, hh=12): return f"{(T + dt.timedelta(days=d)).isoformat()} {hh:02d}:00:00+03"
n = 0
def listing(make, model, price, status="live"):
    global n; n += 1
    vid = su("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTDEALS%010d" % n, make, model))[0][0]
    return su("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
              description, photos, logbook_name_matches, owner_authorised, live_at, created_at, updated_at)
              values (%s,%s,'UG','Kampala',%s,%s,%s,2015,'Petrol','Automatic','Sedan','White','1.5',80000,%s,'UGX',%s,'x',%s,true,true,%s,%s,%s) returning id""",
              (vid, S, status, make, model, "UAD %03dD" % n, price, ["a.webp"] * 8, eat(-40), eat(-40), eat(-40)))[0][0]
P1 = listing("Toyota", "Premio", 40000000, "sold"); P2 = listing("Toyota", "Premio", 40000000); P3 = listing("Toyota", "Premio", 42000000); P4 = listing("Toyota", "Premio", 40000000)
F1 = listing("Subaru", "Forester", 60000000); H1 = listing("Honda", "Fit", 25000000)
su("insert into audit_log (at, actor_role, entity, entity_id, action, detail) values (%s,'seller','listing',%s,'price changed',%s)", (eat(-9), str(P3), json.dumps({"before": 40000000, "after": 42000000})))
def garage(name):
    return su("insert into garages (name, business_type, country, region, address, phone, registration_no, status) values (%s,'garage','UG','Kampala','x','1','r','applied') returning id", (name,))[0][0]
G1 = garage("Ntinda Motors"); G2 = garage("Kira Auto")
def review(lid, gid, scope, status, req, start=None, issued=None, verdict=None, score=None, cancelled=None, hh=12):
    vid = su("select vehicle_id from listings where id=%s", (lid,))[0][0]
    return su("""insert into reviews (listing_id, vehicle_id, garage_id, scope, status, requested_at, started_at, issued_at, verdict, score, cancelled_at, doc_no, created_at)
                 values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'SZR-T-' || substr(md5(random()::text),1,8),%s) returning id""",
              (lid, vid, gid, scope, status, eat(req), eat(start) if start is not None else None, eat(issued, hh) if issued is not None else None, verdict, score,
               eat(cancelled) if cancelled is not None else None, eat(req)))[0][0]
R1 = review(P1, G1, "general", "issued", -5, -4, -3, "pass", 90)
R2 = review(P2, G1, "general", "issued", -10, -9, -2, "conditional", 70)
R3 = review(P3, G2, "general", "issued", -3, -2, -1, "fail", 40, hh=0)       # issued at 00:00 Kampala: 1.5 days after a 12:00 request... see below
R4 = review(F1, G2, "general", "requested", -12)
R5 = review(H1, G1, "engine", "requested", -1)
R6 = review(P4, G2, "general", "cancelled", -20, cancelled=-2)
R7 = review(P4, G1, "general", "issued", -12, -11, -9, "pass", 85)
su("insert into review_opinions (review_id, stance, reason) values (%s,'object','Photos do not match the car')", (R2,))
def conv(lid, gid, status, opened, closed=None, first_msg_h=None):
    return su("insert into conversations (listing_id, garage_id, status, opened_at, closed_at, garage_first_message_at, round) values (%s,%s,%s,%s,%s,%s,1) returning id",
              (lid, gid, status, eat(opened), eat(closed) if closed is not None else None, f"{(T + dt.timedelta(days=opened)).isoformat()} {12 + first_msg_h:02d}:00:00+03" if first_msg_h is not None else None))[0][0]
C1 = conv(P1, G1, "agreed", -6, first_msg_h=3); C2 = conv(F1, G1, "timed_out", -5, -4); C3 = conv(F1, G2, "in_play", -4); C4 = conv(P3, G2, "passed", -8, -6)
def deal(lid, b, status, offer_day, first, agreed_day=None, agreed=None, completed_day=None, ended_day=None, end_kind=None):
    d = su("insert into deals (listing_id, buyer_id, amount, last_by, status, created_at, updated_at) values (%s,%s,%s,'buyer',%s,%s,%s) returning id",
           (lid, b, agreed or first, status, eat(offer_day), eat(offer_day)))[0][0]
    su("insert into deal_events (deal_id, by_side, kind, amount, created_at) values (%s,'buyer','offer',%s,%s)", (d, first, eat(offer_day)))
    if agreed_day is not None: su("insert into deal_events (deal_id, by_side, kind, amount, created_at) values (%s,'system','agreed',%s,%s)", (d, agreed, eat(agreed_day)))
    if completed_day is not None: su("insert into deal_events (deal_id, by_side, kind, created_at) values (%s,'admin','completed',%s)", (d, eat(completed_day)))
    if ended_day is not None: su("insert into deal_events (deal_id, by_side, kind, created_at) values (%s,'system',%s,%s)", (d, end_kind, eat(ended_day)))
    return d
D1 = deal(P1, BUY[0], "completed", -20, 34000000, -18, 36000000, completed_day=-16)    # gap 10%
D2 = deal(P2, BUY[1], "agreed", -15, 35000000, -14, 38000000)                          # gap 5%
D3 = deal(P3, BUY[2], "agreed", -11, 36000000, -10, 37200000)                          # asked 40m then (price rose to 42m later): gap 7%
D4 = deal(P4, BUY[3], "completed", -4, 35000000, -2, 37000000, completed_day=-1)       # gap 7.5%, in the period
D5 = deal(F1, BUY[4], "agreed", -3, 55000000, -1, 57000000)                            # gap 5%, in the period
D6 = deal(H1, BUY[5], "negotiating", -2, 20000000)
D7 = deal(H1, BUY[6], "auto_rejected", -5, 10000000, ended_day=-5, end_kind="auto_reject")
P_FROM, P_TO = T - dt.timedelta(days=6), T
def rep(report, filters=None, **kw):
    a = dict(r=report, f=P_FROM, t=P_TO, c=kw.get("compare", False), fl=json.dumps(filters or {}), g=kw.get("group"), s=kw.get("sort"), d=kw.get("desc", True), e=kw.get("export", False))
    return as_(kw.get("who", A), "select admin_report(%(r)s,%(f)s,%(t)s,%(c)s,%(fl)s::jsonb,%(g)s,%(s)s,%(d)s,1,50,%(e)s)", a)[0][0]
def kpi(r, k): return [x for x in r["kpis"] if x["key"] == k][0]
hand = lambda q: su(q)[0][0]
per = f"'{P_FROM}'::date and '{P_TO}'::date"
def in_per(col): return f"({col} at time zone 'Africa/Kampala')::date between {per}"

# ---------- access and routing ----------
check("signed-out visitors can't run the new reports", err(None, "select admin_report('deals', current_date, current_date)") is not None)
check("a seller can't run the new reports", err(S, "select admin_report('inspections', current_date, current_date)") is not None)
check("the engines behind the reports are closed to users", all(err(A, q) is not None for q in [
    "select * from rpt_inspection_facts(current_date, current_date)", "select * from rpt_deal_facts(current_date, current_date)",
    "select * from rpt_gap_norms(current_date)", "select rpt_listings_report('inventory', current_date, current_date)"]))
check("Inventory still answers through the same admin_report", rep("inventory")["kpis"][0]["key"] == "live_now")

# ---------- Inspections and garages ----------
ins = rep("inspections")
check("requested in period = hand count (3)", kpi(ins, "insp_requested")["value"] == hand(f"select count(*) from reviews where {in_per('coalesce(requested_at, created_at)')}") == 3)
check("issued in period = hand count (3)", kpi(ins, "insp_issued")["value"] == hand(f"select count(*) from reviews where {in_per('issued_at')}") == 3)
med = hand(f"select round((percentile_cont(0.5) within group (order by extract(epoch from issued_at - requested_at) / 86400))::numeric, 1) from reviews where {in_per('issued_at')}")
check("median days to inspect = hand median", float(kpi(ins, "median_days_to_inspect")["value"]) == float(med), (kpi(ins, "median_days_to_inspect"), med))
check("open now = requested or in progress (2)", kpi(ins, "insp_open")["value"] == hand("select count(*) from reviews where status in ('requested','draft')") == 2)
check("waiting over 7 days (1: the Subaru)", kpi(ins, "insp_waiting_7d")["value"] == 1)
check("offered to garages in period = hand count (3)", kpi(ins, "line_offers")["value"] == hand(f"select count(*) from conversations where {in_per('opened_at')}") == 3)
check("time-outs in period (1)", kpi(ins, "timeouts")["value"] == hand(f"select count(*) from conversations where status='timed_out' and {in_per('closed_at')}") == 1)
check("time-out rate = time-outs / turns ended in period (1 of 2)", float(kpi(ins, "timeout_rate")["value"]) == 50.0)
check("pass rate = 1 of 3 issued", float(kpi(ins, "pass_rate")["value"]) == 33.3)
check("trend: requested and issued per day add up", sum(x["requested"] for x in ins["trend"]) == 3 and sum(x["issued"] for x in ins["trend"]) == 3 and len(ins["trend"]) == 7)
g = {x["label"]: x for x in rep("inspections", group="garage")["groups"]}
n1, n2 = g["Ntinda Motors"], g["Kira Auto"]
check("by garage, Ntinda: issued 2, median 5.0 days, 1 open, 2 offers, 1 time-out, pass 1, conditional 1, objected 1, average 80",
      (n1["insp_issued"], float(n1["median_days_to_inspect"]), n1["insp_open"], n1["line_offers"], n1["timeouts"], n1["pass"], n1["conditional"], n1["objected"], float(n1["avg_score"]))
      == (2, 5.0, 1, 2, 1, 1, 1, 1, 80.0), n1)
check("by garage, Kira: issued 1, fail 1, 1 open, time-out rate 0", (n2["insp_issued"], n2["fail"], n2["insp_open"], float(n2["timeout_rate"])) == (1, 1, 1, 0.0), n2)
check("garage rows add up to the key numbers", sum(x["insp_issued"] for x in g.values()) == kpi(ins, "insp_issued")["value"] and sum(x["timeouts"] for x in g.values()) == kpi(ins, "timeouts")["value"])
dr = rep("inspections", {"garage": str(G1), "flag": "issued"})
check("a garage's count opens its inspections (Ntinda issued: 2)", dr["total"] == 2 and dr["rows_kind"] == "inspections" and {x["garage"] for x in dr["rows"]} == {"Ntinda Motors"})
to = rep("inspections", {"flag": "timeouts"})
check("time-outs open the garage line turns behind them", to["rows_kind"] == "garage_line" and to["total"] == 1 and to["rows"][0]["garage"] == "Ntinda Motors")
check("hours to first contact (Ntinda, 3.0)", float([x for x in rep("inspections", {"flag": "line_offers"})["rows"] if x["line_status"] == "agreed"][0]["hours_to_contact"]) == 3.0)
check("waiting list is actionable: the Subaru, over 11 days", [(x["car"], float(x["waiting_days"]) > 11) for x in rep("inspections", {"flag": "waiting_7d"})["rows"]] == [("2015 Subaru Forester", True)])
sc = {x["value"]: x for x in rep("inspections", group="scope")["groups"]}
check("by scope: engine 1 requested, general 2", sc["engine"]["insp_requested"] == 1 and sc["general"]["insp_requested"] == 2)
ci = rep("inspections", compare=True)
check("previous period: issued 1 (Toyota, 9 days ago)", kpi(ci, "insp_issued")["prev"] == hand(f"select count(*) from reviews where (issued_at at time zone 'Africa/Kampala')::date between '{P_FROM - dt.timedelta(days=7)}' and '{P_FROM - dt.timedelta(days=1)}'") == 1)

# ---------- Deals and sales, and what Saaz learns ----------
de = rep("deals")
check("offers in period = hand count (4)", kpi(de, "offers")["value"] == hand(f"select count(*) from deals where {in_per('created_at')}") == 4)
check("agreed in period = hand count of agreed events (2)", kpi(de, "agreed")["value"] == hand(f"select count(*) from deal_events where kind='agreed' and {in_per('created_at')}") == 2)
check("completed in period (1)", kpi(de, "completed")["value"] == 1)
check("offer to agreement: 2 of 4 offers made in the period", float(kpi(de, "agree_rate")["value"]) == 50.0)
check("median days to agree (2.0)", float(kpi(de, "median_days_to_agree")["value"]) == 2.0)
check("median gap over deals agreed in the period: 7.5 and 5 -> 6.3", float(kpi(de, "median_gap")["value"]) == 6.3, kpi(de, "median_gap"))
check("ended without a deal (1 auto-rejected)", kpi(de, "lost")["value"] == 1)
rows = {x["ref"]: x for x in rep("deals", {"flag": "agreed_ever"})["rows"]}
ref = lambda lid: su("select ref from listings where id=%s", (lid,))[0][0]
d3 = rows[ref(P3)]
check("asking at agreement comes from the price history (40m, not today's 42m)", d3["asking"] == 40000000 and float(d3["gap_pct"]) == 7.0, d3)
d4 = [x for x in rep("deals", {"flag": "agreed"})["rows"] if x["ref"] == ref(P4)][0]
check("learned: a Toyota Premio usually agrees 7.3% below asking (4 deals)", float(d4["typical_gap"]) == 7.3 and d4["based_on"] == "Toyota Premio, 4 deals", d4)
check("this deal against the usual: 7.5 - 7.3 = +0.2 points", float(d4["gap_vs_typical"]) == 0.2)
d5 = [x for x in rep("deals", {"flag": "agreed"})["rows"] if x["ref"] == ref(F1)][0]
check("too few Subarus: falls back to the price band (5 deals, 7.0)", d5["based_on"] == "40m to 70m, 5 deals" and float(d5["typical_gap"]) == 7.0, d5)
gm = {x["label"]: x for x in rep("deals", group="model")["groups"]}
check("by model: Toyota Premio 4 deals, median 7.3, quarters 6.5 to 8.1", (gm["Toyota Premio"]["group_n"], float(gm["Toyota Premio"]["median_gap"]), float(gm["Toyota Premio"]["gap_p25"]), float(gm["Toyota Premio"]["gap_p75"])) == (4, 7.3, 6.5, 8.1), gm["Toyota Premio"])
check("by make: Subaru has 1 deal (not enough to learn on its own)", {x["label"]: x["group_n"] for x in rep("deals", group="make")["groups"]}.get("Subaru") == 1)
ex = {x["ref"]: x for x in rep("deals", {"flag": "expected"})["rows"]}
h = ex[ref(H1)]
check("live cars: expected agreed price from the learned gap (Honda 25m, all cars 7.0% -> 23.3m)", h["expected_price"] == 23300000 and h["based_on"] == "All cars, 5 deals", h)
check("expected prices are for live cars only", ref(P1) not in ex and len(ex) == 5)
check("the learning moves with time: at the end of the previous period only 3 Premio deals were agreed",
      {x["label"]: x["group_n"] for x in as_(A, "select admin_report('deals', %s, %s, false, '{}', 'model')", (P_FROM - dt.timedelta(days=7), P_FROM - dt.timedelta(days=1)))[0][0]["groups"]}.get("Toyota Premio") == 3)
cd = rep("deals", compare=True)
check("previous period: 1 offer (the Premio at 11 days? no: 7 to 13 days ago: D3)", kpi(cd, "offers")["prev"] == hand(f"select count(*) from deals where (created_at at time zone 'Africa/Kampala')::date between '{P_FROM - dt.timedelta(days=7)}' and '{P_FROM - dt.timedelta(days=1)}'") == 1)
before = hand("select count(*) from audit_log where action='report exported'")
rep("deals", group="model", export=True)
check("exports of grouped tables are recorded", hand("select count(*) from audit_log where action='report exported'") == before + 1 and su("select detail->>'group' from audit_log where action='report exported' order by id desc limit 1")[0][0] == "model")
check("unknown sort is refused", "Unknown sort" in (err(A, "select admin_report('deals', current_date, current_date, false, '{}', null, 'gap_pct; select 1')") or ""))
gl = as_(A, "select admin_report_options()")[0][0]["glossary"]
check("every column and number on the new reports is defined", all(c in gl for c in ins["columns"] + de["columns"] + [k["key"] for k in ins["kpis"] + de["kpis"]] + to["columns"]
      + ["expected_price", "based_on", "group_n", "gap_p25", "gap_p75", "pass", "conditional", "fail", "avg_score", "objected"]))
print(f"\n{ok} passed, {bad} failed")
