"""Speed check for part 16 at a size Saaz is far from today: 20,000 listings, 600,000 views, 30,000 offers over two years.
Every report call must return in under 2 seconds (the rule in the brief). Fresh database; it is filled with generated rows, so reset after."""
import json, time, psycopg2, admin_session
conn = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb", options="-c TimeZone=UTC"); conn.autocommit = True; cur = conn.cursor()
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
A = su("insert into auth.users (email, raw_user_meta_data) values ('admin@saaz.test','{\"name\":\"Ann\",\"country\":\"UG\"}') returning id")[0][0]
su("insert into admins (user_id, name) values (%s,'Ann')", (A,))
S = su("insert into auth.users (email, raw_user_meta_data) values ('s@x.test','{\"name\":\"Sam\",\"country\":\"UG\"}') returning id")[0][0]
B = su("insert into auth.users (email, raw_user_meta_data) values ('b@x.test','{\"name\":\"Bob\",\"country\":\"UG\"}') returning id")[0][0]
t0 = time.time()
su("""insert into vehicles (vin, make, model) select 'JTSPEED' || lpad(g::text, 10, '0'), (array['Toyota','Subaru','Nissan','Honda','Mazda','Mitsubishi'])[1 + g % 6], 'M' || (g % 40) from generate_series(1, 20000) g""")
su("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price, description, photos,
        logbook_name_matches, owner_authorised, live_at, sold_at, created_at, updated_at)
      select v.id, '{S}', 'UG', 'Kampala', (array['live','live','live','sold','draft','awaiting_review','withdrawn','re_review_due'])[1 + g % 8], v.make, v.model, 2010 + g % 12,
        'Petrol', 'Automatic', 'SUV', 'White', '2.0', 50000 + g, 'SPD ' || g, 'UGX', 10000000 + (g % 90) * 1000000, repeat('d', (g % 300)::int), array_fill('p.webp'::text, array[(g % 9)::int]),
        true, true, now() - (g % 700) * interval '1 day', case when g % 8 = 3 then now() - (g % 300) * interval '1 day' end, now() - (g % 720) * interval '1 day', now() - (g % 90) * interval '1 day'
      from (select id, make, model, (row_number() over ())::int g from vehicles where vin like 'JTSPEED%') v""".replace('{S}', str(S)))
su("insert into audit_log (at, actor_role, entity, entity_id, action) select live_at, 'admin', 'listing', id::text, 'approve' from listings where live_at is not null")
su("""insert into listing_views (listing_id, viewer, day) select l.id, 'v' || k, (now() at time zone 'Africa/Kampala')::date - ((h + k * 7) % 700)
      from (select id, hashtext(id::text) & 1023 h, row_number() over () r from listings) l, generate_series(1, 30) k on conflict do nothing""")
su("""insert into deals (listing_id, buyer_id, amount, last_by, status, created_at, updated_at) select id, '{B}', 1000000, 'buyer', 'closed', now() - (r % 700) * interval '1 day', now()
      from (select id, row_number() over () r from listings) l, generate_series(1, 2) k where (r + k) % 4 <> 0""".replace('{B}', str(B)))
su("analyze")
print("rows:", su("select (select count(*) from listings), (select count(*) from listing_views), (select count(*) from deals)")[0], f"(filled in {time.time() - t0:.0f}s)")
claims = admin_session.claims(cur, A)
worst = 0; bad = 0
for report, days, group, flt, cmp in [("inventory", 30, None, {}, False), ("inventory", 30, "make", {}, False), ("inventory", 90, None, {"flag": "stale"}, True),
                                       ("funnel", 7, None, {}, False), ("funnel", 30, None, {}, True), ("funnel", 90, None, {"make": "Toyota"}, True), ("funnel", 365, None, {}, True), ("funnel", 730, None, {}, False)]:
    cur.execute("select set_config('request.jwt.claims',%s,false)", (claims,)); cur.execute("set role authenticated")
    t = time.time()
    cur.execute("select admin_report(%s, current_date - %s, current_date, %s, %s::jsonb, %s, %s, true, 1, 25, false)", (report, days - 1, cmp, json.dumps(flt), group, None))
    r = cur.fetchone()[0]; cur.execute("reset role")
    s = time.time() - t; worst = max(worst, s); bad += s >= 2
    print(("PASS" if s < 2 else "FAIL"), f"{report} {days} days{' by ' + group if group else ''}{' ' + json.dumps(flt) if flt else ''}{' compared' if cmp else ''}: {s:.2f}s, {r['total']} rows")
print(f"\nslowest {worst:.2f}s; {bad} over 2 seconds")
