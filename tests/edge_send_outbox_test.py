"""The send-outbox Edge Function (part 24) run in Deno against the local stack and a stand-in for Africa's Talking.
Usage: python3 tests/edge_send_outbox_test.py   (needs deno; fresh database after tests/stack/reset.sh; port 8000 free)
Checks: without keys nothing is sent and the run is recorded; with keys each SMS goes to the messaging endpoint with the
apiKey header, username, to, message and the sender name; success marks it sent with the message id and cost; a bad number
fails for good; a low balance stops the run and puts the rest back without using up their tries; codes go first and their
text leaves the outbox; idle runs don't pile up."""
import json, os, subprocess, sys, time, threading, base64, hmac, hashlib, urllib.request, urllib.parse, psycopg2
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
HERE = os.path.dirname(os.path.abspath(__file__)); FN = os.path.join(HERE, "..", "supabase", "functions", "send-outbox", "index.ts")
DENO = os.environ.get("DENO", "deno")
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:300])

# Stand-in for Africa's Talking: answers by number
SEEN = []
CODES = {"+256772000002": (403, "InvalidPhoneNumber"), "+256772000003": (405, "InsufficientBalance")}
class AT(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        SEEN.append({"path": self.path, "key": self.headers.get("apiKey"), "form": {k: v[0] for k, v in body.items()}})
        code, status = CODES.get(body["to"][0], (101, "Success"))
        out = json.dumps({"SMSMessageData": {"Message": "Sent to 1/1", "Recipients": [{"statusCode": code, "number": body["to"][0], "status": status, "cost": "UGX 30.0000", "messageId": "ATXid_%d" % len(SEEN)}]}}).encode()
        self.send_response(201); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
srv = ThreadingHTTPServer(("127.0.0.1", 54400), AT); threading.Thread(target=srv.serve_forever, daemon=True).start()

def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()); p = b64(json.dumps({"role": "service_role", "exp": int(time.time()) + 3600}).encode())
SERVICE = h + "." + p + "." + b64(hmac.new(b"saaz-local-test-secret-saaz-local-test-secret", (h + "." + p).encode(), hashlib.sha256).digest())

def run_fn(env_extra):
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:54321", SUPABASE_SERVICE_ROLE_KEY=SERVICE, SAAZ_SITE_URL="http://localhost:8777/saaz/",
               NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost", **env_extra)
    for k in ("AT_USERNAME", "AT_API_KEY", "AT_SENDER_ID", "AT_BASE_URL"):
        if k not in env_extra: env.pop(k, None)
    pr = subprocess.Popen([DENO, "run", "--allow-net", "--allow-env", "--allow-read", FN], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(80):
        try: urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/", method="OPTIONS"), timeout=1); break
        except Exception: time.sleep(0.25)
    try:
        r = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/", data=b"{}", method="POST", headers={"Content-Type": "application/json"}), timeout=60)
        return json.loads(r.read())
    finally:
        pr.terminate(); pr.wait()

def user(e, mobile):
    u = sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,'{\"name\":\"T\"}',now()) returning id", (e,))[0][0]
    sql("update profiles set mobile=%s, phone_verified=true where id=%s", (mobile, u)); return u
U1, U2, U3, U4 = user("e1@x.test", "+256772000001"), user("e2@x.test", "+256772000002"), user("e3@x.test", "+256772000003"), user("e4@x.test", "+256772000004")
sql("delete from outbox"); sql("delete from outbox_runs")
for u in (U1, U2): sql("select notify(%s,'offer_received','New offer on your car',null,'{app,sms}')", (u,))

# 1. No keys
r = run_fn({})
check("without keys: nothing sent, says so", r == {"configured": False} and not SEEN, r)
check("without keys: SMS still queued", sql("select count(*) from outbox where status='queued'")[0][0] == 2)
run_fn({})
check("idle runs don't pile up rows", sql("select count(*) from outbox_runs")[0][0] == 1)

# 2. Keys set
KEYS = {"AT_USERNAME": "saaztest", "AT_API_KEY": "test-key-not-real", "AT_SENDER_ID": "SAAZ", "AT_BASE_URL": "http://127.0.0.1:54400"}
sql("update profiles set phone_verified=false where id=%s", (U4,))
cur.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": str(U4), "role": "authenticated"}),))
sql("insert into auth.sessions (user_id) values (%s)", (U4,))
sid = sql("select id from auth.sessions where user_id=%s", (U4,))[0][0]
cur.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"sub": str(U4), "role": "authenticated", "session_id": str(sid)}),))
sql("select phone_send_code()"); cur.execute("select set_config('request.jwt.claims', '', false)")
r = run_fn(KEYS)
check("with keys: 3 sent (2 alerts, 1 code), 1 failed", r.get("claimed") == 3 and r.get("sent") == 2 and r.get("failed") == 1, r)
check("the code went first", SEEN and "your code is" in SEEN[0]["form"]["message"], SEEN[:1])
check("messaging endpoint, apiKey header", all(s["path"] == "/version1/messaging" and s["key"] == "test-key-not-real" for s in SEEN))
check("form has username, to, message and the sender name", all(set(s["form"]) == {"username", "to", "message", "from"} and s["form"]["from"] == "SAAZ" and s["form"]["username"] == "saaztest" for s in SEEN), SEEN[:1])
row = sql("select status, provider_id, cost from outbox where to_addr='+256772000001'")[0]
check("success: sent, with message id and cost", row[0] == "sent" and row[1].startswith("ATXid_") and row[2] == "UGX 30.0000", row)
check("bad number: failed for good, reason kept", sql("select status, reason from outbox where to_addr='+256772000002'")[0] == ("failed", "403 InvalidPhoneNumber"))
check("code text removed once sent", sql("select body from outbox where kind='phone_code'")[0][0] == "(code removed after sending)")

# 3. Low balance stops the run
for u in (U3, U1, U1): sql("select notify(%s,'offer_received','Another offer',null,'{app,sms}')", (u,))
SEEN.clear(); r = run_fn(KEYS)
check("low balance: run stops after the first refusal", len(SEEN) == 1 and "Stopped: 405" in (r.get("note") or ""), r)
rest = sql("select status, attempts from outbox where to_addr='+256772000001' and status <> 'sent'")
check("the rest go back to the queue without using a try", rest and all(x == ("queued", 0) for x in rest), rest)
check("the refused one waits to retry", sql("select status, attempts from outbox where to_addr='+256772000003'")[0] == ("queued", 1))
check("the run is recorded with the reason", "405" in (sql("select note from outbox_runs order by id desc limit 1")[0][0] or ""))
srv.shutdown()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
