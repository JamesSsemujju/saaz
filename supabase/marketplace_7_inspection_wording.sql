-- Saaz marketplace, part 7: "review" becomes "inspection" in every message people see (17 Oct 2026).
-- Run once in Supabase: SQL Editor > New query > paste > Run. Only replaces functions; names of tables and statuses stay as they are.
-- The word 'delete' appears inside some functions (unfinished drafts); running this file deletes nothing.
begin;
create or replace function public.admin_assign_garage(p_listing uuid, p_garage uuid) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings; cid uuid;
begin
  perform public.require_admin();
  select * into l from public.listings where id = p_listing;
  if l.status not in ('awaiting_review','review_booked') then raise exception 'The car is not waiting for an inspection.'; end if;
  if not exists (select 1 from public.garages where id = p_garage and status = 'certified' and country = l.country) then
    raise exception 'Choose a certified garage in the same country.'; end if;
  update public.conversations set status = 'closed', closed_at = now() where listing_id = p_listing and status in ('in_play','agreed');
  delete from public.reviews where listing_id = p_listing and status = 'draft';
  insert into public.conversations (listing_id, garage_id, round, status, assigned_by_admin, garage_first_message_at)
  values (p_listing, p_garage, l.line_round, 'agreed', true, now()) returning id into cid;
  update public.listings set status = 'review_booked', line_empty = false, updated_at = now() where id = p_listing;
  perform public.notify_garage(p_garage,'assigned','Saaz assigned you ' || l.ref || '. Message the seller to arrange the inspection.','#/garage/job/' || cid);
  perform public.notify(x,'assigned','Saaz booked your Saaz inspection for ' || l.ref || '. The garage will message you here.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
  perform public.audit('admin','listing',l.id::text,'garage assigned directly', jsonb_build_object('garage',p_garage));
end $$;

create or replace function public.admin_void_review(p_review uuid, p_reason text) returns void language plpgsql security definer set search_path = public as $$
declare r public.reviews; l public.listings;
begin
  perform public.require_admin();
  if coalesce(trim(p_reason),'') = '' then raise exception 'A reason is required.'; end if;
  select * into r from public.reviews where id = p_review;
  if r.status <> 'issued' then raise exception 'Only an issued inspection report can be voided.'; end if;
  update public.reviews set status = 'void', void_reason = p_reason where id = p_review;
  select * into l from public.listings where id = r.listing_id;
  update public.deals set status = 'closed', updated_at = now() where listing_id = l.id and status in ('negotiating','on_hold');
  update public.listings set status = 'awaiting_review', current_review_id = null, updated_at = now() where id = l.id and status not in ('sold','reserved','withdrawn');
  perform public.notify_garage(r.garage_id,'review_void','Saaz voided inspection report ' || r.doc_no || ': ' || p_reason,'#/garage');
  perform public.notify(x,'review_void','The Saaz inspection for ' || l.ref || ' was voided. Saaz is arranging a new one.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
  perform public.audit('admin','review',p_review::text,'voided', jsonb_build_object('reason',p_reason));
  perform public.put_next_in_play(l.id);
end $$;

create or replace function public.apply_garage(p jsonb) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid;
begin
  if exists (select 1 from public.garage_members where user_id = u and status <> 'removed') then
    raise exception 'This account is already on a garage team.'; end if;
  if not coalesce((p->>'honest_declaration')::boolean,false) then raise exception 'Tick the honest-inspections declaration.'; end if;
  insert into public.garages (name, business_type, country, region, address, phone, registration_no, years, specialties, honest_declaration, created_by)
  values (trim(p->>'name'), p->>'business_type', p->>'country', p->>'region', trim(p->>'address'), trim(p->>'phone'),
          trim(p->>'registration_no'), nullif(p->>'years','')::int,
          coalesce(array(select jsonb_array_elements_text(p->'specialties')),'{}'), true, u)
  returning id into gid;
  insert into public.garage_members (garage_id, user_id, role, status) values (gid, u, 'owner', 'active');
  perform public.audit('garage','garage',gid::text,'applied', jsonb_build_object('after',p));
  perform public.notify_admins('garage_applied','New garage application: ' || (p->>'name'), '#/admin/garage/' || gid);
  return gid;
end $$;

create or replace function public.garage_respond(p_conv uuid, p_action text, p_date date default null) returns void
language plpgsql security definer set search_path = public as $$
declare c public.conversations; l public.listings;
begin
  perform public.require_user();
  select * into c from public.conversations where id = p_conv;
  if public.my_garage_id() is distinct from c.garage_id then raise exception 'Not your garage''s job.'; end if;
  select * into l from public.listings where id = c.listing_id;
  if p_action = 'decline' and c.status = 'in_play' then
    perform public.audit('garage','conversation',p_conv::text,'declined');
    perform public.pass_on(p_conv, 'declined');
  elsif p_action = 'release' and c.status = 'agreed' then
    perform public.notify(x,'garage_released','The garage released ' || l.ref || '. Saaz is bringing in the next garage.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
    perform public.audit('garage','conversation',p_conv::text,'released');
    perform public.pass_on(p_conv, 'released');
  elsif p_action = 'set_date' and c.status = 'agreed' then
    update public.conversations set review_date = p_date where id = p_conv;
    perform public.notify(x,'review_date','Inspection date for ' || l.ref || ': ' || to_char(p_date,'Dy DD Mon YYYY') || '.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
    perform public.audit('garage','conversation',p_conv::text,'inspection date set', jsonb_build_object('after',p_date));
  else
    raise exception 'That action is not available now.';
  end if;
end $$;

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
  if not r.in_person then raise exception 'Confirm the car was inspected in person and the VIN checked.'; end if;
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
  perform public.notify(x, 'review_issued', 'Your Saaz inspection report for ' || l.ref || ' is issued (' || initcap(r.verdict) || ', ' || r.score || '/100). ' ||
    case when auto_live then 'Your car is live.' else 'Saaz will check it within ' || (public.setting('approval_response')#>>'{}') || '.' end,
    '#/my/cars/' || l.id, '{app,email,sms}') from public.seller_side_users(l) x;
  if not auto_live then perform public.notify_admins('review_issued','Inspection report issued for ' || l.ref || ': waiting for approval.','#/admin/car/' || l.id); end if;
  return jsonb_build_object('doc_no',r.doc_no,'verify_code',code,'verdict',r.verdict,'score',r.score,'live',auto_live);
end $$;

create or replace function public.reopen_for_changes(p_listing uuid) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings;
begin
  perform public.require_user();
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('live','re_review_due') then raise exception 'Only live cars use this. Cars in inspection must be withdrawn to edit.'; end if;
  if exists (select 1 from public.deals where listing_id = l.id and status in ('negotiating','agreed','on_hold')) then
    raise exception 'Close or reject open offers before changing anything other than the price.'; end if;
  update public.listings set status = 'draft', updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'taken off sale to edit; needs a new Saaz inspection');
end $$;

create or replace function public.seller_respond(p_conv uuid, p_agree boolean, p_reason text default null) returns void
language plpgsql security definer set search_path = public as $$
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
    update public.listings set status = 'review_booked', updated_at = now() where id = l.id;
    perform public.notify_garage(c.garage_id,'seller_agreed','The seller of ' || l.ref || ' agreed. Set an inspection date and start the inspection when the car is with you.','#/garage/job/' || p_conv);
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'conversation',p_conv::text,'agreed');
  else
    if coalesce(trim(p_reason),'') <> '' then insert into public.pass_reasons values (p_conv, trim(p_reason)); end if;
    perform public.notify_garage(c.garage_id,'seller_passed','The seller of ' || l.ref || ' chose another garage.','#/garage');
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'conversation',p_conv::text,'passed');
    perform public.pass_on(p_conv, 'passed');
  end if;
end $$;

create or replace function public.start_review(p_listing uuid) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid := public.my_garage_id(); l public.listings; rid uuid; other text;
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  select * into l from public.listings where id = p_listing;
  if not exists (select 1 from public.conversations where listing_id = p_listing and garage_id = gid and status = 'agreed') then
    raise exception 'This car is not booked with your garage.'; end if;
  select p.name into other from public.reviews r join public.profiles p on p.id = r.member_id
    where r.listing_id = p_listing and r.garage_id = gid and r.status = 'draft' and r.member_id <> u;
  if other is not null then raise exception 'In progress: % is writing this inspection report.', other; end if;
  select id into rid from public.reviews where listing_id = p_listing and member_id = u and status = 'draft';
  if rid is null then
    insert into public.reviews (listing_id, vehicle_id, garage_id, member_id) values (p_listing, l.vehicle_id, gid, u) returning id into rid;
    perform public.audit('garage','review',rid::text,'inspection started', jsonb_build_object('listing',l.ref));
  end if;
  return rid;
end $$;

create or replace function public.verify_review(p_code text) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare r public.reviews; v public.vehicles; l public.listings;
begin
  select * into r from public.reviews where verify_code = upper(trim(p_code));
  if r is null then return jsonb_build_object('genuine',false,'message','No Saaz inspection has this code.'); end if;
  select * into v from public.vehicles where id = r.vehicle_id;
  select * into l from public.listings where id = r.listing_id;
  return jsonb_build_object('genuine', true,
    'intact', encode(sha256(convert_to(public.review_canonical(r),'UTF8')),'hex') = r.fingerprint,
    'status', case when r.status = 'issued' and r.valid_until < current_date then 'expired' else r.status end,
    'doc_no', r.doc_no, 'version', r.version, 'vin', v.vin, 'make', l.make, 'model', l.model, 'year', l.year, 'plate', l.plate,
    'verdict', r.verdict, 'score', r.score, 'odometer', r.odometer, 'issued_at', r.issued_at, 'valid_until', r.valid_until,
    'garage', r.garage_name, 'member', r.member_name, 'fingerprint', r.fingerprint);
end $$;
-- Replacing a function resets its settings: keep East Africa Time on the ones part 6 set
alter function public.issue_review(uuid) set timezone = 'Africa/Kampala';
alter function public.verify_review(text) set timezone = 'Africa/Kampala';
alter function public.garage_respond(uuid, text, date) set timezone = 'Africa/Kampala';
commit;
