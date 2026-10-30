"""The API boundary as an attacker reaches it: plain HTTP to PostgREST (port 54330) with no token or a real signed token.
Run on a database with part 21 and the marketplace world (python3 tests/db_marketplace_test.py first)."""
import json, os, sys, urllib.request, psycopg2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "stack")); from fakesb_jwt import jwt
c = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); c.autocommit = True; k = c.cursor()
ok = bad = 0
def check(n, cond, x=""):
    global ok, bad
    if cond: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def token(email):
    k.execute("select id from auth.users where email=%s", (email,)); u = k.fetchone()[0]
    k.execute("insert into auth.sessions (user_id, aal) values (%s,'aal1') returning id", (u,)); return jwt(u, email, k.fetchone()[0])
def req(method, path, body=None, auth=None, schema=None):
    h = {"Content-Type": "application/json", "Prefer": "return=representation"}
    if auth: h["Authorization"] = "Bearer " + auth
    if schema: h["Accept-Profile"] = h["Content-Profile"] = schema
    r = urllib.request.Request("http://localhost:54330" + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    try: x = urllib.request.urlopen(r); return x.status, json.loads(x.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, e.read()[:200]
B = token("buyer@x.test"); S = token("seller@x.test")
k.execute("select price from listings order by ref"); before = k.fetchall()
for who, t in (("visitor", None), ("buyer", B), ("seller", S)):
    for tab in ("listings", "deals", "messages", "reviews", "profiles", "notifications", "audit_log", "admins", "settings", "garages", "vehicles"):
        s, _ = req("POST", "/" + tab, {}, t); check(f"{who}: POST /{tab} refused", s in (401, 403), s)
        s, _ = req("PATCH", f"/{tab}?id=not.is.null", {"updated_at": "2000-01-01"} if tab != "settings" else {"value": 1}, t); check(f"{who}: PATCH /{tab} refused", s in (400, 401, 403), s)
        s, _ = req("DELETE", f"/{tab}?id=not.is.null", None, t); check(f"{who}: DELETE /{tab} refused", s in (400, 401, 403), s)
k.execute("select price from listings order by ref"); check("no listing changed", k.fetchall() == before)
s, r = req("GET", "/vehicles", None, B); check("buyer reads no vehicle register", s == 200 and r == [], r)
s, r = req("GET", "/odometer_readings"); check("visitor reads no odometer history", s == 200 and r == [], r)
s, r = req("GET", "/profiles", None, B); check("buyer sees only their own profile", s == 200 and [p["email"] for p in r] == ["buyer@x.test"], r)
s, r = req("GET", "/deals?select=id,buyer_id", None, B); k.execute("select id from auth.users where email='buyer@x.test'"); me = str(k.fetchone()[0])
check("buyer sees only their own deals", s == 200 and all(d["buyer_id"] == me for d in r), r)
s, r = req("GET", "/messages", None, B); check("buyer reads no garage-seller messages", s == 200 and r == [], r)
s, _ = req("GET", "/tasks", None, B, "build"); check("Build Assistant schema not served", s in (400, 406), s)
s, _ = req("POST", "/rpc/opinions_of", {"p_review": "00000000-0000-0000-0000-000000000000"}, B); check("internal helper not callable over the API", s in (401, 403, 404), s)
s, r = req("POST", "/rpc/admin_set_setting", {"p_key": "min_offer_pct", "p_value": 1}, B); check("admin function refused to a buyer", s >= 400 and b"Admins only" in r, r)
forged = B.split(".")[0] + "." + B.split(".")[1] + ".forged"; s, _ = req("GET", "/profiles", None, forged); check("token with a forged signature refused", s == 401, s)
print(f"\n{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
