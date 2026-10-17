"""Local stand-in for Supabase: auth (sign-up, sign-in, sessions) and storage, plus a proxy to PostgREST for /rest/v1."""
import base64, hashlib, hmac, json, os, time, uuid, urllib.request, urllib.error, psycopg2
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
SECRET = b"saaz-local-test-secret-saaz-local-test-secret"
PG = dict(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb")
STORE = os.path.join(os.path.dirname(__file__), "storage"); os.makedirs(STORE, exist_ok=True)
PW = {}
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def jwt(uid, email):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": str(uid), "email": email, "role": "authenticated", "aud": "authenticated", "exp": int(time.time()) + 3600}).encode())
    return h + "." + p + "." + b64(hmac.new(SECRET, (h + "." + p).encode(), hashlib.sha256).digest())
def anon(): 
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()); p = b64(json.dumps({"role": "anon"}).encode())
    return h + "." + p + "." + b64(hmac.new(SECRET, (h + "." + p).encode(), hashlib.sha256).digest())
def db(sql, args=()):
    c = psycopg2.connect(**PG); c.autocommit = True; cur = c.cursor(); cur.execute(sql, args)
    r = cur.fetchall() if cur.description else None; c.close(); return r
def session(uid, email, meta):
    return {"access_token": jwt(uid, email), "token_type": "bearer", "expires_in": 3600, "expires_at": int(time.time()) + 3600,
            "refresh_token": "r-" + str(uid), "user": {"id": str(uid), "email": email, "aud": "authenticated", "role": "authenticated",
            "user_metadata": meta or {}, "app_metadata": {}, "created_at": "2026-10-17T00:00:00Z"}}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS"); self.send_header("Access-Control-Expose-Headers", "*")
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.cors(); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_OPTIONS(self): self.send_response(204); self.cors(); self.end_headers()
    def body(self):
        n = int(self.headers.get("Content-Length") or 0); return self.rfile.read(n) if n else b""
    def uid(self):
        a = self.headers.get("Authorization", "")
        try: return json.loads(base64.urlsafe_b64decode(a.split(".")[1] + "==")).get("sub")
        except Exception: return None
    def handle_any(self, method):
        p = self.path
        if p.startswith("/auth/v1/"):
            return self.auth(method, p)
        if p.startswith("/storage/v1/"):
            return self.storage(method, p)
        if p.startswith("/rest/v1/"):
            return self.rest(method, p)
        self.send(404, {"message": "not found"})
    def auth(self, method, p):
        data = json.loads(self.body() or b"{}") if method in ("POST", "PUT") else {}
        if p.startswith("/auth/v1/signup"):
            email = data["email"].lower()
            if db("select 1 from auth.users where email=%s", (email,)): return self.send(422, {"code": 422, "error_code": "user_already_exists", "msg": "User already registered"})
            meta = data.get("data") or {}
            uid = db("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (email, json.dumps(meta)))[0][0]
            PW[email] = data["password"]; return self.send(200, session(uid, email, meta))
        if p.startswith("/auth/v1/token"):
            if "refresh_token" in p:
                uid = data.get("refresh_token", "")[2:]; r = db("select email, raw_user_meta_data from auth.users where id=%s", (uid,))
                return self.send(200, session(uid, r[0][0], r[0][1]))
            email = data.get("email", "").lower(); r = db("select id, raw_user_meta_data from auth.users where email=%s", (email,))
            if not r or PW.get(email, "demo1234") != data.get("password"):
                return self.send(400, {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"})
            return self.send(200, session(r[0][0], email, r[0][1]))
        if p.startswith("/auth/v1/user"):
            uid = self.uid(); r = db("select email, raw_user_meta_data from auth.users where id=%s", (uid,))
            if method == "PUT" and data.get("password"): PW[r[0][0]] = data["password"]
            return self.send(200, session(uid, r[0][0], r[0][1])["user"])
        if p.startswith("/auth/v1/logout") or p.startswith("/auth/v1/recover"): return self.send(204, b"")
        self.send(404, {"msg": "not found"})
    def storage(self, method, p):
        if p.startswith("/storage/v1/object/public/"):
            f = os.path.join(STORE, p[len("/storage/v1/object/public/"):].split("?")[0])
            if not os.path.exists(f): return self.send(404, {"message": "not found"})
            return self.send(200, open(f, "rb").read(), "image/webp")
        if p.startswith("/storage/v1/object/") and method in ("POST", "PUT"):
            key = p[len("/storage/v1/object/"):].split("?")[0]
            if not self.uid() or key.split("/")[1] != self.uid(): return self.send(403, {"message": "new row violates row-level security policy"})
            data = self.body(); ct = self.headers.get("Content-Type", "")
            if ct.startswith("multipart/form-data"):  # supabase-js sends Blobs as multipart, like real Supabase accepts
                import email.parser, email.policy
                msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(b"Content-Type: " + ct.encode() + b"\r\n\r\n" + data)
                data = [part.get_payload(decode=True) for part in msg.iter_parts() if part.get_filename() is not None or part.get_content_type() != "text/plain"][-1]
            f = os.path.join(STORE, key); os.makedirs(os.path.dirname(f), exist_ok=True); open(f, "wb").write(data)
            return self.send(200, {"Key": key, "Id": str(uuid.uuid4())})
        self.send(404, {"message": "not found"})
    def rest(self, method, p):
        auth = self.headers.get("Authorization", "")
        if not auth or auth == "Bearer " + "LOCALANON": auth = "Bearer " + anon()
        hdrs = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer", "accept", "range", "accept-profile", "content-profile")}
        hdrs["Authorization"] = auth
        req = urllib.request.Request("http://127.0.0.1:54330" + p[len("/rest/v1"):], data=self.body() if method != "GET" else None, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req) as r: code, data, ct = r.status, r.read(), r.headers.get("Content-Type", "application/json"); extra = r.headers.get("Content-Range")
        except urllib.error.HTTPError as e: code, data, ct, extra = e.code, e.read(), e.headers.get("Content-Type", "application/json"), None
        self.send_response(code); self.cors(); self.send_header("Content-Type", ct)
        if extra: self.send_header("Content-Range", extra)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
    def do_PUT(self): self.handle_any("PUT")
    def do_PATCH(self): self.handle_any("PATCH")
    def do_DELETE(self): self.handle_any("DELETE")
ThreadingHTTPServer(("127.0.0.1", 54321), H).serve_forever()
