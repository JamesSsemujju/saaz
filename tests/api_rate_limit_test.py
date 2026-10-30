"""Part 22 request limits, over HTTP to PostgREST (port 54330) as browsers and scripts reach it.
Run on a fresh database with part 22 (tests/stack reset): python3 tests/api_rate_limit_test.py"""
import json, os, sys, urllib.request, psycopg2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "stack")); from fakesb_jwt import jwt
c = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); c.autocommit = True; k = c.cursor()
ok = bad = 0
def check(n, cond, x=""):
    global ok, bad
    if cond: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def req(method, path, body=None, auth=None, ip=None):
    h = {"Content-Type": "application/json"}
    if auth: h["Authorization"] = "Bearer " + auth
    if ip: h["X-Forwarded-For"] = ip
    r = urllib.request.Request("http://localhost:54330" + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    try: x = urllib.request.urlopen(r); return x.status, x.read(), dict(x.headers)
    except urllib.error.HTTPError as e: return e.code, e.read(), dict(e.headers)
def user(email):
    k.execute("insert into auth.users (email, raw_user_meta_data) values (%s, '{\"name\":\"T\",\"country\":\"UG\"}') returning id", (email,)); u = k.fetchone()[0]
    k.execute("insert into auth.sessions (user_id, aal) values (%s,'aal1') returning id", (u,)); return u, jwt(u, email, k.fetchone()[0])
k.execute("delete from request_hits")

# Visitors: inspection-number look-ups, 60 per 10 minutes per network address
codes = [req("POST", "/rpc/lookup_inspection", {"p_id": "SZR-2026-%06d" % i}, ip="203.0.113.7")[0] for i in range(61)]
check("visitor: 60 inspection look-ups answered", codes[:60] == [200] * 60, codes[:60])
s, body, hd = req("POST", "/rpc/lookup_inspection", {"p_id": "SZR-2026-000999"}, ip="203.0.113.7")
check("visitor: the 61st and later are refused with 429", codes[60] == 429 and s == 429, (codes[60], s))
check("the refusal says what to do", b"Too many requests" in body and hd.get("Retry-After") == "120", (body, hd.get("Retry-After")))
check("another visitor (other address) is not affected", req("POST", "/rpc/lookup_inspection", {"p_id": "x"}, ip="198.51.100.9")[0] == 200)
check("reads are not counted: browsing still works for the limited visitor", req("GET", "/settings?select=key", ip="203.0.113.7")[0] == 200)

# Signed-in: messages limit 40 per 10 minutes, counted per account whatever the address
u, t = user("ratelimit@x.test")
codes = [req("POST", "/rpc/update_profile", {"p_name": "Rate Tester", "p_country": "UG", "p_mobile": ""}, t, ip="192.0.2.%d" % i)[0] for i in range(31)]
check("account: 30 profile saves answered from changing addresses", all(x in (200, 204) for x in codes[:30]), codes[:30])
check("account: the 31st refused even from a new address", codes[30] == 429, codes[30])
u2, t2 = user("ratelimit2@x.test")
check("another account is not affected", req("POST", "/rpc/update_profile", {"p_name": "Other", "p_country": "UG", "p_mobile": ""}, t2)[0] in (200, 204))
# Read-only functions still work (they run read-only, so they aren't counted, and must not break)
check("read-only calls still answered (browse, my roles)", req("POST", "/rpc/browse_listings", {"p_country": "UG"})[0] == 200 and req("POST", "/rpc/my_roles", {}, t2)[0] == 200)

# Anything not listed falls under the general limit; the counter tables are private
k.execute("select max_hits from request_limits where path='*'"); check("a general limit exists for every other write", k.fetchone()[0] == 600)
check("visitors can't read the limits or the hits", req("GET", "/request_hits")[0] in (401, 403) and req("GET", "/request_limits")[0] in (401, 403))
check("visitors can't clear their own hits", req("DELETE", "/request_hits?who=not.is.null")[0] in (401, 403))
k.execute("select count(*) from request_hits where who like 'ip:%%'"); check("visitors are counted by address", k.fetchone()[0] >= 61)
print(f"\n{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
