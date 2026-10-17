import base64, hashlib, hmac, json, time
SECRET = b"saaz-local-test-secret-saaz-local-test-secret"
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def jwt(uid, email):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": str(uid), "email": email, "role": "authenticated", "aud": "authenticated", "exp": int(time.time()) + 3600}).encode())
    return h + "." + p + "." + b64(hmac.new(SECRET, (h + "." + p).encode(), hashlib.sha256).digest())
