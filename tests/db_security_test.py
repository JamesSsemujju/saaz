"""Security boundaries, tested against the database the way the browser and the API reach it.

Builds the marketplace world with db_marketplace_test.py when the database is empty (seller, buyers, two certified
garages, an inspector, a live car with an issued report, deals, messages), then adds outsiders who have no part in it:
Eve (a buyer), Olu (owner of a third certified garage, no jobs) and Pat (another seller).

1. Function sweep: every function a signed-in person (or a visitor) may call, called by each outsider with the ids of
   things that are not theirs. Passes when nothing changes in any table and no reply carries someone else's data.
2. Table reads: each outsider reads every table directly; only public rows come back.
3. Grants: visitors and signed-in people hold no write rights on any table (defence in depth under RLS).
4. Named cases: report visibility, inspections, admin functions, vehicle and odometer records, storage paths.
Run: python3 tests/db_security_test.py  (fresh database: run tests/stack reset first)"""
import json, os, subprocess, sys, psycopg2, admin_session
HERE = os.path.dirname(os.path.abspath(__file__))
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def as_(uid, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, uid),))
    cur.execute("set role " + ("authenticated" if uid else "anon"))
    try: cur.execute(q, a or None); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def err(uid, q, a=()):
    try: as_(uid, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def user(e, n, mobile):
    x = su("select id from auth.users where email=%s", (e,))
    if x: return x[0][0]
    return su("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG", "mobile": mobile})))[0][0]

if su("select count(*) from listings")[0][0] == 0:
    subprocess.run([sys.executable, os.path.join(HERE, "db_marketplace_test.py")], check=True, stdout=subprocess.DEVNULL)

E = user("eve@outside.test", "Eve Outsider", "+256711000001")
P = user("pat@outside.test", "Pat Seller", "+256711000002")
O = user("olu@outside.test", "Olu Owner", "+256711000003")
A = su("select user_id from admins limit 1")[0][0]
g3 = su("select garage_id from garage_members where user_id=%s", (O,))
g3 = g3[0][0] if g3 else as_(O, "select apply_garage(%s)", (json.dumps({"name": "Outside Motors", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "Plot 9",
         "phone": "+256700999999", "registration_no": "REG9", "years": 3, "specialties": ["Toyota"], "honest_declaration": True}),))[0][0]
as_(A, "select admin_decide_garage(%s,'approve')", (g3,)); as_(O, "select garage_sign_in()")
OUTSIDERS = {"visitor": None, "eve (buyer)": E, "pat (seller)": P, "olu (other garage owner)": O}

# What belongs to other people. Any of these in a reply to an outsider is a leak.
others = su("select id from auth.users where id <> all(%s::uuid[])", ([str(E), str(P), str(O)],))
SECRETS = set()
for (em, mob) in su("select email, mobile from profiles where id <> all(%s::uuid[])", ([str(E), str(P), str(O)],)):
    SECRETS.add(em)
    if mob and len(mob) > 8: SECRETS.add(mob)
SECRETS |= {b for (b,) in su("select body from messages") if b and len(b) > 12}
SECRETS |= {r for (r,) in su("select o.reason from review_opinions o where not public.is_public_review(o.review_id)") if r and len(r) > 12}
for (v, pl, an) in su("select v.vin, l.plate, l.admin_note from listings l join vehicles v on v.id = l.vehicle_id where l.status not in ('live','reserved','sold')"):
    SECRETS |= {x for x in (v, pl, an) if x and len(x) > 6}
SECRETS |= {n for (n,) in su("select r.notes from reviews r where not public.is_public_review(r.id)") if n and len(n) > 12}
SECRETS |= {v for (v,) in su("select v.vin from vehicles v where not exists (select 1 from listings l where l.vehicle_id = v.id and l.status in ('live','reserved','sold'))") if v}
SECRETS.discard(None)
# Facts printed on a public car or its public report are not secrets, even when an older private listing shares them (same VIN)
for (v, pl) in su("select v.vin, l.plate from listings l join vehicles v on v.id = l.vehicle_id where l.status in ('live','reserved','sold')"):
    SECRETS.discard(v); SECRETS.discard(pl)
def leaks(v):
    s = json.dumps(v, default=str)
    return [x for x in SECRETS if x and x in s]

IDS = {
    "listing": [r[0] for r in su("select id from listings")], "deal": [r[0] for r in su("select id from deals")],
    "conv": [r[0] for r in su("select id from conversations")], "review": [r[0] for r in su("select id from reviews")],
    "garage": [r[0] for r in su("select id from garages where id <> %s", (g3,))], "user": [r[0] for r in others],
    "member": [r[0] for r in su("select user_id from garage_members where garage_id <> %s", (g3,))] + [E, O],
    "invite": [r[0] for r in su("select id from garage_invites")], "message": [r[0] for r in su("select id from build.messages")] if su("select to_regclass('build.messages')")[0][0] else [],
    "task": [r[0] for r in su("select id from build.tasks")] if su("select to_regclass('build.tasks')")[0][0] else [],
}
TEXT = {"p_id": [r[0] for r in su("select doc_no from reviews where doc_no is not null")] or ["SZR-2026-000001"],
        "p_code": [r[0] for r in su("select verify_code from reviews where verify_code is not null")] or ["X"]}
def kind(name):
    for k, ks in (("listing", "listing"), ("deal", "deal"), ("conv", "conv"), ("review", "review"), ("garage", "garage"), ("user", "user"),
                  ("member", "member"), ("invite", "invite"), ("message", "message"), ("task", "task"), ("target", "listing")):
        if ks in name: return k
    return None
SAMPLE = {"text": "Security test value long enough", "jsonb": "{}", "boolean": "true", "integer": "1", "bigint": "100000000", "date": "2026-10-30",
          "numeric": "1", "text[]": "{engine}", "uuid[]": None}

def snapshot():
    tabs = [r[0] for r in su("select format('%I.%I', table_schema, table_name) from information_schema.tables where table_schema in ('public','build','auth','storage') and table_type='BASE TABLE'")]
    out = {}
    for t in tabs:
        if t in ("public.audit_log", "auth.sessions", "auth.mfa_factors", "public.listing_views"): continue   # written by sign-in helpers and failed-attempt logs
        out[t] = su("select md5(coalesce(string_agg(t::text, '|' order by t::text), '')) from %s t" % t)[0][0]
    return out

funcs = su("""select p.proname, coalesce(array_agg(a.name order by a.ord) filter (where a.name is not null), '{}'), coalesce(array_agg(format_type(a.typ, null) order by a.ord) filter (where a.name is not null), '{}'),
                     has_function_privilege('anon', p.oid, 'execute'), p.prorettype = 'trigger'::regtype
              from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              left join lateral unnest(p.proargnames, p.proargtypes::oid[]) with ordinality a(name, typ, ord) on true
              where n.nspname = 'public' and has_function_privilege('authenticated', p.oid, 'execute') and p.prokind = 'f'
              group by p.oid, p.proname order by p.proname""")

before = snapshot(); calls = 0; leaked = []; changed_by = []
for who, uid in OUTSIDERS.items():
    for (fn, names, types, anon_ok, is_trigger) in funcs:
        if is_trigger or (uid is None and not anon_ok): continue
        if any(t not in SAMPLE and t != "uuid" and t not in ("listings", "deals", "reviews") for t in types): continue
        if any(t in ("listings", "deals", "reviews") for t in types): continue   # row-typed helpers: checked by name below
        variants = [[]]
        for nm, ty in zip(names, types):
            k = kind(nm) if ty == "uuid" else None
            if ty == "uuid": vals = (IDS.get(k) or IDS["listing"])[:6] or [None]
            elif nm in TEXT and ty == "text": vals = TEXT[nm][:2]
            elif nm == "p_email": vals = ["eve@outside.test", su("select email from profiles where id=%s", (others[0][0],))[0][0]]
            elif nm in ("p_action", "p_decision", "p_stance", "p_kind", "p_field", "p_role", "p_report", "p_status", "p_to"): vals = {"p_action": ["accept", "decline", "withdraw", "complete", "counter"],
                 "p_decision": ["approve", "reject"], "p_stance": ["support", "object"], "p_kind": ["price", "remove"], "p_field": ["banned", "phone_verified"], "p_role": ["owner", "full"],
                 "p_report": ["inventory", "deals"], "p_status": ["awaiting_review", "live"], "p_to": ["done"]}[nm]
            else: vals = [SAMPLE.get(ty)]
            variants = [v + [x] for v in variants for x in vals][:12]
        for v in variants:
            calls += 1
            q = "select %s(%s)" % (fn, ", ".join("%s := %%s::%s" % (nm, ty) for nm, ty in zip(names, types)))
            try:
                r = as_(uid, q, tuple(None if x is None else str(x) for x in v))
                lk = leaks(r)
                if lk: leaked.append((who, fn, lk[:2]))
            except psycopg2.Error:
                pass
            now = snapshot()
            if now != before:
                diff = [t for t in now if now[t] != before.get(t)]
                own = (fn == "toggle_save" and diff == ["public.saves"] and su("select bool_and(l.status in ('live','reserved','sold')) from saves s join listings l on l.id = s.listing_id where s.user_id = %s", (uid,))[0][0] is not False) \
                   or (fn == "add_garage_member" and uid == O and su("select count(*) from garage_members where garage_id <> %s and invited_by = %s", (g3, O))[0][0] == 0 if su("select count(*) from information_schema.columns where table_name='garage_members' and column_name='invited_by'")[0][0] else fn == "add_garage_member" and uid == O)
                if not own: changed_by.append((who, fn, diff))
                before = now
print("function calls made:", calls)
check("outsiders' calls change nothing in any table", not changed_by, changed_by[:8])
check("outsiders' calls return nobody else's data", not leaked, leaked[:8])

# 2. Table reads
PUBLIC_TABLES_OK = {"inspection_scopes", "regions", "settings"}
for who, uid in OUTSIDERS.items():
    rows_leak = []
    for (t,) in su("select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'"):
        try: r = as_(uid, "select coalesce(json_agg(x), '[]') from public.%s x" % t)[0][0]
        except psycopg2.Error: continue
        lk = leaks(r)
        if lk: rows_leak.append((t, lk[:1]))
    check(f"{who}: direct table reads show nobody else's data", not rows_leak, rows_leak)
for who, uid in OUTSIDERS.items():
    n = as_(uid, "select count(*) from listings where status not in ('live','reserved','sold') and seller_id is distinct from auth.uid()")[0][0]
    check(f"{who}: no private listings visible", n == 0, n)
    n = as_(uid, "select count(*) from reviews r where not public.is_public_review(r.id)")[0][0] if uid else as_(uid, "select count(*) from reviews where status <> 'issued'")[0][0]
    check(f"{who}: no unpublished inspection reports visible", n == 0, n)
    check(f"{who}: no vehicle register rows (VINs of every car)", as_(uid, "select count(*) from vehicles")[0][0] == 0)
    check(f"{who}: no odometer history rows", as_(uid, "select count(*) from odometer_readings")[0][0] == 0)
    check(f"{who}: no deals, messages or conversations", as_(uid, "select (select count(*) from deals) + (select count(*) from messages) + (select count(*) from conversations)")[0][0] == 0)
    check(f"{who}: no other people's notifications or profiles", as_(uid, "select (select count(*) from notifications where user_id is distinct from auth.uid()) + (select count(*) from profiles where id is distinct from auth.uid())")[0][0] == 0)
    check(f"{who}: no activity log", as_(uid, "select count(*) from audit_log")[0][0] == 0)
    check(f"{who}: Build Assistant schema unreachable", err(uid, "select count(*) from build.tasks") is not None)

# 3. Grants: defence in depth under RLS
g = su("""select r.rolname, c.relname, string_agg(p.privilege_type, ',') from pg_class c join pg_namespace n on n.oid=c.relnamespace
          cross join (values ('anon'),('authenticated')) r(rolname)
          cross join lateral (select unnest(array['INSERT','UPDATE','DELETE','TRUNCATE']) privilege_type) p
          where n.nspname='public' and c.relkind in ('r','p') and has_table_privilege(r.rolname, c.oid, p.privilege_type)
          group by 1,2 order by 1,2""")
check("visitors and signed-in people hold no write rights on any table", not g, g[:6])
for who, uid in OUTSIDERS.items():
    check(f"{who}: direct insert into listings refused", err(uid, "insert into listings (seller_id) values (auth.uid())") is not None)
    check(f"{who}: direct update of any listing changes nothing", (lambda e: e is not None or su("select count(*) from listings where price = 1")[0][0] == 0)(err(uid, "update listings set price = 1")))

# 4. Named cases
pub = su("select id from reviews r where public.is_public_review(r.id) limit 1")
priv = su("select id from reviews r where not public.is_public_review(r.id) limit 1")
if priv:
    for who, uid in OUTSIDERS.items():
        r = None
        try: r = as_(uid, "select public.opinions_of(%s)", (priv[0][0],))
        except psycopg2.Error: pass
        check(f"{who}: Saaz's comments on an unpublished report not readable", not r or r[0][0] in (None, []), r)
for who, uid in OUTSIDERS.items():
    r = None
    try: r = as_(uid, "select public.tick()")
    except psycopg2.Error as e: r = "refused"
    if uid is None: check("visitor can't run the scheduler step (tick)", r == "refused", r)
    L = su("select id from listings where status not in ('live','reserved','sold') limit 1")
    if L:
        try: r = as_(uid, "select public.listing_stats(%s)", (L[0][0],))[0][0]
        except psycopg2.Error: r = None
        check(f"{who}: no figures for a private listing", r is None, r)
    check(f"{who}: can't pin an authenticator for staff", err(uid, "select admin_pin_staff_authenticator(%s)", (uid or E,)) is not None)
    check(f"{who}: can't change settings", err(uid, "select admin_set_setting('min_offer_pct','1'::jsonb)") is not None)
    check(f"{who}: can't open an inspection by ID", (lambda d: d is not None)(err(uid, "select open_inspection(%s)", (TEXT['p_id'][0],))) or as_(uid, "select open_inspection(%s)", (TEXT['p_id'][0],))[0][0] in (None, {}) )
    jobs = None
    try: jobs = as_(uid, "select garage_jobs()")
    except psycopg2.Error: pass
    check(f"{who}: no other garage's jobs", not jobs or not leaks(jobs) and "Harrier" not in json.dumps(jobs, default=str), jobs)

# The pattern, not just today's instances: a visitor may call only these functions. A new function that visitors can
# call fails this test until it is either locked down (revoke execute ... from public, anon) or added here on purpose.
VISITOR_OK = {"browse_listings", "whats_selling", "listing_stats", "record_view", "review_document", "verify_review", "lookup_inspection",
              "my_roles", "model_sales_public",
              # used inside row security policies, so the visitor's role must be able to run them; each answers only about the caller
              "is_admin", "is_full_admin", "my_garage_id", "my_garage_role", "my_team_garage", "garage_sees", "garage_sees_listing_work",
              "garage_on_listing", "is_seller_of", "is_listing_seller", "deal_side", "can_see_deal", "can_read_messages", "i_own_team",
              "is_public_review", "owner_booked"}
definers = {r[0] for r in su("select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.prosecdef")}
extra = sorted({fn for (fn, _, _, anon_ok, trg) in funcs if anon_ok and not trg and fn in definers} - VISITOR_OK)  # definer functions bypass row security
check("visitors can call only the agreed functions", not extra, extra)
# Every function in public is SECURITY DEFINER only with a fixed search_path
loose = su("select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname in ('public','build') and p.prokind = 'f' and p.proconfig is null and p.prolang <> 13 and p.proname not like 'pgp%%' and p.proname not in ('rpt_age_band','rpt_price_band','rpt_status_group')")  # left inlinable on purpose (part 21 note)
check("every function has a fixed search_path", not loose, loose)

# Storage: uploads only into your own folder
up = lambda uid, path: err(uid, "insert into storage.objects (bucket_id, name, owner) values ('car-photos', %s, auth.uid())", (path,))
if su("select to_regclass('storage.objects')")[0][0]:
    S_ = su("select seller_id from listings limit 1")[0][0]
    check("seller can't upload into another person's folder", up(P, f"{S_}/evil.webp") is not None)
    check("visitor can't upload", up(None, f"{S_}/evil.webp") is not None)

print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
