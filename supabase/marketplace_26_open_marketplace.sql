-- Saaz marketplace part 26: open marketplace (6 Nov 2026). Run after part 25.
-- Allan's request: every car can be on Saaz, with its inspection status shown. One switch, Admin, Settings, "open_market"
-- (false = today's rule, no inspection no listing; true = the open marketplace). Off until Saaz turns it on.
-- With it on:
--   - A seller can list now, without an inspection. Saaz approves the car and it goes live marked Not inspected.
--     Getting a Saaz inspection first still works as before, and the car goes live marked Inspected.
--   - A buyer can buy a Not inspected car as it is, or ask for a Saaz inspection. The usual garage line runs while the car
--     stays on sale; the buyer pays the garage directly (no money moves through Saaz). The report goes on the car's page for
--     everyone (James, 6 Nov 2026).
--   - Transparency (James, 6 Nov 2026): a report stays on the car, pass or fail. A car that fails safety is not taken off;
--     its page shows every Saaz inspection of the car, and Saaz can approve a car whose report failed.
--   - An inspection that expires no longer takes the car off sale: the car shows "Inspection expired".
-- Also: sellers can open Edit on their own cars again (a part 21 side effect), and car_history (every Saaz report of the car, for its public page). The app reads the switch from settings (visitors can read settings).
-- Changes no existing row except adding one setting and one column. Safe to run twice.

insert into public.settings (key, value, note) values
  ('open_market', 'false'::jsonb, 'Open marketplace: true lets cars go live without a Saaz inspection, marked Not inspected (Allan, 6 Nov 2026)')
on conflict (key) do nothing;
insert into public.request_limits (path, max_hits, per_seconds, note) values
  ('/rpc/buyer_request_inspection', 5, 86400, 'Buyer inspection requests')
on conflict (path) do nothing;

-- Who asked for an inspection when it was a buyer (null: the seller or Saaz). Never shown publicly.
alter table public.reviews add column if not exists requested_by uuid references auth.users(id) on delete set null;

create or replace function public.open_market() returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((select value = 'true'::jsonb from public.settings where key = 'open_market'), false)
$$;
revoke execute on function public.open_market() from public, anon, authenticated;

-- A car is in the garage line while it waits for its first inspection, or (open marketplace) while it is on sale with a
-- Saaz inspection requested and not yet issued.
create or replace function public.in_line(l public.listings) returns boolean language sql stable security definer set search_path = public as $$
  select l.status in ('awaiting_review','review_booked')
      or (l.status in ('live','reserved') and exists (select 1 from public.reviews r where r.listing_id = l.id and r.scope = 'general' and r.status in ('requested','draft')))
$$;
revoke execute on function public.in_line(public.listings) from public, anon, authenticated;

create or replace function public.put_next_in_play(p_listing uuid)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare l public.listings; gid uuid; cid uuid; gname text;
begin
  select * into l from public.listings where id = p_listing;
  if not public.in_line(l) then return null; end if;
  gid := public.next_garage(l);
  if gid is null then
    update public.listings set line_empty = true where id = p_listing;
    perform public.notify_admins('line_empty','No garage left in line for ' || l.ref || '. Assign one or restart the line.','#/admin/car/' || l.id);
    if not l.saaz_owned then
      perform public.notify(l.seller_id, 'line_empty', 'Saaz will find a garage for ' || l.ref || ' and let you know.', '#/my/cars/' || l.id);
    end if;
    perform public.audit('system','listing',l.id::text,'garage line empty');
    return null;
  end if;
  insert into public.conversations (listing_id, garage_id, round, deadline)
  values (p_listing, gid, l.line_round, now() + make_interval(hours => (public.setting('garage_contact_hours'))::text::int))
  returning id into cid;
  update public.listings set line_empty = false where id = p_listing;
  select name into gname from public.garages where id = gid;
  perform public.notify_garage(gid,'garage_in_play','A ' || l.year || ' ' || l.make || ' ' || l.model || ' in ' || l.region ||
    ' is yours to contact. Message the seller within ' || (public.setting('garage_contact_hours')) || ' hours.' ||
    case when exists (select 1 from public.reviews r where r.listing_id = l.id and r.status = 'requested' and r.requested_by is not null)
      then ' A buyer asked for this inspection and pays your fee.' else '' end,'#/garage/job/' || cid);
  perform public.notify(u, 'garage_in_play', gname || ' will contact you about ' || l.ref || ' inside Saaz.', '#/my/cars/' || l.id)
    from public.seller_side_users(l) u;
  perform public.audit('system','conversation',cid::text,'garage put in play', jsonb_build_object('listing',l.ref,'garage',gname));
  return cid;
end $function$;

create or replace function public.pass_on(p_conv uuid, p_status text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
  if p_status <> 'closed' or public.in_line(l) then
    perform public.put_next_in_play(l.id);
  end if;
end $function$;

create or replace function public.seller_respond(p_conv uuid, p_agree boolean, p_reason text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare c public.conversations; l public.listings;
begin
  perform public.require_user();
  select * into c from public.conversations where id = p_conv;
  select * into l from public.listings where id = c.listing_id;
  if not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if c.status <> 'in_play' then raise exception 'This conversation is not waiting for you.'; end if;
  if p_agree then
    if c.garage_first_message_at is null then raise exception 'You can agree once the garage has messaged you.'; end if;
    update public.conversations set status = 'agreed' where id = p_conv;
    update public.listings set status = 'review_booked', updated_at = now() where id = l.id and status = 'awaiting_review';   -- a car on sale stays on sale
    -- A buyer asked for this inspection: tell them which garage, and how to reach it about the fee
    perform public.notify(r.requested_by, 'buyer_inspection_booked', g.name || ' will inspect ' || l.ref || '. Call them on ' || coalesce(nullif(g.phone,''), 'the number on their Saaz page') ||
      ' to agree the fee. You pay the garage directly. The report shows on the car''s page when it is issued.', '#/car/' || l.ref, '{app,sms}')
      from public.reviews r, public.garages g where r.listing_id = l.id and r.status = 'requested' and r.requested_by is not null and g.id = c.garage_id;
    perform public.notify_garage(c.garage_id,'seller_agreed','The seller of ' || l.ref || ' agreed. Set an inspection date and start the inspection when the car is with you.','#/garage/job/' || p_conv);
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'conversation',p_conv::text,'agreed');
  else
    if coalesce(trim(p_reason),'') <> '' then insert into public.pass_reasons values (p_conv, trim(p_reason)); end if;
    perform public.notify_garage(c.garage_id,'seller_passed','The seller of ' || l.ref || ' chose another garage.','#/garage');
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'conversation',p_conv::text,'passed');
    perform public.pass_on(p_conv, 'passed');
  end if;
end $function$;

create or replace function public.issue_review(p_review uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
 SET "TimeZone" TO 'Africa/Kampala'
AS $function$
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
  if sc.makes_live and l.status in ('live','reserved') then
    -- Open marketplace: a car already on sale stays on sale. The new report shows on it, pass or fail.
    update public.listings set current_review_id = r.id, updated_at = now() where id = l.id;
    perform public.notify_admins('review_issued','New inspection report on ' || l.ref || ', which is on sale (' || initcap(r.verdict) || ').','#/admin/car/' || l.id);
  elsif sc.makes_live then
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
    case when not sc.makes_live then '' when l.status in ('live','reserved') then 'It shows on your car''s page.' when auto_live then 'Your car is live.' else 'Saaz will check it within ' || (public.setting('approval_response')#>>'{}') || '.' end,
    '#/inspection/' || r.doc_no, '{app,email,sms}') from public.seller_side_users(l) x;
  if r.requested_by is not null then
    perform public.notify(r.requested_by, 'buyer_inspection_ready', 'The Saaz inspection you asked for on ' || l.ref || ' is ready: ' || initcap(r.verdict) || ', ' || r.score || '/100.',
      '#/report/' || code, '{app,sms}');
  end if;
  if sc.makes_live and not auto_live and l.status not in ('live','reserved') then perform public.notify_admins('review_issued','Inspection report issued for ' || l.ref || ': waiting for approval.','#/admin/car/' || l.id); end if;
  return jsonb_build_object('doc_no',r.doc_no,'verify_code',code,'verdict',r.verdict,'score',r.score,'live',auto_live,'scope',r.scope);
end $function$;

create or replace function public.admin_decide_listing(p_listing uuid, p_decision text, p_note text DEFAULT NULL::text, p_new_review boolean DEFAULT false)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare l public.listings; r public.reviews;
begin
  perform public.require_admin();
  select * into l from public.listings where id = p_listing;
  select * into r from public.reviews where id = l.current_review_id;
  if p_decision in ('changes','reject','unlist') and coalesce(trim(p_note),'') = '' then raise exception 'A note to the seller is required.'; end if;
  if p_decision = 'approve' then
    if l.status <> 'awaiting_approval' then raise exception 'Nothing to approve.'; end if;
    if r.id is null and not public.open_market() then raise exception 'This car has no Saaz inspection yet.'; end if;
    if r.verdict = 'fail' and not public.open_market() then raise exception 'A safety Fail cannot be approved.'; end if;   -- open marketplace: shown, with the report
    if public.saaz_stance(r.id) = 'object' then raise exception 'Saaz objected to this report. Support it (with a reason) or ask for a new inspection first.'; end if;
    update public.listings set status = 'live', live_at = now(), admin_note = null, updated_at = now() where id = l.id;
    update public.deals set status = 'negotiating', updated_at = now() where listing_id = l.id and status = 'on_hold'
      and not exists (select 1 from public.deals d2 where d2.listing_id = l.id and d2.status = 'agreed');
  elsif p_decision = 'changes' then
    update public.listings set status = 'changes_requested', admin_note = p_note, updated_at = now() where id = l.id;
    if p_new_review then update public.listings set current_review_id = null where id = l.id; end if;
  elsif p_decision = 'reject' then
    update public.listings set status = 'rejected', admin_note = p_note, updated_at = now() where id = l.id;
  elsif p_decision = 'unlist' then
    if l.status not in ('live','re_review_due') then raise exception 'Only live cars can be unlisted.'; end if;
    update public.listings set status = 'withdrawn', admin_note = p_note, updated_at = now() where id = l.id;
    update public.deals set status = 'closed', updated_at = now() where listing_id = l.id and status in ('negotiating','on_hold');
  else raise exception 'Unknown decision.'; end if;
  perform public.audit('admin','listing',l.id::text,p_decision, jsonb_build_object('before',l.status,'note',p_note));
  perform public.notify(x, 'listing_' || p_decision, case p_decision when 'approve' then l.ref || ' is live on Saaz.'
    when 'changes' then 'Changes needed on ' || l.ref || ': ' || p_note when 'reject' then l.ref || ' was not approved: ' || p_note
    else l.ref || ' was taken off Saaz: ' || p_note end, '#/my/cars/' || l.id, '{app,email,sms}') from public.seller_side_users(l) x;
end $function$;

create or replace function public.submit_listing(p_listing uuid, p_inspect boolean DEFAULT true)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
  if not coalesce(p_inspect, true) then   -- open marketplace: list now, Saaz approves it, it goes live marked Not inspected
    if not public.open_market() then raise exception 'Every car needs a Saaz inspection before it goes on sale.'; end if;
    update public.listings set status = 'awaiting_approval', submitted_at = now(), admin_note = null, updated_at = now() where id = l.id;
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'submitted without an inspection');
    perform public.notify_admins('listing_submitted', l.ref || ' is waiting for approval, not inspected.', '#/admin/car/' || l.id);
    return;
  end if;
  perform public.request_inspections(l.id, array['general']);
  update public.listings set status = 'awaiting_review', submitted_at = now(), admin_note = null, updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'submitted');
  perform public.put_next_in_play(l.id);
end $function$;

create or replace function public.tick()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
 SET "TimeZone" TO 'Africa/Kampala'
AS $function$
declare c record;
begin
  if not pg_try_advisory_xact_lock(hashtext('saaz.tick')) then return; end if;   -- already running for someone else
  for c in select id from public.conversations where status = 'in_play' and garage_first_message_at is null and deadline < now() loop
    perform public.pass_on(c.id, 'timed_out');
  end loop;
  update public.listings l set status = 're_review_due', updated_at = now()
    from public.reviews r where r.id = l.current_review_id and l.status = 'live' and r.valid_until < current_date
      and not public.open_market();   -- open marketplace: the car stays on sale, shown as Inspection expired
end $function$;

create or replace function public.listing_card(l listings)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
 SET "TimeZone" TO 'Africa/Kampala'
AS $function$
  select to_jsonb(l) - 'logbook_name_matches' - 'owner_authorised' - 'rule_min_pct' - 'rule_min_amount' - 'admin_note' - 'seller_id'
    || jsonb_build_object(
      'views_7d', (select count(*) from public.listing_views v where v.listing_id = l.id and v.day > current_date - 7),
      'saves', (select count(*) from public.saves s where s.listing_id = l.id),
      'offers', (select count(*) from public.deals d where d.listing_id = l.id),
      'review', (select jsonb_build_object('verdict',r.verdict,'score',r.score,'verify_code',r.verify_code,'valid_until',r.valid_until,'garage',r.garage_name)
                 from public.reviews r where r.id = l.current_review_id),
      'saved', exists (select 1 from public.saves s where s.listing_id = l.id and s.user_id = auth.uid()),
      'inspection_requested', exists (select 1 from public.reviews r2 where r2.listing_id = l.id and r2.scope = 'general' and r2.status in ('requested','draft')))
$function$;

create or replace function public.listing_stats(p_listing uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
 SET "TimeZone" TO 'Africa/Kampala'
AS $function$
declare l public.listings; full_access boolean; days numeric; res jsonb;
begin
  select * into l from public.listings where id = p_listing;
  if l is null then return null; end if; -- part 21 visibility
  if l.status not in ('live','reserved','sold') and not (public.is_listing_seller(l) or public.is_admin()) then return null; end if;
  full_access := public.is_listing_seller(l) or public.is_admin();
  res := jsonb_build_object(
    'views_7d', (select count(*) from public.listing_views where listing_id = l.id and day > current_date - 7),
    'saves', (select count(*) from public.saves where listing_id = l.id),
    'offers', (select count(*) from public.deals where listing_id = l.id),
    'inspection_requested', exists (select 1 from public.reviews r where r.listing_id = l.id and r.scope = 'general' and r.status in ('requested','draft')));
  if not full_access then return res; end if;
  days := greatest(1, extract(epoch from (now() - coalesce(l.live_at, now()))) / 86400);
  return res || jsonb_build_object(
    'views_total', (select count(*) from public.listing_views where listing_id = l.id),
    'auto_rejected', (select count(*) from public.deals where listing_id = l.id and status = 'auto_rejected'),
    'highest_offer', (select max(e.amount) from public.deal_events e join public.deals d on d.id = e.deal_id
                      where d.listing_id = l.id and e.kind in ('offer','counter') and e.by_side = 'buyer'),
    'daily_14', (select jsonb_agg(jsonb_build_object('day',g.d::date,'views',(select count(*) from public.listing_views v where v.listing_id = l.id and v.day = g.d::date)) order by g.d)
                 from generate_series(current_date - 13, current_date, interval '1 day') g(d)),
    'views_per_day', round((select count(*) from public.listing_views where listing_id = l.id) / days, 1),
    'model_views_per_day', (select round(avg(c.n / greatest(1, extract(epoch from (now() - o.live_at)) / 86400)), 1)
                            from public.listings o cross join lateral (select count(*)::numeric n from public.listing_views v where v.listing_id = o.id) c
                            where o.make = l.make and o.model = l.model and o.id <> l.id and o.live_at is not null),
    'model', public.model_sales(l.make, l.model, l.country));
end $function$;

drop function if exists public.submit_listing(uuid);
revoke execute on function public.submit_listing(uuid, boolean) from public, anon;
grant execute on function public.submit_listing(uuid, boolean) to authenticated;

-- Fix (found 6 Nov 2026): since part 21 only admins could read vehicles, so a seller opening Edit on their own draft got
-- "Couldn't load this page". A seller may read the vehicle record of their own cars again. Nobody else's.
drop policy if exists "sellers read their cars' vehicles" on public.vehicles;
create policy "sellers read their cars' vehicles" on public.vehicles for select
  using (exists (select 1 from public.listings l where l.vehicle_id = vehicles.id and public.is_seller_of(l.id)));

-- A buyer asks for a Saaz inspection of a car on sale that has none, or whose inspection expired
create or replace function public.buyer_request_inspection(p_listing uuid) returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare u uuid := public.require_user(); l public.listings; r public.reviews; did text; rid uuid;
begin
  if not public.open_market() then raise exception 'Buyer inspections are not open yet.'; end if;
  select * into l from public.listings where id = p_listing for update;
  if l is null or l.status not in ('live','reserved') then raise exception 'This car is not on sale.'; end if;
  if public.is_listing_seller(l) then raise exception 'This is your car.'; end if;
  select * into r from public.reviews where id = l.current_review_id;
  if r.id is not null and r.valid_until >= current_date then raise exception 'This car already has a Saaz inspection. Read the report on its page.'; end if;
  if exists (select 1 from public.reviews where listing_id = l.id and scope = 'general' and status in ('requested','draft')) then
    raise exception 'A Saaz inspection of this car is already on its way. The report shows on its page when it is issued.'; end if;
  did := public.new_inspection_id();
  insert into public.reviews (listing_id, vehicle_id, scope, status, doc_no, requested_at, requested_by)
  values (l.id, l.vehicle_id, 'general', 'requested', did, now(), u) returning id into rid;
  perform public.audit('buyer', 'review', rid::text, 'inspection requested by a buyer', jsonb_build_object('inspection_id', did, 'listing', l.ref));
  perform public.notify(x, 'buyer_inspection_requested', 'A buyer asked for a Saaz inspection of ' || l.ref ||
    '. A certified garage will message you inside Saaz to book it. The buyer pays the garage; your car stays on sale.', '#/my/cars/' || l.id, '{app,sms}')
    from public.seller_side_users(l) x;
  perform public.put_next_in_play(l.id);
  return jsonb_build_object('inspection_id', did);
end $$;
revoke execute on function public.buyer_request_inspection(uuid) from public, anon;
grant execute on function public.buyer_request_inspection(uuid) to authenticated;

-- Every Saaz report of a car (the same VIN across its listings), newest first, for the car's public page.
-- Only issued reports (current or replaced); who asked for them is never shown.
create or replace function public.car_history(p_listing uuid) returns setof jsonb language plpgsql stable security definer set search_path = public as $$
declare l public.listings;
begin
  select * into l from public.listings where id = p_listing;
  if l is null or not (l.status in ('live','reserved','sold') or public.is_admin() or public.is_listing_seller(l)) then return; end if;
  return query
  select jsonb_build_object('doc_no', r.doc_no, 'scope_name', s.name, 'verdict', r.verdict, 'score', r.score, 'issued_at', r.issued_at,
    'valid_until', r.valid_until, 'garage', r.garage_name, 'verify_code', r.verify_code, 'current', r.id = l.current_review_id,
    'replaced', r.status = 'superseded', 'odometer', r.odometer, 'odometer_flag', r.odometer_flag, 'saaz_stance', public.saaz_stance(r.id))
  from public.reviews r join public.inspection_scopes s on s.key = r.scope
  where r.vehicle_id = l.vehicle_id and r.status in ('issued','superseded')
  order by r.issued_at desc;
end $$;
revoke execute on function public.car_history(uuid) from public;
grant execute on function public.car_history(uuid) to anon, authenticated;

-- Tell the API about the changed functions now (Supabase usually does this by itself)
notify pgrst, 'reload schema';
