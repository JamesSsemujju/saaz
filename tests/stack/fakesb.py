"""Local stand-in for Supabase: auth (sign-up, sign-in, sessions) and storage, plus a proxy to PostgREST for /rest/v1."""
import base64, hashlib, hmac, json, os, time, uuid, urllib.request, urllib.error, psycopg2
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
SECRET = b"saaz-local-test-secret-saaz-local-test-secret"
PG = dict(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb")
STORE = os.path.join(os.path.dirname(__file__), "storage"); os.makedirs(STORE, exist_ok=True)
PW = {}
SESS = {}  # refresh token -> (uid, session id)
import struct, secrets as _secrets
def totp(secret, t=None):
    """RFC 6238 code, the same maths an authenticator app uses (6 digits, 30 seconds)."""
    k = base64.b32decode(secret + "=" * (-len(secret) % 8)); c = int((t or time.time()) // 30)
    h = hmac.new(k, struct.pack(">Q", c), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def jwt(uid, email, sid=None, aal="aal1", amr=None):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": str(uid), "email": email, "role": "authenticated", "aud": "authenticated", "exp": int(time.time()) + 3600,
                        "session_id": str(sid) if sid else None, "aal": aal, "amr": amr or [{"method": "password", "timestamp": int(time.time())}]}).encode())
    return h + "." + p + "." + b64(hmac.new(SECRET, (h + "." + p).encode(), hashlib.sha256).digest())
def anon(): 
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()); p = b64(json.dumps({"role": "anon"}).encode())
    return h + "." + p + "." + b64(hmac.new(SECRET, (h + "." + p).encode(), hashlib.sha256).digest())
def db(sql, args=()):
    c = psycopg2.connect(**PG); c.autocommit = True; cur = c.cursor(); cur.execute(sql, args)
    r = cur.fetchall() if cur.description else None; c.close(); return r
def factors(uid):
    return [{"id": str(r[0]), "factor_type": "totp", "status": r[1], "friendly_name": r[2], "created_at": r[3].isoformat(), "updated_at": r[3].isoformat()}
            for r in db("select id, status::text, friendly_name, created_at from auth.mfa_factors where user_id=%s order by created_at", (uid,))]
def session(uid, email, meta, sid=None):
    """A session row like Supabase keeps in auth.sessions; the token carries its id, level (aal) and methods (amr)."""
    if sid is None:
        sid = db("insert into auth.sessions (user_id, aal, ip, user_agent) values (%s,'aal1','127.0.0.1','test browser') returning id", (uid,))[0][0]
        db("insert into auth.mfa_amr_claims (session_id, authentication_method) values (%s,'password')", (sid,))
    aal, fid = db("select aal::text, factor_id from auth.sessions where id=%s", (sid,))[0]
    amr = [{"method": m, "timestamp": int(ts.timestamp())} for m, ts in db("select authentication_method, created_at from auth.mfa_amr_claims where session_id=%s order by created_at desc", (sid,))]
    rt = "r-" + str(sid); SESS[rt] = (str(uid), str(sid))
    return {"access_token": jwt(uid, email, sid, aal, amr), "token_type": "bearer", "expires_in": 3600, "expires_at": int(time.time()) + 3600,
            "refresh_token": rt, "user": {"id": str(uid), "email": email, "aud": "authenticated", "role": "authenticated",
            "user_metadata": meta or {}, "app_metadata": {}, "created_at": "2026-10-17T00:00:00Z", "factors": factors(uid)}}
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
    def claims(self):
        a = self.headers.get("Authorization", "")
        try: return json.loads(base64.urlsafe_b64decode(a.split(".")[1] + "=="))
        except Exception: return {}
    def uid(self): return self.claims().get("sub")
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
                uid, sid = SESS.get(data.get("refresh_token", ""), (None, None))
                if not uid:  # a session made outside this server (tests), still alive in auth.sessions
                    row = db("select user_id, id from auth.sessions where id::text=%s", (data.get("refresh_token", "")[2:],)) if len(data.get("refresh_token", "")) == 38 else None
                    if row: uid, sid = str(row[0][0]), str(row[0][1])
                if not uid or not db("select 1 from auth.sessions where id=%s", (sid,)):  # session ended (signed out, revoked)
                    SESS.pop(data.get("refresh_token", ""), None)
                    return self.send(400, {"code": 400, "error_code": "refresh_token_not_found", "msg": "Invalid Refresh Token: Refresh Token Not Found"})
                r = db("select email, raw_user_meta_data from auth.users where id=%s", (uid,))
                return self.send(200, session(uid, r[0][0], r[0][1], sid))
            email = data.get("email", "").lower(); r = db("select id, raw_user_meta_data from auth.users where email=%s", (email,))
            if not r or PW.get(email, "demo1234") != data.get("password"):
                return self.send(400, {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"})
            return self.send(200, session(r[0][0], email, r[0][1]))
        if p.startswith("/auth/v1/user"):
            uid = self.uid(); r = db("select email, raw_user_meta_data from auth.users where id=%s", (uid,))
            if method == "PUT" and data.get("password"): PW[r[0][0]] = data["password"]
            return self.send(200, session(uid, r[0][0], r[0][1], self.claims().get("session_id"))["user"])
        if p.startswith("/auth/v1/factors"):
            return self.mfa(method, p, data)
        if p.startswith("/auth/v1/logout"):
            # Like Supabase: scope=global ends every session of this user, local only this one
            c = self.claims()
            if c.get("sub"):
                if "scope=local" in p: db("delete from auth.sessions where id=%s", (c.get("session_id"),))
                else: db("delete from auth.sessions where user_id=%s", (c["sub"],))
                for k in [k for k, v in SESS.items() if v[0] == c["sub"]]: SESS.pop(k, None)
            return self.send(204, b"")
        if p.startswith("/auth/v1/recover"): return self.send(204, b"")
        self.send(404, {"msg": "not found"})
    def mfa(self, method, p, data):
        c = self.claims(); uid, sid = c.get("sub"), c.get("session_id")
        if not uid or not sid: return self.send(401, {"msg": "Sign in first"})
        parts = p.split("?")[0].split("/")[3:]  # ['factors', id?, action?]
        if len(parts) == 1 and method == "POST":  # enroll
            if db("select 1 from auth.mfa_factors where user_id=%s and status='verified'", (uid,)) and c.get("aal") != "aal2":
                return self.send(422, {"msg": "AAL2 required to enroll a new factor"})
            secret = base64.b32encode(_secrets.token_bytes(20)).decode().rstrip("=")
            fid = db("insert into auth.mfa_factors (user_id, friendly_name, factor_type, status, secret) values (%s,%s,'totp','unverified',%s) returning id",
                     (uid, data.get("friendly_name") or "", secret))[0][0]
            uri = "otpauth://totp/%s:%s?secret=%s&issuer=%s" % (data.get("issuer") or "Saaz", c.get("email"), secret, data.get("issuer") or "Saaz")
            return self.send(200, {"id": str(fid), "type": "totp", "friendly_name": data.get("friendly_name") or "",
                                   "totp": {"qr_code": "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'></svg>", "secret": secret, "uri": uri}})
        fid = parts[1]
        own = db("select secret, status::text from auth.mfa_factors where id=%s and user_id=%s", (fid, uid))
        if not own: return self.send(404, {"msg": "Factor not found"})
        if len(parts) == 2 and method == "DELETE":
            if own[0][1] == "verified" and c.get("aal") != "aal2": return self.send(422, {"msg": "AAL2 required"})
            db("delete from auth.mfa_factors where id=%s", (fid,)); return self.send(200, {"id": fid})
        if parts[2] == "challenge": return self.send(200, {"id": str(uuid.uuid4()), "type": "totp", "expires_at": int(time.time()) + 300})
        if parts[2] == "verify":
            code = str(data.get("code", ""))
            if code not in (totp(own[0][0], time.time() - 30), totp(own[0][0]), totp(own[0][0], time.time() + 30)):
                return self.send(422, {"code": 422, "error_code": "mfa_verification_failed", "msg": "Invalid TOTP code entered"})
            db("update auth.mfa_factors set status='verified' where id=%s", (fid,))
            db("update auth.sessions set aal='aal2', factor_id=%s where id=%s", (fid, sid))
            db("insert into auth.mfa_amr_claims (session_id, authentication_method) values (%s,'totp')", (sid,))
            r = db("select email, raw_user_meta_data from auth.users where id=%s", (uid,))
            return self.send(200, session(uid, r[0][0], r[0][1], sid))
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
