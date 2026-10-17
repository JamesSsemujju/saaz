-- Saaz marketplace, part 3 of 4: Saaz reviews, admin decisions, offers and deals, demand, admin controls.

-- ===== Saaz reviews =====
-- 12 checks. Safety items: brakes, steering, odometer, vin. Weights: safety 10, others 6 (assumption).
create or replace function public.review_keys() returns text[] language sql immutable as $$
  select array['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin'] $$;
create or replace function public.panel_keys() returns text[] language sql immutable as $$
  select array['front_bumper','bonnet','roof','boot','rear_bumper','left_front','left_rear','right_front','right_rear'] $$;

create or replace function public.start_review(p_listing uuid) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid := public.my_garage_id(); l public.listings; rid uuid; other text;
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  select * into l from public.listings where id = p_listing;
  if not exists (select 1 from public.conversations where listing_id = p_listing and garage_id = gid and status = 'agreed') then
    raise exception 'This car is not booked with your garage.'; end if;
  select p.name into other from public.reviews r join public.profiles p on p.id = r.member_id
    where r.listing_id = p_listing and r.garage_id = gid and r.status = 'draft' and r.member_id <> u;
  if other is not null then raise exception 'In progress: % is writing this review.', other; end if;
  select id into rid from public.reviews where listing_id = p_listing and member_id = u and status = 'draft';
  if rid is null then
    insert into public.reviews (listing_id, vehicle_id, garage_id, member_id) values (p_listing, l.vehicle_id, gid, u) returning id into rid;
    perform public.audit('garage','review',rid::text,'review started', jsonb_build_object('listing',l.ref));
  end if;
  return rid;
end $$;

create or replace function public.save_review(p_review uuid, p jsonb) returns void language plpgsql security definer set search_path = public as $$
declare r public.reviews;
begin
  perform public.require_user();
  select * into r from public.reviews where id = p_review;
  if r.member_id <> auth.uid() or r.status <> 'draft' then raise exception 'Only the member who started this draft can change it.'; end if;
  if public.my_garage_id() is distinct from r.garage_id then raise exception 'Your garage access has ended.'; end if;
  update public.reviews set checks = coalesce(p->'checks','{}'::jsonb), panels = coalesce(p->'panels','{}'::jsonb),
    odometer = nullif(p->>'odometer','')::int, notes = coalesce(p->>'notes',''), in_person = coalesce((p->>'in_person')::boolean,false),
    updated_at = now()
  where id = p_review;
end $$;

create or replace function public.discard_review(p_review uuid) returns void language plpgsql security definer set search_path = public as $$
declare r public.reviews;
begin
  select * into r from public.reviews where id = p_review;
  if r.member_id <> auth.uid() or r.status <> 'draft' then raise exception 'Only the member who started this draft can discard it.'; end if;
  delete from public.reviews where id = p_review;
  perform public.audit('garage','review',p_review::text,'draft discarded');
end $$;

-- The text the fingerprint covers. Verify recomputes it to catch altered records.
create or replace function public.review_canonical(r public.reviews) returns text language sql stable security definer set search_path = public as $$
  select concat_ws('|', r.doc_no, r.version, v.vin, l.ref, r.checks::text, r.panels::text, r.odometer, r.verdict, r.score,
    r.member_id, r.garage_id, to_char(r.issued_at at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'), r.valid_until)
  from public.vehicles v, public.listings l where v.id = r.vehicle_id and l.id = r.listing_id
$$;

create or replace function public.issue_review(p_review uuid) returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); r public.reviews; l public.listings; k text; val text; s numeric := 0; maxs numeric := 0;
  safety text[] := array['brakes','steering','odometer','vin']; v_verdict text := 'pass'; panel_pen int := 0; v_score int;
  prev_top int; v_flag text; ver int; code text; fp text; pr public.profiles; m public.garage_members; g public.garages;
  auto_live boolean; v_trusted boolean;
begin
  select * into r from public.reviews where id = p_review for update;
  if r.member_id <> u or r.status <> 'draft' then raise exception 'Only the member who started this draft can issue it.'; end if;
  if public.my_garage_id() is distinct from r.garage_id then raise exception 'Your garage access has ended.'; end if;
  if not exists (select 1 from public.conversations where listing_id = r.listing_id and garage_id = r.garage_id and status = 'agreed') then
    raise exception 'This car is no longer booked with your garage.'; end if;
  if not r.in_person then raise exception 'Confirm the car was reviewed in person and the VIN checked.'; end if;
  if r.odometer is null then raise exception 'Enter the odometer reading.'; end if;
  foreach k in array public.review_keys() loop
    val := r.checks->>k;
    if val not in ('pass','advise','fail') or val is null then raise exception 'Mark every check: % is missing.', k; end if;
    maxs := maxs + case when k = any(safety) then 10 else 6 end;
    s := s + (case when k = any(safety) then 10 else 6 end) * (case val when 'pass' then 1 when 'advise' then 0.5 else 0 end);
    if val = 'fail' and k = any(safety) then v_verdict := 'fail';
    elsif val <> 'pass' and v_verdict = 'pass' then v_verdict := 'conditional'; end if;
  end loop;
  if v_verdict <> 'pass' and length(trim(r.notes)) < 10 then raise exception 'Add notes: something is not a Pass.'; end if;
  foreach k in array public.panel_keys() loop
    panel_pen := panel_pen + case coalesce(r.panels->>k,'none') when 'scratch' then 1 when 'dent' then 2 when 'repaint' then 2 when 'damage' then 4 else 0 end;
  end loop;
  v_score := greatest(0, least(100, round(s / maxs * 100) - panel_pen));
  select * into l from public.listings where id = r.listing_id;
  select max(km) into prev_top from public.odometer_readings where vehicle_id = r.vehicle_id;
  if prev_top is not null and r.odometer < prev_top then v_flag := 'Lower than an earlier Saaz reading (' || prev_top || ' km)';
  elsif abs(r.odometer - l.mileage) > l.mileage * (public.setting('mileage_flag_pct'))::text::numeric / 100 then
    v_flag := 'Differs by more than ' || (public.setting('mileage_flag_pct')) || '% from the seller''s ' || l.mileage || ' km'; end if;
  select coalesce(max(version),0) + 1 into ver from public.reviews where listing_id = r.listing_id and status <> 'draft';
  select * into pr from public.profiles where id = u;
  select * into m from public.garage_members where user_id = u and status <> 'removed';
  select * into g from public.garages where id = r.garage_id;
  update public.reviews set status = 'superseded' where listing_id = r.listing_id and status = 'issued';
  update public.reviews set status = 'issued', verdict = v_verdict, score = v_score,
    doc_no = 'SZR-' || to_char(now(),'YYYY') || '-' || lpad(nextval('public.review_doc_seq')::text, 6, '0'),
    version = ver, odometer_flag = v_flag, issued_at = date_trunc('second', now()),
    valid_until = current_date + (public.setting('review_valid_days'))::text::int,
    member_name = pr.name, member_role = m.role, garage_name = g.name, garage_certified_at = g.certified_at, updated_at = now()
  where id = p_review returning * into r;
  fp := encode(sha256(convert_to(public.review_canonical(r), 'UTF8')), 'hex');
  code := upper(substr(fp, 1, 4) || '-' || substr(fp, 5, 4) || '-' || substr(fp, 9, 4));
  update public.reviews set fingerprint = fp, verify_code = code where id = p_review;
  insert into public.odometer_readings (vehicle_id, km, source, review_id, flagged) values (r.vehicle_id, r.odometer, 'review', r.id, v_flag);
  select p2.trusted into v_trusted from public.profiles p2 where p2.id = l.seller_id;
  auto_live := (l.saaz_owned or coalesce(v_trusted,false)) and r.verdict = 'pass' and v_flag is null;
  update public.listings set current_review_id = r.id, updated_at = now(),
    status = case when auto_live then 'live' else 'awaiting_approval' end,
    live_at = case when auto_live then now() else live_at end
  where id = l.id;
  update public.conversations set status = 'closed', closed_at = now() where listing_id = l.id and garage_id = r.garage_id and status = 'agreed';
  perform public.audit('garage','review',r.id::text,'issued', jsonb_build_object('doc_no',r.doc_no,'verdict',r.verdict,'score',r.score,'odometer',r.odometer,'flag',v_flag));
  perform public.notify(x, 'review_issued', 'Your Saaz review for ' || l.ref || ' is issued (' || initcap(r.verdict) || ', ' || r.score || '/100). ' ||
    case when auto_live then 'Your car is live.' else 'Saaz will check it within ' || (public.setting('approval_response')#>>'{}') || '.' end,
    '#/my/cars/' || l.id, '{app,email,sms}') from public.seller_side_users(l) x;
  if not auto_live then perform public.notify_admins('review_issued','Review issued for ' || l.ref || ': waiting for approval.','#/admin/cars/' || l.id); end if;
  return jsonb_build_object('doc_no',r.doc_no,'verify_code',code,'verdict',r.verdict,'score',r.score,'live',auto_live);
end $$;

-- Public verify page: Genuine or not, what the report should say, and whether the stored record still matches its fingerprint.
create or replace function public.verify_review(p_code text) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare r public.reviews; v public.vehicles; l public.listings;
begin
  select * into r from public.reviews where verify_code = upper(trim(p_code));
  if r is null then return jsonb_build_object('genuine',false,'message','No Saaz review has this code.'); end if;
  select * into v from public.vehicles where id = r.vehicle_id;
  select * into l from public.listings where id = r.listing_id;
  return jsonb_build_object('genuine', true,
    'intact', encode(sha256(convert_to(public.review_canonical(r),'UTF8')),'hex') = r.fingerprint,
    'status', case when r.status = 'issued' and r.valid_until < current_date then 'expired' else r.status end,
    'doc_no', r.doc_no, 'version', r.version, 'vin', v.vin, 'make', l.make, 'model', l.model, 'year', l.year, 'plate', l.plate,
    'verdict', r.verdict, 'score', r.score, 'odometer', r.odometer, 'issued_at', r.issued_at, 'valid_until', r.valid_until,
    'garage', r.garage_name, 'member', r.member_name, 'fingerprint', r.fingerprint);
end $$;

-- ===== Admin decisions on listings =====
create or replace function public.admin_decide_listing(p_listing uuid, p_decision text, p_note text default null, p_new_review boolean default false)
returns void language plpgsql security definer set search_path = public as $$
declare l public.listings; r public.reviews;
begin
  perform public.require_admin();
  select * into l from public.listings where id = p_listing;
  select * into r from public.reviews where id = l.current_review_id;
  if p_decision in ('changes','reject','unlist') and coalesce(trim(p_note),'') = '' then raise exception 'A note to the seller is required.'; end if;
  if p_decision = 'approve' then
    if l.status <> 'awaiting_approval' then raise exception 'Nothing to approve.'; end if;
    if r.verdict = 'fail' then raise exception 'A safety Fail cannot be approved.'; end if;
    update public.listings set status = 'live', live_at = now(), admin_note = null, updated_at = now() where id = l.id;
  elsif p_decision = 'changes' then
    update public.listings set status = 'changes_requested', admin_note = p_note, updated_at = now() where id = l.id;
    if p_new_review then update public.reviews set status = 'superseded' where id = r.id; update public.listings set current_review_id = null where id = l.id; end if;
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
end $$;

create or replace function public.admin_void_review(p_review uuid, p_reason text) returns void language plpgsql security definer set search_path = public as $$
declare r public.reviews; l public.listings;
begin
  perform public.require_admin();
  if coalesce(trim(p_reason),'') = '' then raise exception 'A reason is required.'; end if;
  select * into r from public.reviews where id = p_review;
  if r.status <> 'issued' then raise exception 'Only an issued review can be voided.'; end if;
  update public.reviews set status = 'void', void_reason = p_reason where id = p_review;
  select * into l from public.listings where id = r.listing_id;
  update public.deals set status = 'closed', updated_at = now() where listing_id = l.id and status in ('negotiating','on_hold');
  update public.listings set status = 'awaiting_review', current_review_id = null, updated_at = now() where id = l.id and status not in ('sold','reserved','withdrawn');
  perform public.notify_garage(r.garage_id,'review_void','Saaz voided review ' || r.doc_no || ': ' || p_reason,'#/garage');
  perform public.notify(x,'review_void','The Saaz review for ' || l.ref || ' was voided. Saaz is arranging a new one.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
  perform public.audit('admin','review',p_review::text,'voided', jsonb_build_object('reason',p_reason));
  perform public.put_next_in_play(l.id);
end $$;

-- ===== Offers and deals =====
-- Which of the seller's rules an amount breaks, or null. Never reveals the minimum.
create or replace function public.rule_broken(l public.listings, p_amount bigint, p_trade_in boolean) returns text language sql stable as $$
  select case
    when l.rule_no_trade_in and p_trade_in then 'The seller does not accept offers with a trade-in.'
    when l.rule_min_pct is not null and p_amount < l.price * l.rule_min_pct / 100 then 'The offer is below the seller''s minimum.'
    when l.rule_min_amount is not null and p_amount < l.rule_min_amount then 'The offer is below the seller''s minimum.'
    else null end
$$;

create or replace function public.make_offer(p_listing uuid, p_amount bigint, p_trade_in boolean, p_message text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); l public.listings; pr public.profiles; broken text; did uuid;
begin
  select * into l from public.listings where id = p_listing;
  select * into pr from public.profiles where id = u;
  if l.status <> 'live' then raise exception 'This car is not open for offers.'; end if;
  if l.seller_id = u then raise exception 'You cannot offer on your own car.'; end if;
  if (public.setting('require_phone_verified'))::text::boolean and not pr.phone_verified then raise exception 'Verify your phone number before making offers.'; end if;
  if p_amount < l.price * (public.setting('min_offer_pct'))::text::int / 100 then
    raise exception 'Offers must be at least % percent of the asking price.', (public.setting('min_offer_pct')); end if;
  if exists (select 1 from public.deals where listing_id = p_listing and buyer_id = u and status in ('negotiating','agreed','on_hold')) then
    raise exception 'You already have an open offer on this car.'; end if;
  broken := public.rule_broken(l, p_amount, coalesce(p_trade_in,false));
  insert into public.deals (listing_id, buyer_id, amount, trade_in, last_by, buyer_ok, flag, status)
  values (p_listing, u, p_amount, coalesce(p_trade_in,false), 'buyer', true,
    case when broken is not null and not l.auto_reject then broken end,
    case when broken is not null and l.auto_reject then 'auto_rejected' else 'negotiating' end)
  returning id into did;
  insert into public.deal_events (deal_id, by_side, kind, amount, message) values (did, 'buyer', 'offer', p_amount, nullif(trim(p_message),''));
  if broken is not null and l.auto_reject then
    insert into public.deal_events (deal_id, by_side, kind) values (did, 'system', 'auto_reject');
    perform public.audit('system','deal',did::text,'auto-rejected', jsonb_build_object('listing',l.ref,'amount',p_amount,'rule',broken));
    perform public.notify(u,'offer_auto_rejected', broken || ' You can make another offer.','#/car/' || l.ref);
    return jsonb_build_object('deal',did,'status','auto_rejected','message',broken || ' You can make another offer.');
  end if;
  perform public.audit('buyer','deal',did::text,'offer made', jsonb_build_object('listing',l.ref,'amount',p_amount,'flag',broken));
  perform public.notify(x,'offer_received', 'New offer on ' || l.ref || ': ' || l.currency || ' ' || to_char(p_amount,'FM999,999,999,999') ||
    case when broken is not null then ' (breaks your offer rules)' else '' end, '#/deals/' || did, '{app,sms}') from public.seller_side_users(l) x;
  return jsonb_build_object('deal',did,'status','negotiating');
end $$;

create or replace function public.deal_side(d public.deals) returns text language sql stable security definer set search_path = public as $$
  select case when d.buyer_id = auth.uid() then 'buyer'
    when exists (select 1 from public.listings l where l.id = d.listing_id and public.is_listing_seller(l)) then 'seller'
    when public.is_admin() then 'admin' end
$$;

create or replace function public.deal_action(p_deal uuid, p_action text, p_amount bigint default null, p_message text default null, p_trade_in boolean default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); d public.deals; l public.listings; side text; broken text; other_ok boolean;
begin
  select * into d from public.deals where id = p_deal for update;
  select * into l from public.listings where id = d.listing_id;
  side := public.deal_side(d);
  if side is null then raise exception 'Not your deal.'; end if;
  if p_action = 'counter' then
    if d.status <> 'negotiating' or side = 'admin' then raise exception 'You cannot counter now.'; end if;
    if p_amount is null or p_amount <= 0 then raise exception 'Enter an amount.'; end if;
    broken := case when side = 'buyer' and l.rule_on_counters then public.rule_broken(l, p_amount, coalesce(p_trade_in, d.trade_in)) end;
    if broken is not null and l.auto_reject then
      insert into public.deal_events (deal_id, by_side, kind, amount) values (p_deal, 'system', 'auto_reject', p_amount);
      perform public.audit('system','deal',p_deal::text,'counter auto-rejected', jsonb_build_object('amount',p_amount,'rule',broken));
      return jsonb_build_object('status','negotiating','message',broken || ' Your counter was not sent.');
    end if;
    update public.deals set amount = p_amount, trade_in = coalesce(p_trade_in, trade_in), last_by = side,
      buyer_ok = (side = 'buyer'), seller_ok = (side = 'seller'), flag = case when side = 'buyer' then broken else flag end, updated_at = now()
    where id = p_deal;
    insert into public.deal_events (deal_id, by_side, kind, amount, message) values (p_deal, side, 'counter', p_amount, nullif(trim(p_message),''));
  elsif p_action = 'accept' then
    if d.status <> 'negotiating' then raise exception 'Nothing to accept now.'; end if;
    if side = 'admin' then raise exception 'Admins propose a price or mark agreed instead.'; end if;
    update public.deals set buyer_ok = buyer_ok or side = 'buyer', seller_ok = seller_ok or side = 'seller', updated_at = now()
      where id = p_deal returning * into d;
    insert into public.deal_events (deal_id, by_side, kind, amount) values (p_deal, side, 'accept', d.amount);
    if d.buyer_ok and d.seller_ok then perform public.deal_agree(p_deal, null); end if;
  elsif p_action = 'reject' then
    if side <> 'seller' or d.status <> 'negotiating' then raise exception 'Only the seller can reject an open offer.'; end if;
    update public.deals set status = 'rejected', updated_at = now() where id = p_deal;
    insert into public.deal_events (deal_id, by_side, kind, message) values (p_deal, 'seller', 'reject', nullif(trim(p_message),''));
    perform public.notify(d.buyer_id,'offer_rejected','Your offer on ' || l.ref || ' was declined.','#/deals/' || p_deal);
  elsif p_action = 'withdraw' then
    if side <> 'buyer' or d.status <> 'negotiating' then raise exception 'You can withdraw only an open offer of yours.'; end if;
    update public.deals set status = 'withdrawn', updated_at = now() where id = p_deal;
    insert into public.deal_events (deal_id, by_side, kind) values (p_deal, 'buyer', 'withdraw');
  elsif p_action = 'propose' then
    if side <> 'admin' or d.status <> 'negotiating' then raise exception 'Admins only, on an open deal.'; end if;
    update public.deals set amount = p_amount, last_by = 'admin', buyer_ok = false, seller_ok = false, updated_at = now() where id = p_deal;
    insert into public.deal_events (deal_id, by_side, kind, amount, message) values (p_deal, 'admin', 'propose', p_amount, p_message);
  elsif p_action = 'mark_agreed' then
    if side <> 'admin' or d.status <> 'negotiating' then raise exception 'Admins only, on an open deal.'; end if;
    if coalesce(trim(p_message),'') = '' then raise exception 'Note how both sides confirmed.'; end if;
    perform public.deal_agree(p_deal, p_message);
  elsif p_action = 'complete' then
    perform public.require_admin();
    if d.status <> 'agreed' then raise exception 'Only an agreed deal can be completed.'; end if;
    update public.deals set status = 'completed', updated_at = now() where id = p_deal;
    update public.deals set status = 'closed', updated_at = now() where listing_id = l.id and status = 'on_hold';
    update public.listings set status = 'sold', sold_at = now(), updated_at = now() where id = l.id;
    update public.vehicles set saaz_owned = false where id = l.vehicle_id;
    insert into public.odometer_readings (vehicle_id, km, source)
      select l.vehicle_id, greatest(l.mileage, coalesce(max(km),0)), 'sale' from public.odometer_readings where vehicle_id = l.vehicle_id;
    insert into public.deal_events (deal_id, by_side, kind, amount) values (p_deal, 'admin', 'completed', d.amount);
    perform public.notify(d.buyer_id,'sale_completed','Sale completed: ' || l.ref || '.','#/deals/' || p_deal,'{app,email,sms}');
    perform public.notify(x,'sale_completed','Sale completed: ' || l.ref || '.','#/deals/' || p_deal,'{app,email,sms}') from public.seller_side_users(l) x;
  elsif p_action = 'cancel' then
    perform public.require_admin();
    if d.status not in ('negotiating','agreed') then raise exception 'This deal cannot be cancelled.'; end if;
    update public.deals set status = 'cancelled', updated_at = now() where id = p_deal;
    if d.status = 'agreed' then
      update public.listings set status = 'live', updated_at = now() where id = l.id;
      update public.deals set status = 'negotiating', updated_at = now() where listing_id = l.id and status = 'on_hold';
    end if;
    insert into public.deal_events (deal_id, by_side, kind, message) values (p_deal, 'admin', 'cancelled', p_message);
  else raise exception 'Unknown action.'; end if;
  perform public.audit(side,'deal',p_deal::text,p_action, jsonb_build_object('amount',p_amount));
  if p_action in ('counter','propose') then
    perform public.notify(t, 'deal_' || p_action,
      'New figure on ' || l.ref || ': ' || l.currency || ' ' || to_char(p_amount,'FM999,999,999,999'), '#/deals/' || p_deal)
      from (select x t from public.seller_side_users(l) x where side in ('buyer','admin')
            union select d.buyer_id where side in ('seller','admin')) q;
  end if;
  select * into d from public.deals where id = p_deal;
  return jsonb_build_object('status', d.status);
end $$;

create or replace function public.deal_agree(p_deal uuid, p_note text) returns void language plpgsql security definer set search_path = public as $$
declare d public.deals; l public.listings;
begin
  select * into d from public.deals where id = p_deal;
  select * into l from public.listings where id = d.listing_id;
  update public.deals set status = 'agreed', buyer_ok = true, seller_ok = true, agreed_note = p_note, updated_at = now() where id = p_deal;
  update public.deals set status = 'on_hold', updated_at = now() where listing_id = l.id and id <> p_deal and status = 'negotiating';
  update public.listings set status = 'reserved', updated_at = now() where id = l.id;
  insert into public.deal_events (deal_id, by_side, kind, amount, message) values (p_deal, 'system', 'agreed', d.amount, p_note);
  perform public.notify(d.buyer_id,'deal_agreed','Deal agreed on ' || l.ref || '. You can now see the seller''s contact details.','#/deals/' || p_deal,'{app,email,sms}');
  perform public.notify(x,'deal_agreed','Deal agreed on ' || l.ref || '. You can now see the buyer''s contact details.','#/deals/' || p_deal,'{app,email,sms}') from public.seller_side_users(l) x;
  perform public.notify_admins('deal_agreed','Deal agreed on ' || l.ref || ': confirm the handover to complete it.','#/admin/deals/' || p_deal);
end $$;

-- Contacts are shared only after agreement
create or replace function public.deal_contacts(p_deal uuid) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare d public.deals; l public.listings; side text; who public.profiles;
begin
  select * into d from public.deals where id = p_deal;
  side := public.deal_side(d);
  if side is null then raise exception 'Not your deal.'; end if;
  if d.status not in ('agreed','completed') then return null; end if;
  select * into l from public.listings where id = d.listing_id;
  if side = 'buyer' then
    if l.saaz_owned then return jsonb_build_object('name','Saaz','note','Saaz will contact you here.'); end if;
    select * into who from public.profiles where id = l.seller_id;
  else select * into who from public.profiles where id = d.buyer_id; end if;
  return jsonb_build_object('name',who.name,'mobile',who.mobile,'email',who.email);
end $$;

-- ===== Demand =====
create or replace function public.record_view(p_listing uuid, p_device text) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings; viewer text := coalesce(auth.uid()::text, nullif(left(p_device,64),''));
begin
  select * into l from public.listings where id = p_listing;
  if l is null or viewer is null or l.status not in ('live','reserved') then return; end if;
  if l.seller_id = auth.uid() or (l.saaz_owned and public.is_admin()) then return; end if;
  insert into public.listing_views (listing_id, viewer) values (p_listing, viewer) on conflict do nothing;
end $$;

create or replace function public.toggle_save(p_listing uuid) returns boolean language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user();
begin
  if exists (select 1 from public.saves where listing_id = p_listing and user_id = u) then
    delete from public.saves where listing_id = p_listing and user_id = u; return false;
  end if;
  insert into public.saves (listing_id, user_id) values (p_listing, u); return true;
end $$;

-- Public counts for a car page; full stats for its seller and admins.
create or replace function public.listing_stats(p_listing uuid) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare l public.listings; full_access boolean; days numeric; res jsonb;
begin
  select * into l from public.listings where id = p_listing;
  if l is null then return null; end if;
  full_access := public.is_listing_seller(l) or public.is_admin();
  res := jsonb_build_object(
    'views_7d', (select count(*) from public.listing_views where listing_id = l.id and day > current_date - 7),
    'saves', (select count(*) from public.saves where listing_id = l.id),
    'offers', (select count(*) from public.deals where listing_id = l.id));
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
end $$;

create or replace function public.model_sales(p_make text, p_model text, p_country text) returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'sold_90d', count(*),
    'median_days', percentile_cont(0.5) within group (order by extract(epoch from (l.sold_at - l.live_at)) / 86400),
    'typical_price', percentile_cont(0.5) within group (order by d.amount))
  from public.listings l join public.deals d on d.listing_id = l.id and d.status = 'completed'
  where l.make = p_make and l.model = p_model and l.country = p_country and l.status = 'sold' and l.sold_at > now() - interval '90 days'
$$;

-- What's selling: one row per make and model in a country
create or replace function public.whats_selling(p_country text) returns table (
  make text, model text, selling_fast boolean, hint_only boolean, median_days numeric, sold_90d bigint, live_now bigint,
  views_per_day numeric, offers_per_listing numeric, typical_price numeric, currency text)
language sql stable security definer set search_path = public as $$
  with m as (
    select l.make, l.model,
      count(*) filter (where l.status = 'sold' and l.sold_at > now() - interval '90 days') sold,
      percentile_cont(0.5) within group (order by extract(epoch from (l.sold_at - l.live_at)) / 86400)
        filter (where l.status = 'sold' and l.sold_at > now() - interval '90 days') med,
      count(*) filter (where l.status in ('live','reserved')) live_now,
      count(*) filter (where l.live_at is not null) listed,
      avg((select count(*) from public.listing_views v where v.listing_id = l.id) / greatest(1, extract(epoch from (coalesce(l.sold_at, now()) - l.live_at)) / 86400))
        filter (where l.live_at is not null) vpd,
      avg((select count(*) from public.deals d where d.listing_id = l.id)) filter (where l.live_at is not null) opl,
      percentile_cont(0.5) within group (order by (select d.amount from public.deals d where d.listing_id = l.id and d.status = 'completed' limit 1))
        filter (where l.status = 'sold' and l.sold_at > now() - interval '90 days') price
    from public.listings l where l.country = p_country and l.live_at is not null
    group by l.make, l.model)
  select make, model,
    sold >= (public.setting('selling_fast_min_sold'))::text::int and med <= (public.setting('selling_fast_max_days'))::text::numeric,
    listed < (public.setting('trend_min_listings'))::text::int,
    round(med::numeric, 1), sold, live_now, round(vpd, 1), round(opl, 1), round(price::numeric), case when p_country = 'KE' then 'KES' else 'UGX' end
  from m order by sold desc, med nulls last
$$;

-- ===== Admin controls =====
create or replace function public.admin_set_user(p_user uuid, p_field text, p_value boolean, p_note text default null) returns void
language plpgsql security definer set search_path = public as $$
declare a uuid := public.require_admin(); before boolean;
begin
  if p_user = a then raise exception 'You cannot change your own access.'; end if;
  if p_field = 'trusted' then select trusted into before from public.profiles where id = p_user; update public.profiles set trusted = p_value where id = p_user;
  elsif p_field = 'suspended' then
    select suspended into before from public.profiles where id = p_user;
    update public.profiles set suspended = p_value where id = p_user;
    if p_value then update public.listings set status = 'withdrawn', admin_note = 'Account suspended', updated_at = now()
      where seller_id = p_user and status in ('live','re_review_due','awaiting_approval','awaiting_review','review_booked'); end if;
  elsif p_field = 'phone_verified' then select phone_verified into before from public.profiles where id = p_user; update public.profiles set phone_verified = p_value where id = p_user;
  elsif p_field = 'admin' then
    before := exists (select 1 from public.admins where user_id = p_user);
    if p_value then insert into public.admins (user_id, name) select id, name from public.profiles where id = p_user on conflict do nothing;
    else delete from public.admins where user_id = p_user; end if;
  else raise exception 'Unknown field.'; end if;
  perform public.audit('admin','account',p_user::text,p_field, jsonb_build_object('before',before,'after',p_value,'note',p_note));
end $$;

create or replace function public.admin_set_setting(p_key text, p_value jsonb) returns void language plpgsql security definer set search_path = public as $$
declare before jsonb;
begin
  perform public.require_admin();
  select value into before from public.settings where key = p_key;
  if before is null then raise exception 'Unknown setting.'; end if;
  update public.settings set value = p_value, updated_at = now() where key = p_key;
  perform public.audit('admin','setting',p_key,'changed', jsonb_build_object('before',before,'after',p_value));
end $$;

-- Saaz imports: admin records an import so its details fill in and lock when it is listed
create or replace function public.admin_add_import(p jsonb) returns uuid language plpgsql security definer set search_path = public as $$
declare v_vin text := upper(regexp_replace(coalesce(p->>'vin',''),'\s','','g')); vid uuid;
begin
  perform public.require_admin();
  perform public.check_vin(v_vin);
  insert into public.vehicles (vin, make, model, year, fuel, gearbox, body, engine, source, import_mileage, saaz_owned)
  values (v_vin, p->>'make', p->>'model', (p->>'year')::int, p->>'fuel', p->>'gearbox', p->>'body', p->>'engine', 'saaz_import',
          (p->>'import_mileage')::int, coalesce((p->>'saaz_owned')::boolean, true))
  returning id into vid;
  insert into public.odometer_readings (vehicle_id, km, source) values (vid, (p->>'import_mileage')::int, 'import');
  perform public.audit('admin','vehicle',vid::text,'import recorded', jsonb_build_object('after',p));
  return vid;
end $$;

-- A seller's view of their car's history: admin names shown as "Our team", no message text
create or replace function public.listing_history(p_listing uuid) returns table (at timestamptz, who text, action text)
language sql stable security definer set search_path = public as $$
  select a.at, case when a.actor_role = 'admin' then 'Our team' when a.actor_role = 'system' then 'Saaz'
    else coalesce((select name from public.profiles where id = a.actor_id), a.actor_role) end, a.action
  from public.audit_log a, public.listings l
  where l.id = p_listing and (public.is_listing_seller(l) or public.is_admin())
    and ((a.entity = 'listing' and a.entity_id = l.id::text)
      or (a.entity = 'conversation' and a.entity_id in (select id::text from public.conversations where listing_id = l.id))
      or (a.entity = 'review' and a.entity_id in (select id::text from public.reviews where listing_id = l.id)))
  order by a.at
$$;

-- Admin: conversation counts only, never message text (except Saaz-owned cars, where admin is the seller)
create or replace function public.admin_conversation_counts() returns table (listing_ref text, garage text, status text, messages bigint, opened_at timestamptz)
language sql stable security definer set search_path = public as $$
  select l.ref, g.name, c.status, (select count(*) from public.messages m where m.conversation_id = c.id), c.opened_at
  from public.conversations c join public.listings l on l.id = c.listing_id join public.garages g on g.id = c.garage_id
  where public.is_admin() order by c.opened_at desc
$$;

-- ===== Read helpers for the website =====
-- Public browse: live and reserved cars with their public demand counts, in one call
create or replace function public.browse_listings(p_country text default null) returns setof jsonb language sql stable security definer set search_path = public as $$
  select to_jsonb(l) - 'logbook_name_matches' - 'owner_authorised' - 'rule_min_pct' - 'rule_min_amount' - 'admin_note' - 'seller_id'
    || jsonb_build_object(
      'views_7d', (select count(*) from public.listing_views v where v.listing_id = l.id and v.day > current_date - 7),
      'saves', (select count(*) from public.saves s where s.listing_id = l.id),
      'offers', (select count(*) from public.deals d where d.listing_id = l.id),
      'review', (select jsonb_build_object('verdict',r.verdict,'score',r.score,'verify_code',r.verify_code,'valid_until',r.valid_until,'garage',r.garage_name)
                 from public.reviews r where r.id = l.current_review_id),
      'saved', exists (select 1 from public.saves s where s.listing_id = l.id and s.user_id = auth.uid()))
  from public.listings l
  where l.status in ('live','reserved') and (p_country is null or l.country = p_country)
  order by l.live_at desc
$$;

-- A seller's cars (or, for admins, Saaz-owned cars) with demand counts and the garage in play
create or replace function public.my_listings(p_saaz boolean default false) returns setof jsonb language plpgsql stable security definer set search_path = public as $$
begin
  if p_saaz then perform public.require_admin(); else perform public.require_user(); end if;
  return query
  select to_jsonb(l) || jsonb_build_object(
      'views_7d', (select count(*) from public.listing_views v where v.listing_id = l.id and v.day > current_date - 7),
      'saves', (select count(*) from public.saves s where s.listing_id = l.id),
      'offers', (select count(*) from public.deals d where d.listing_id = l.id),
      'open_offers', (select count(*) from public.deals d where d.listing_id = l.id and d.status = 'negotiating'),
      'conversation', (select jsonb_build_object('id',c.id,'status',c.status,'garage',g.name,'deadline',c.deadline,'review_date',c.review_date,
                         'garage_messaged', c.garage_first_message_at is not null)
                       from public.conversations c join public.garages g on g.id = c.garage_id
                       where c.listing_id = l.id and c.status in ('in_play','agreed') limit 1),
      'review', (select jsonb_build_object('verdict',r.verdict,'score',r.score,'doc_no',r.doc_no,'verify_code',r.verify_code,'valid_until',r.valid_until,'odometer_flag',r.odometer_flag)
                 from public.reviews r where r.id = l.current_review_id))
  from public.listings l
  where (p_saaz and l.saaz_owned) or (not p_saaz and l.seller_id = auth.uid())
  order by l.updated_at desc;
end $$;

-- Everything the report document shows, by verification code. Public.
create or replace function public.review_document(p_code text) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare r public.reviews; l public.listings; v public.vehicles;
begin
  select * into r from public.reviews where verify_code = upper(trim(p_code)) and status <> 'draft';
  if r is null then return null; end if;
  select * into l from public.listings where id = r.listing_id;
  select * into v from public.vehicles where id = r.vehicle_id;
  return jsonb_build_object('review', to_jsonb(r) - 'notes' || jsonb_build_object('notes', r.notes),
    'status', case when r.status = 'issued' and r.valid_until < current_date then 'expired' else r.status end,
    'intact', encode(sha256(convert_to(public.review_canonical(r),'UTF8')),'hex') = r.fingerprint,
    'listing', jsonb_build_object('ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'plate',l.plate,'colour',l.colour,'engine',l.engine,
       'fuel',l.fuel,'gearbox',l.gearbox,'body',l.body,'country',l.country,'mileage',l.mileage),
    'vehicle', jsonb_build_object('vin',v.vin,'source',v.source,'first_record_date',v.first_record_date,'import_mileage',v.import_mileage),
    'odometer', (select jsonb_agg(jsonb_build_object('km',o.km,'source',o.source,'at',o.recorded_at,'flagged',o.flagged) order by o.recorded_at)
                 from public.odometer_readings o where o.vehicle_id = v.id));
end $$;

-- A garage's jobs: cars in play (offered to you) and booked jobs
create or replace function public.garage_jobs() returns setof jsonb language plpgsql stable security definer set search_path = public as $$
declare gid uuid := public.my_garage_id();
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  return query
  select jsonb_build_object('conversation', to_jsonb(c), 'listing',
      jsonb_build_object('id',l.id,'ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'region',l.region,'mileage',l.mileage,'status',l.status,'photos',l.photos),
      'draft', (select jsonb_build_object('id',r.id,'member',p.name,'mine',r.member_id = auth.uid())
                from public.reviews r join public.profiles p on p.id = r.member_id
                where r.listing_id = l.id and r.garage_id = gid and r.status = 'draft' limit 1),
      'unread_from_seller', (select count(*) from public.messages m where m.conversation_id = c.id and m.side = 'seller'))
  from public.conversations c join public.listings l on l.id = c.listing_id
  where c.garage_id = gid order by (c.status in ('in_play','agreed')) desc, c.opened_at desc;
end $$;

-- Garage team list with names (profiles are otherwise private)
create or replace function public.garage_team(p_garage uuid default null) returns setof jsonb language plpgsql stable security definer set search_path = public as $$
declare gid uuid := coalesce(p_garage, public.my_team_garage());
begin
  if not (public.is_admin() or gid = public.my_team_garage()) then raise exception 'Not your garage.'; end if;
  return query
  select jsonb_build_object('id',m.id,'name',p.name,'email',p.email,'role',m.role,'status',m.status,'user_id',m.user_id,'added_at',m.added_at)
  from public.garage_members m join public.profiles p on p.id = m.user_id where m.garage_id = gid
  union all
  select jsonb_build_object('id',i.id,'name',coalesce(i.name,''),'email',i.email,'role',i.role,'status','invited (no account yet)','user_id',null,'added_at',i.created_at)
  from public.garage_invites i where i.garage_id = gid and not i.used;
end $$;

-- Deal page: the deal, its events, the car, and names
create or replace function public.deal_view(p_deal uuid) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare d public.deals; l public.listings; side text;
begin
  select * into d from public.deals where id = p_deal;
  side := public.deal_side(d);
  if side is null then raise exception 'Not your deal.'; end if;
  select * into l from public.listings where id = d.listing_id;
  return jsonb_build_object('deal', to_jsonb(d), 'side', side,
    'listing', jsonb_build_object('id',l.id,'ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'price',l.price,'currency',l.currency,'status',l.status,'photos',l.photos,'saaz_owned',l.saaz_owned),
    'buyer', (select name from public.profiles where id = d.buyer_id),
    'events', (select jsonb_agg(to_jsonb(e) order by e.created_at) from public.deal_events e where e.deal_id = d.id),
    'contacts', public.deal_contacts(p_deal));
end $$;

create or replace function public.my_deals() returns setof jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object('deal', to_jsonb(d), 'side', public.deal_side(d),
    'listing', jsonb_build_object('ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'currency',l.currency,'price',l.price))
  from public.deals d join public.listings l on l.id = d.listing_id
  where d.buyer_id = auth.uid() or public.is_seller_of(l.id)
  order by d.updated_at desc
$$;
