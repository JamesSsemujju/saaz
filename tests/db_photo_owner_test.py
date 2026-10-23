"""Part 20: a seller's listing only takes photos that seller uploaded. Runs inside one transaction and rolls back, so the database is left as it was."""
import json, os, psycopg2, admin_session, sys
D = os.path.dirname(os.path.abspath(__file__))
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname=sys.argv[1] if len(sys.argv) > 1 else "sb")
cur = conn.cursor()  # not autocommit: everything below is rolled back at the end
passed = failed = 0
def su(sql, args=()):
    cur.execute("reset role; select set_config('request.jwt.claims','',true)"); cur.execute(sql, args)
    return cur.fetchall() if cur.description else None
def as_(uid, sql, args=()):
    claims = admin_session.claims(cur, uid)
    cur.execute("reset role; select set_config('request.jwt.claims',%s,true)", (claims,)); cur.execute("set local role authenticated")
    cur.execute("savepoint s")
    try:
        cur.execute(sql, args); r = cur.fetchall() if cur.description else None; cur.execute("release savepoint s"); return r
    except psycopg2.Error:
        cur.execute("rollback to savepoint s"); raise
    finally:
        cur.execute("reset role")
def err(uid, sql, args=()):
    try: as_(uid, sql, args); return None
    except psycopg2.Error as e: return e.diag.message_primary
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name, extra)
def user(email, name):
    return su("insert into auth.users (email, raw_user_meta_data) values (%s, %s) returning id", (email, json.dumps({"name": name, "country": "UG", "mobile": "+256700000000"})))[0][0]

cur.execute(open(os.path.join(D, "..", "supabase", "marketplace_20_photo_owner.sql")).read())
S = user("po-seller@x.test", "Sam Seller"); T = user("po-other@x.test", "Tom Other")
def up(uid, n):  # what an upload leaves behind: a row in storage.objects under the uploader's folder
    paths = ["%s/p%d.webp" % (uid, i) for i in range(n)]
    for p in paths: su("insert into storage.objects (bucket_id, name) values ('car-photos', %s)", (p,))
    return paths
mine, theirs = up(S, 5), up(T, 4)
car = {"vin": "JTEBU3FJ10K777777", "make": "Toyota", "model": "Harrier", "year": 2015, "fuel": "Petrol", "gearbox": "Automatic", "body": "SUV",
       "colour": "White", "engine": "2.0", "mileage": 84000, "plate": "UBA 777X", "country": "UG", "region": "Kampala", "price": 95000000,
       "description": "Clean Harrier, one owner in Uganda, full service history.", "logbook_name_matches": True}

e = err(S, "select save_listing(%s)", (json.dumps({**car, "photos": theirs}),))
check("another seller's photos are refused", e and "not uploaded from your account" in e, e)
e = err(S, "select save_listing(%s)", (json.dumps({**car, "photos": mine[:3] + [S + "/never-uploaded.webp"]}),))
check("a photo that never finished uploading is refused", e and "did not finish uploading" in e, e)
e = err(S, "select save_listing(%s)", (json.dumps({**car, "photos": [S + "/../" + T + "/p0.webp"] + mine[:3]}),))
check("a path that climbs out of the folder is refused", e is not None, e)
L = as_(S, "select save_listing(%s)", (json.dumps({**car, "photos": mine[:4]}),))[0][0]
check("own uploaded photos are accepted", L is not None)
L2 = as_(S, "select save_listing(%s)", (json.dumps({**car, "id": str(L), "photos": mine[:4] + [mine[4]]}),))[0][0]
check("adding another own photo on edit is accepted", str(L2) == str(L))
# a photo already on the car before part 20 (any path) survives later edits
su("alter table public.listings disable trigger listings_photo_owner"); su("update public.listings set photos = array['legacy-photo.webp'] || photos where id = %s", (L,)); su("alter table public.listings enable trigger listings_photo_owner")
e = err(S, "select save_listing(%s)", (json.dumps({**car, "id": str(L), "price": 94000000, "photos": ["legacy-photo.webp"] + mine[:4]}),))
check("photos already on the car are left alone", e is None, e)
e = err(S, "select save_listing(%s)", (json.dumps({**car, "id": str(L), "photos": ["legacy-photo.webp"] + mine[:4] + [theirs[0]]}),))
check("but a new foreign photo on edit is refused", e and "not uploaded from your account" in e, e)
check("visitors and sellers can't call the rule directly",
      su("select has_function_privilege('authenticated','public.check_listing_photos()','execute') or has_function_privilege('anon','public.check_listing_photos()','execute')")[0][0] is False)
conn.rollback()
print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
