-- Part 14: inspection IDs from the request, Track your inspection, one inspector per inspection, and scoped inspections.
--
-- Lifecycle of one inspection (one row in reviews, one inspection ID):
--   requested  the seller sent the car for inspection; the ID exists from here and can be tracked
--   draft      in progress: ONE inspector started it (start_inspection); only they can fill it in and issue it
--   issued     the report; later 'superseded' by a newer report of the same scope
--   cancelled  the car was withdrawn or rejected before the inspection was issued
--   void       old reports voided before part 13 (Saaz no longer voids)
-- If a garage passes on or releases the car, its in-progress inspections go back to 'requested' (same ID, empty form).
--
-- Scopes: a seller selling a car always gets a General inspection (the one that can make the car live, as before).
-- They can add scoped inspections (Engine and gearbox, Body, Electrics, Brakes and steering). Each scope is its own
-- inspection with its own ID, so the garage owner can give the engine to one inspector and the electrics to another.
-- PROPOSAL, edit freely: which checks each scope covers (table inspection_scopes). Scoped reports never make a car live.

alter table public.reviews drop constraint if exists reviews_status_check;
alter table public.reviews add constraint reviews_status_check
  check (status in ('requested','draft','issued','superseded','void','cancelled'));
alter table public.reviews alter column garage_id drop not null;
alter table public.reviews alter column member_id drop not null;
alter table public.reviews add column if not exists scope text not null default 'general';
alter table public.reviews add column if not exists inspector_id uuid references auth.users(id);
alter table public.reviews add column if not exists requested_at timestamptz;
alter table public.reviews add column if not exists started_at timestamptz;
alter table public.reviews add column if not exists cancelled_at timestamptz;
alter table public.reviews add column if not exists cancel_reason text;
update public.reviews set started_at = coalesce(started_at, created_at), requested_at = coalesce(requested_at, created_at) where started_at is null;

create table if not exists public.inspection_scopes (
  key text primary key,
  name text not null,
  checks text[] not null,
  panels boolean not null default false,
  makes_live boolean not null default false,
  sort int not null default 0
);
alter table public.inspection_scopes enable row level security;
drop policy if exists "anyone reads scopes" on public.inspection_scopes;
create policy "anyone reads scopes" on public.inspection_scopes for select using (true);
revoke insert, update, delete on public.inspection_scopes from anon, authenticated;
-- VIN and odometer are in every scope: they tie the report to this car.
insert into public.inspection_scopes (key, name, checks, panels, makes_live, sort) values
  ('general',  'General inspection',    array['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin'], true, true, 0),
  ('engine',   'Engine and gearbox',    array['engine','gearbox','test_drive','odometer','vin'], false, false, 1),
  ('body',     'Body and chassis',      array['body','chassis','interior','odometer','vin'], true, false, 2),
  ('electrics','Electrics',             array['electrics','odometer','vin'], false, false, 3),
  ('brakes',   'Brakes, steering, tyres', array['brakes','steering','tyres','odometer','vin'], false, false, 4)
on conflict (key) do nothing;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'reviews_scope_fkey') then
    alter table public.reviews add constraint reviews_scope_fkey foreign key (scope) references public.inspection_scopes(key); end if;
end $$;
-- One open inspection per car and scope
create unique index if not exists reviews_one_open_per_scope on public.reviews (listing_id, scope) where status in ('requested','draft');

-- The fingerprint covers the scope of scoped reports (general reports keep their existing fingerprints)
create or replace function public.review_canonical(r public.reviews) returns text
language sql stable security definer set search_path = public as $$
  select concat_ws('|', r.doc_no, r.version, v.vin, l.ref, r.checks::text, r.panels::text, r.odometer, r.verdict, r.score,
    r.member_id, r.garage_id, to_char(r.issued_at at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'), r.valid_until, nullif(r.scope, 'general'))
  from public.vehicles v, public.listings l where v.id = r.vehicle_id and l.id = r.listing_id
$$;

create or replace function public.new_inspection_id() returns text
language sql volatile security definer set search_path = public as $$
  select 'SZR-' || to_char(now() at time zone 'Africa/Kampala','YYYY') || '-' || lpad(nextval('public.review_doc_seq')::text, 6, '0')
$$;
revoke execute on function public.new_inspection_id() from public, anon, authenticated;

-- Request inspections for a car (inside submit_listing, or later by the seller while the car waits for a garage)
create or replace function public.request_inspections(p_listing uuid, p_scopes text[]) returns setof jsonb
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); l public.listings; sc text; rid uuid; did text;
begin
  select * into l from public.listings where id = p_listing for update;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('draft','changes_requested','re_review_due','awaiting_review','review_booked') then
    raise exception 'Inspections can be requested while the car is with Saaz for inspection.'; end if;
  foreach sc in array coalesce(p_scopes, array['general']) loop
    if not exists (select 1 from public.inspection_scopes where key = sc) then raise exception 'Unknown inspection type: %.', sc; end if;
    if exists (select 1 from public.reviews where listing_id = l.id and scope = sc and status in ('requested','draft')) then continue; end if;
    did := public.new_inspection_id();
    insert into public.reviews (listing_id, vehicle_id, scope, status, doc_no, requested_at)
    values (l.id, l.vehicle_id, sc, 'requested', did, now()) returning id into rid;
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end, 'review', rid::text, 'inspection requested',
      jsonb_build_object('inspection_id', did, 'scope', sc, 'listing', l.ref));
    return next jsonb_build_object('id', rid, 'inspection_id', did, 'scope', sc);
  end loop;
end $$;
revoke execute on function public.request_inspections(uuid, text[]) from public, anon;
grant execute on function public.request_inspections(uuid, text[]) to authenticated;

-- Sending a car for inspection always requests the General inspection (and gives its ID)
create or replace function public.submit_listing(p_listing uuid) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); l public.listings; pr public.profiles; n int; minp bigint;
begin
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('draft','changes_requested','re_review_due') then raise exception 'This listing is already submitted.'; end if;
  if not l.saaz_owned then u := l.seller_id; end if;
  select * into pr from public.profiles where id = u;
  if not l.saaz_owned then
    if (public.setting('require_phone_verified'))::text::boolean and not pr.phone_verified then
      raise exception 'Verify your phone number before selling.'; end if;
    if not pr.trusted then
      select count(*) into n from public.listings where seller_id = u and id <> l.id
        and status not in ('draft','sold','rejected','withdrawn');
      if n >= (public.setting('listing_limit'))::text::int then
        raise exception 'You can have % active listings. Withdraw one first.', (public.setting('listing_limit')); end if;
    end if;
    if not l.logbook_name_matches and not l.owner_authorised then
      raise exception 'Confirm the logbook is in your name, or that the owner authorised the sale.'; end if;
  end if;
  if array_length(l.photos,1) is null or array_length(l.photos,1) < 4 then raise exception 'Add at least 4 photos.'; end if;
  if array_length(l.photos,1) > 12 then raise exception 'Use at most 12 photos.'; end if;
  if length(l.description) < 30 then raise exception 'Write at least 30 characters of description.'; end if;
  minp := case when l.currency = 'KES' then (public.setting('min_price_kes'))::text::bigint else (public.setting('min_price_ugx'))::text::bigint end;
  if l.price < minp then raise exception 'The lowest asking price is % %.', l.currency, minp; end if;
  perform public.request_inspections(l.id, array['general']);
  update public.listings set status = 'awaiting_review', submitted_at = now(), admin_note = null, updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'submitted');
  perform public.put_next_in_play(l.id);
end $$;

-- Close inspections that can no longer happen
create or replace function public.cancel_open_inspections(p_listing uuid, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
declare r record;
begin
  for r in select id, doc_no from public.reviews where listing_id = p_listing and status in ('requested','draft') loop
    update public.reviews set status = 'cancelled', cancelled_at = now(), cancel_reason = p_reason where id = r.id;
    perform public.audit('system','review',r.id::text,'inspection cancelled', jsonb_build_object('inspection_id', r.doc_no, 'reason', p_reason));
  end loop;
end $$;
revoke execute on function public.cancel_open_inspections(uuid, text) from public, anon, authenticated;

create or replace function public.withdraw_listing(p_listing uuid) returns void
language plpgsql security definer set search_path = public as $$
declare l public.listings;
begin
  perform public.require_user();
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status in ('reserved','sold','withdrawn') then raise exception 'This listing cannot be withdrawn now.'; end if;
  update public.listings set status = 'withdrawn', updated_at = now() where id = l.id;
  update public.conversations set status = 'closed', closed_at = now() where listing_id = l.id and status in ('in_play','agreed');
  update public.deals set status = 'closed', updated_at = now() where listing_id = l.id and status in ('negotiating','on_hold');
  perform public.cancel_open_inspections(l.id, 'The car was withdrawn.');
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'withdrawn');
end $$;

-- When a garage passes, declines or releases: its in-progress inspections go back to 'requested' (same ID, fresh form)
create or replace function public.pass_on(p_conv uuid, p_status text) returns void
language plpgsql security definer set search_path = public as $$
declare c public.conversations; l public.listings; r record;
begin
  select * into c from public.conversations where id = p_conv;
  if c.status not in ('in_play','agreed') then return; end if;
  update public.conversations set status = p_status, closed_at = now() where id = p_conv;
  select * into l from public.listings where id = c.listing_id;
  if l.status = 'review_booked' then update public.listings set status = 'awaiting_review' where id = l.id; end if;
  for r in select id, doc_no from public.reviews where listing_id = l.id and status in ('requested','draft') and garage_id = c.garage_id loop
    update public.reviews set status = 'requested', garage_id = null, member_id = null, inspector_id = null, started_at = null,
      checks = '{}'::jsonb, panels = '{}'::jsonb, odometer = null, notes = '', in_person = false, updated_at = now() where id = r.id;
    perform public.audit('system','review',r.id::text,'inspection back to requested: the garage left', jsonb_build_object('inspection_id', r.doc_no));
  end loop;
  perform public.audit('system','conversation',p_conv::text,p_status);
  if p_status <> 'closed' or l.status in ('awaiting_review','review_booked') then
    perform public.put_next_in_play(l.id);
  end if;
end $$;

-- ===== Lookup, access and start: three separate steps =====

-- 1. Lookup (anyone, signed in or not): does this ID exist? Nothing else is returned.
create or replace function public.lookup_inspection(p_id text) returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object('found', exists (select 1 from public.reviews where doc_no = upper(trim(coalesce(p_id,'')))))
$$;
grant execute on function public.lookup_inspection(text) to anon, authenticated;

-- Why this person can't start this inspection now (null = they can). Never says more than they may know.
create or replace function public.inspection_start_block(r public.reviews) returns text
language plpgsql stable security definer set search_path = public as $$
declare u uuid := auth.uid(); gid uuid := public.my_garage_id(); l public.listings; c public.conversations;
begin
  if r.status = 'draft' then return case when r.member_id = u then null else 'Another inspector has already started this inspection.' end; end if;
  if r.status = 'issued' or r.status = 'superseded' then return 'This inspection is already completed.'; end if;
  if r.status = 'cancelled' then return 'This inspection was cancelled.'; end if;
  if r.status = 'void' then return 'This inspection was voided.'; end if;
  if r.status <> 'requested' then return 'This inspection can''t be started.'; end if;
  if gid is null then return 'Sign in as a member of a certified garage.'; end if;
  select * into l from public.listings where id = r.listing_id;
  if l.status in ('withdrawn','rejected','sold') then return 'This car is no longer with Saaz for inspection.'; end if;
  select * into c from public.conversations where listing_id = l.id and garage_id = gid and status = 'agreed' limit 1;
  if c is null then return 'This inspection is not booked with your garage.'; end if;
  if r.inspector_id is null and public.my_garage_role() = 'owner' then return null; end if;  -- the owner may take an unassigned inspection
  if r.inspector_id is distinct from u then return 'This inspection is given to someone else in your garage.'; end if;
  return null;
end $$;
revoke execute on function public.inspection_start_block(public.reviews) from public, anon, authenticated;

-- 2. Access (signed in): what is this person's relationship to the inspection, and what may they do?
create or replace function public.inspection_access(p_id text) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_user(); r public.reviews; l public.listings; rel text; c public.conversations; sc public.inspection_scopes; blk text;
begin
  select * into r from public.reviews where doc_no = upper(trim(coalesce(p_id,'')));
  if r is null then raise exception 'No inspection has this ID.'; end if;
  select * into l from public.listings where id = r.listing_id;
  rel := case
    when public.is_admin() then 'saaz'
    when public.is_listing_seller(l) then 'seller'
    when r.member_id = u or r.inspector_id = u then 'inspector'
    when public.my_garage_role() = 'owner' and (r.garage_id = public.my_garage_id()
         or (r.status = 'requested' and exists (select 1 from public.conversations where listing_id = l.id and garage_id = public.my_garage_id() and status = 'agreed'))) then 'garage_owner'
    else null end;
  if rel is null then raise exception 'This inspection isn''t linked to your account.'; end if;
  select * into c from public.conversations where listing_id = l.id and status in ('in_play','agreed') order by opened_at desc limit 1;
  select * into sc from public.inspection_scopes where key = r.scope;
  blk := case when rel in ('inspector','garage_owner') then public.inspection_start_block(r) end;
  return jsonb_build_object('id', r.id, 'inspection_id', r.doc_no, 'scope', r.scope, 'scope_name', sc.name, 'status', r.status, 'relation', rel,
    'car', jsonb_build_object('listing_id', l.id, 'ref', l.ref, 'year', l.year, 'make', l.make, 'model', l.model, 'status', l.status),
    'requested_at', r.requested_at, 'started_at', r.started_at, 'issued_at', r.issued_at, 'cancelled_at', r.cancelled_at, 'cancel_reason', r.cancel_reason,
    'garage', case when c.status = 'agreed' or r.garage_id is not null then coalesce(r.garage_name, (select name from public.garages where id = coalesce(r.garage_id, c.garage_id))) end,
    'booking', case when c is null then null else c.status end, 'inspection_date', c.review_date,
    'inspector', case when rel in ('saaz','garage_owner','inspector') then (select name from public.profiles where id = coalesce(r.member_id, r.inspector_id)) end,
    'mine', r.member_id = u,
    'can_start', rel in ('inspector','garage_owner') and r.status = 'requested' and blk is null,
    'can_continue', r.status = 'draft' and r.member_id = u,
    'start_block', case when r.status = 'requested' then blk end,
    'verify_code', case when r.status in ('issued','superseded','void') then r.verify_code end);
end $$;
revoke execute on function public.inspection_access(text) from public, anon;
grant execute on function public.inspection_access(text) to authenticated;

-- 3. Start: re-checks everything at the moment of starting, and takes the row lock so two people can't both start it
create or replace function public.start_inspection(p_id text) returns uuid
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); r public.reviews; blk text; gid uuid := public.my_garage_id();
begin
  select * into r from public.reviews where doc_no = upper(trim(coalesce(p_id,''))) for update;
  if r is null then raise exception 'No inspection has this ID.'; end if;
  if r.status = 'draft' and r.member_id = u then return r.id; end if;  -- already yours: continue
  blk := public.inspection_start_block(r);
  if blk is not null then raise exception '%', blk; end if;
  update public.reviews set status = 'draft', member_id = u, inspector_id = u, garage_id = gid, started_at = now(), updated_at = now()
  where id = r.id and status = 'requested';
  if not found then raise exception 'This inspection was changed a moment ago. Open it again.'; end if;
  perform public.audit('garage','review',r.id::text,'inspection started', jsonb_build_object('inspection_id', r.doc_no, 'scope', r.scope));
  return r.id;
end $$;
revoke execute on function public.start_inspection(text) from public, anon;
grant execute on function public.start_inspection(text) to authenticated;

-- Older screens start "the car's inspection": that is its General inspection (created on the spot for cars sent before part 14)
create or replace function public.start_review(p_listing uuid) returns uuid
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid := public.my_garage_id(); l public.listings; did text; cnv public.conversations;
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  select * into l from public.listings where id = p_listing;
  select * into cnv from public.conversations where listing_id = p_listing and garage_id = gid and status = 'agreed' limit 1;
  if cnv is null then raise exception 'This car is not booked with your garage.'; end if;
  select doc_no into did from public.reviews where listing_id = p_listing and scope = 'general' and status in ('requested','draft');
  if did is null then
    did := public.new_inspection_id();
    insert into public.reviews (listing_id, vehicle_id, scope, status, doc_no, requested_at, inspector_id)
    values (l.id, l.vehicle_id, 'general', 'requested', did, now(), cnv.inspector_id);
  end if;
  update public.reviews set inspector_id = cnv.inspector_id where doc_no = did and status = 'requested' and inspector_id is null and cnv.inspector_id is not null;
  return public.start_inspection(did);
end $$;

-- The owner gives one inspection to one inspector (before it starts). One inspector per inspection.
create or replace function public.assign_inspection(p_review uuid, p_member uuid) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); r public.reviews; gid uuid := public.my_garage_id(); who text; l public.listings;
begin
  select * into r from public.reviews where id = p_review for update;
  if r is null or gid is null or public.my_garage_role() <> 'owner'
     or not exists (select 1 from public.conversations where listing_id = r.listing_id and garage_id = gid and status = 'agreed') then
    raise exception 'Only the owner of the garage booked for this car can give out its inspections.'; end if;
  if r.status <> 'requested' then raise exception 'This inspection has started: it stays with the inspector who started it.'; end if;
  if p_member is not null and not exists (select 1 from public.garage_members where garage_id = gid and user_id = p_member and status = 'active') then
    raise exception 'Choose an active member of your garage.'; end if;
  update public.reviews set inspector_id = p_member, garage_id = case when p_member is null then null else gid end, updated_at = now() where id = r.id;
  select * into l from public.listings where id = r.listing_id;
  select name into who from public.profiles where id = p_member;
  if p_member is not null and p_member <> u then
    perform public.notify(p_member, 'inspection_assigned', 'Inspection ' || r.doc_no || ' is yours: ' || l.year || ' ' || l.make || ' ' || l.model || '.', '#/inspection/' || r.doc_no, '{app,sms}');
  end if;
  perform public.audit('garage','review',r.id::text, case when p_member is null then 'inspection taken back by the owner' else 'inspection given to ' || who end,
    jsonb_build_object('inspection_id', r.doc_no));
end $$;
revoke execute on function public.assign_inspection(uuid, uuid) from public, anon;
grant execute on function public.assign_inspection(uuid, uuid) to authenticated;

-- An inspector with any inspection of a booked car sees the job (car, date, messages); the owner sees all
create or replace function public.garage_sees_listing_work(p_listing uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.reviews r where r.listing_id = p_listing and r.garage_id = public.my_garage_id()
                 and (r.inspector_id = auth.uid() or r.member_id = auth.uid()) and r.status in ('requested','draft'))
$$;
create or replace function public.garage_sees(p_garage uuid, p_inspector uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select p_garage = public.my_garage_id() and (public.my_garage_role() = 'owner' or p_inspector = auth.uid())
$$;
drop policy if exists "seller, garage owner or the job's inspector, admin" on public.conversations;
create policy "seller, garage owner or the job's inspectors, admin" on public.conversations for select
  using (public.is_admin() or public.garage_sees(garage_id, inspector_id)
    or (garage_id = public.my_garage_id() and public.garage_sees_listing_work(listing_id)) or public.is_seller_of(listing_id));
create or replace function public.garage_on_listing(p_listing uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.conversations c where c.listing_id = p_listing and
    (public.garage_sees(c.garage_id, c.inspector_id) or (c.garage_id = public.my_garage_id() and public.garage_sees_listing_work(p_listing))))
$$;

-- Report rules: the garage owner, the inspector (assigned or author), the seller, Saaz
drop policy if exists "current inspection of a public car, garage owner or its author, seller, admin" on public.reviews;
create or replace function public.owner_booked(p_listing uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.my_garage_role() = 'owner' and exists (select 1 from public.conversations
    where listing_id = p_listing and garage_id = public.my_garage_id() and status = 'agreed')
$$;
create policy "current inspection of a public car, garage owner or its inspector, seller, admin" on public.reviews for select
  using ((status = 'issued' and public.is_public_review(id)) or public.is_admin()
    or (garage_id = public.my_garage_id() and (public.my_garage_role() = 'owner' or member_id = auth.uid() or inspector_id = auth.uid()))
    or (status = 'requested' and garage_id is null and public.owner_booked(listing_id))
    or public.is_seller_of(listing_id));

create or replace function public.garage_jobs() returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
declare gid uuid := public.my_garage_id(); own boolean := public.my_garage_role() = 'owner';
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  return query
  select jsonb_build_object('conversation', to_jsonb(c), 'listing',
      jsonb_build_object('id',l.id,'ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'region',l.region,'mileage',l.mileage,'status',l.status,'photos',l.photos),
      'inspector', (select name from public.profiles where id = c.inspector_id),
      'mine', c.inspector_id = auth.uid(),
      'inspections', (select coalesce(jsonb_agg(jsonb_build_object('id', r.id, 'inspection_id', r.doc_no, 'scope', r.scope, 'scope_name', s.name, 'status', r.status,
            'inspector', (select name from public.profiles where id = coalesce(r.member_id, r.inspector_id)), 'inspector_id', coalesce(r.member_id, r.inspector_id),
            'mine', coalesce(r.member_id, r.inspector_id) = auth.uid(), 'verify_code', r.verify_code) order by s.sort), '[]'::jsonb)
          from public.reviews r join public.inspection_scopes s on s.key = r.scope
          where r.listing_id = l.id and (r.garage_id = gid or (r.status = 'requested' and c.status = 'agreed'))
            and r.status in ('requested','draft','issued')
            and (own or coalesce(r.member_id, r.inspector_id) = auth.uid())),
      'draft', (select jsonb_build_object('id',r.id,'doc_no',r.doc_no,'member',p.name,'mine',r.member_id = auth.uid())
                from public.reviews r join public.profiles p on p.id = r.member_id
                where r.listing_id = l.id and r.garage_id = gid and r.status = 'draft' and r.scope = 'general' limit 1),
      'unread_from_seller', (select count(*) from public.messages m where m.conversation_id = c.id and m.side = 'seller'))
  from public.conversations c join public.listings l on l.id = c.listing_id
  where public.garage_sees(c.garage_id, c.inspector_id) or (c.garage_id = gid and public.garage_sees_listing_work(l.id))
  order by (c.status in ('in_play','agreed')) desc, c.opened_at desc;
end $$;

-- ===== Saving and issuing follow the scope =====
create or replace function public.save_review(p_review uuid, p jsonb) returns void
language plpgsql security definer set search_path = public as $$
declare r public.reviews;
begin
  perform public.require_user();
  select * into r from public.reviews where id = p_review for update;
  if r.member_id is distinct from auth.uid() or r.status <> 'draft' then raise exception 'Only the inspector who started this inspection can change it.'; end if;
  if public.my_garage_id() is distinct from r.garage_id then raise exception 'Your garage access has ended.'; end if;
  update public.reviews set checks = coalesce(p->'checks','{}'::jsonb), panels = coalesce(p->'panels','{}'::jsonb),
    odometer = nullif(p->>'odometer','')::int, notes = coalesce(p->>'notes',''), in_person = coalesce((p->>'in_person')::boolean,false),
    updated_at = now()
  where id = p_review;
end $$;

create or replace function public.discard_review(p_review uuid) returns void
language plpgsql security definer set search_path = public as $$
declare r public.reviews;
begin
  select * into r from public.reviews where id = p_review for update;
  if r.member_id is distinct from auth.uid() or r.status <> 'draft' then raise exception 'Only the inspector who started this inspection can stop it.'; end if;
  -- The inspection keeps its ID and goes back to requested, still given to the same inspector
  update public.reviews set status = 'requested', member_id = null, started_at = null, checks = '{}'::jsonb, panels = '{}'::jsonb,
    odometer = null, notes = '', in_person = false, updated_at = now() where id = p_review;
  perform public.audit('garage','review',p_review::text,'inspection stopped: back to requested', jsonb_build_object('inspection_id', r.doc_no));
end $$;

create or replace function public.issue_review(p_review uuid) returns jsonb
language plpgsql security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
declare u uuid := public.require_user(); r public.reviews; l public.listings; k text; val text; s numeric := 0; maxs numeric := 0;
  safety text[] := array['brakes','steering','odometer','vin']; v_verdict text := 'pass'; panel_pen int := 0; v_score int;
  prev_top int; v_flag text; ver int; code text; fp text; pr public.profiles; m public.garage_members; g public.garages;
  auto_live boolean; v_trusted boolean; sc public.inspection_scopes; others int;
begin
  select * into r from public.reviews where id = p_review for update;
  if r.member_id is distinct from u or r.status <> 'draft' then raise exception 'Only the inspector who started this inspection can issue it.'; end if;
  if public.my_garage_id() is distinct from r.garage_id then raise exception 'Your garage access has ended.'; end if;
  if not exists (select 1 from public.conversations where listing_id = r.listing_id and garage_id = r.garage_id and status = 'agreed') then
    raise exception 'This car is no longer booked with your garage.'; end if;
  if not r.in_person then raise exception 'Confirm the car was inspected in person and the VIN checked.'; end if;
  if r.odometer is null then raise exception 'Enter the odometer reading.'; end if;
  select * into sc from public.inspection_scopes where key = r.scope;
  foreach k in array sc.checks loop
    val := r.checks->>k;
    if val not in ('pass','advise','fail') or val is null then raise exception 'Mark every check: % is missing.', k; end if;
    maxs := maxs + case when k = any(safety) then 10 else 6 end;
    s := s + (case when k = any(safety) then 10 else 6 end) * (case val when 'pass' then 1 when 'advise' then 0.5 else 0 end);
    if val = 'fail' and k = any(safety) then v_verdict := 'fail';
    elsif val <> 'pass' and v_verdict = 'pass' then v_verdict := 'conditional'; end if;
  end loop;
  if v_verdict <> 'pass' and length(trim(r.notes)) < 10 then raise exception 'Add notes: something is not a Pass.'; end if;
  if sc.panels then
    foreach k in array public.panel_keys() loop
      panel_pen := panel_pen + case coalesce(r.panels->>k,'none') when 'scratch' then 1 when 'dent' then 2 when 'repaint' then 2 when 'damage' then 4 else 0 end;
    end loop;
  end if;
  v_score := greatest(0, least(100, round(s / maxs * 100) - panel_pen));
  select * into l from public.listings where id = r.listing_id for update;
  select max(km) into prev_top from public.odometer_readings where vehicle_id = r.vehicle_id;
  if prev_top is not null and r.odometer < prev_top then v_flag := 'Lower than an earlier Saaz reading (' || prev_top || ' km)';
  elsif abs(r.odometer - l.mileage) > l.mileage * (public.setting('mileage_flag_pct'))::text::numeric / 100 then
    v_flag := 'Differs by more than ' || (public.setting('mileage_flag_pct')) || '% from the seller''s ' || l.mileage || ' km'; end if;
  select coalesce(max(version),0) + 1 into ver from public.reviews where listing_id = r.listing_id and scope = r.scope and status not in ('draft','requested','cancelled');
  select * into pr from public.profiles where id = u;
  select * into m from public.garage_members where user_id = u and status <> 'removed';
  select * into g from public.garages where id = r.garage_id;
  update public.reviews set status = 'superseded' where listing_id = r.listing_id and scope = r.scope and status = 'issued';
  update public.reviews set status = 'issued', verdict = v_verdict, score = v_score,
    doc_no = coalesce(doc_no, public.new_inspection_id()),
    version = ver, odometer_flag = v_flag, issued_at = date_trunc('second', now()),
    valid_until = current_date + (public.setting('review_valid_days'))::text::int,
    panels = case when sc.panels then panels else '{}'::jsonb end,
    member_name = pr.name, member_role = m.role, garage_name = g.name, garage_certified_at = g.certified_at, updated_at = now()
  where id = p_review returning * into r;
  fp := encode(sha256(convert_to(public.review_canonical(r), 'UTF8')), 'hex');
  code := upper(substr(fp, 1, 4) || '-' || substr(fp, 5, 4) || '-' || substr(fp, 9, 4));
  update public.reviews set fingerprint = fp, verify_code = code where id = p_review;
  insert into public.odometer_readings (vehicle_id, km, source, review_id, flagged) values (r.vehicle_id, r.odometer, 'review', r.id, v_flag);
  auto_live := false;
  if sc.makes_live then
    select p2.trusted into v_trusted from public.profiles p2 where p2.id = l.seller_id;
    auto_live := (l.saaz_owned or coalesce(v_trusted,false)) and r.verdict = 'pass' and v_flag is null;
    update public.listings set current_review_id = r.id, updated_at = now(),
      status = case when auto_live then 'live' else 'awaiting_approval' end,
      live_at = case when auto_live then now() else live_at end
    where id = l.id;
  end if;
  -- The booking closes when this garage has no open inspection of the car left
  select count(*) into others from public.reviews where listing_id = l.id and status in ('requested','draft') and (garage_id = r.garage_id or garage_id is null);
  if others = 0 then
    update public.conversations set status = 'closed', closed_at = now() where listing_id = l.id and garage_id = r.garage_id and status = 'agreed';
  end if;
  perform public.audit('garage','review',r.id::text,'issued', jsonb_build_object('doc_no',r.doc_no,'scope',r.scope,'verdict',r.verdict,'score',r.score,'odometer',r.odometer,'flag',v_flag));
  perform public.notify(x, 'review_issued', 'Saaz ' || lower(sc.name) || ' report ' || r.doc_no || ' for ' || l.ref || ' is issued (' || initcap(r.verdict) || ', ' || r.score || '/100). ' ||
    case when not sc.makes_live then '' when auto_live then 'Your car is live.' else 'Saaz will check it within ' || (public.setting('approval_response')#>>'{}') || '.' end,
    '#/inspection/' || r.doc_no, '{app,email,sms}') from public.seller_side_users(l) x;
  if sc.makes_live and not auto_live then perform public.notify_admins('review_issued','Inspection report issued for ' || l.ref || ': waiting for approval.','#/admin/car/' || l.id); end if;
  return jsonb_build_object('doc_no',r.doc_no,'verify_code',code,'verdict',r.verdict,'score',r.score,'live',auto_live,'scope',r.scope);
end $$;

-- Reports and the public check name the scope
create or replace function public.review_document(p_code text) returns jsonb
language plpgsql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
declare r public.reviews; l public.listings; v public.vehicles; sc public.inspection_scopes;
begin
  select * into r from public.reviews where verify_code = upper(trim(p_code)) and status not in ('draft','requested','cancelled');
  if r is null then return null; end if;
  select * into l from public.listings where id = r.listing_id;
  select * into v from public.vehicles where id = r.vehicle_id;
  select * into sc from public.inspection_scopes where key = r.scope;
  return jsonb_build_object('review', to_jsonb(r) - 'notes' || jsonb_build_object('notes', r.notes),
    'status', case when r.status = 'issued' and r.valid_until < current_date then 'expired' else r.status end,
    'intact', encode(sha256(convert_to(public.review_canonical(r),'UTF8')),'hex') = r.fingerprint,
    'scope', jsonb_build_object('key', sc.key, 'name', sc.name, 'checks', sc.checks, 'panels', sc.panels),
    'saaz_stance', public.saaz_stance(r.id), 'opinions', public.opinions_of(r.id),
    'listing', jsonb_build_object('ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'plate',l.plate,'colour',l.colour,'engine',l.engine,
       'fuel',l.fuel,'gearbox',l.gearbox,'body',l.body,'country',l.country,'mileage',l.mileage),
    'vehicle', jsonb_build_object('vin',v.vin,'source',v.source,'first_record_date',v.first_record_date,'import_mileage',v.import_mileage),
    'odometer', (select jsonb_agg(jsonb_build_object('km',o.km,'source',o.source,'at',o.recorded_at,'flagged',o.flagged) order by o.recorded_at)
                 from public.odometer_readings o where o.vehicle_id = v.id));
end $$;

create or replace function public.car_inspections(p_listing uuid) returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
declare l public.listings; sees_all boolean;
begin
  select * into l from public.listings where id = p_listing;
  if l is null then return; end if;
  sees_all := public.is_admin() or public.is_listing_seller(l);
  return query
  select jsonb_build_object('id', r.id, 'doc_no', r.doc_no, 'scope', r.scope, 'scope_name', s.name, 'status', r.status,
    'garage', coalesce(r.garage_name, g.name), 'inspector', coalesce(r.member_name, p.name), 'verdict', r.verdict, 'score', r.score,
    'issued_at', r.issued_at, 'started_at', coalesce(r.started_at, r.requested_at, r.created_at), 'verify_code', r.verify_code,
    'saaz_stance', public.saaz_stance(r.id), 'listing_ref', l2.ref)
  from public.reviews r join public.listings l2 on l2.id = r.listing_id join public.inspection_scopes s on s.key = r.scope
    left join public.garages g on g.id = r.garage_id left join public.profiles p on p.id = coalesce(r.member_id, r.inspector_id)
  where r.vehicle_id = l.vehicle_id
    and (sees_all or (r.garage_id = public.my_garage_id() and (public.my_garage_role() = 'owner' or r.member_id = auth.uid() or r.inspector_id = auth.uid())))
  order by coalesce(r.requested_at, r.created_at);
end $$;

-- Opening by ID from the garage dashboard goes through the same access check
create or replace function public.open_inspection(p_id text) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare a jsonb := public.inspection_access(p_id);
begin
  if a->>'relation' not in ('saaz','inspector','garage_owner') then raise exception 'This inspection isn''t linked to your account.'; end if;
  return jsonb_build_object('id', a->'id', 'status', a->'status', 'verify_code', a->'verify_code', 'listing_id', a->'car'->'listing_id', 'inspection_id', a->'inspection_id');
end $$;

-- Rejecting a car cancels its open inspections (approve, changes and unlist leave them as they are)
create or replace function public.cancel_on_reject() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.status in ('rejected','withdrawn') and old.status is distinct from new.status then
    perform public.cancel_open_inspections(new.id, case new.status when 'rejected' then 'Saaz did not approve the car.' else 'The car was withdrawn.' end);
  end if;
  return new;
end $$;
drop trigger if exists listings_cancel_inspections on public.listings;
create trigger listings_cancel_inspections after update of status on public.listings for each row execute function public.cancel_on_reject();
