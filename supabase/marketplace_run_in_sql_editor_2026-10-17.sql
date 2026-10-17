-- Saaz marketplace: the rest of the database update, 17 Oct 2026.
-- Run once in Supabase: SQL Editor > New query > paste all of this > Run.
-- Parts 1, 2a and 2b were applied earlier from this chat. This adds the remaining functions and the read rules.
-- It only adds functions and rules. The word 'delete' below only appears inside functions (removing unfinished review drafts,
-- un-saving a car, removing an admin); running this file deletes nothing.
begin;
create or replace function public.apply_garage(p jsonb) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid;
begin
  if exists (select 1 from public.garage_members where user_id = u and status <> 'removed') then
    raise exception 'This account is already on a garage team.'; end if;
  if not coalesce((p->>'honest_declaration')::boolean,false) then raise exception 'Tick the honest-reviews declaration.'; end if;
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

create or replace function public.resubmit_garage(p_garage uuid, p jsonb) returns void language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); g public.garages;
begin
  select * into g from public.garages where id = p_garage;
  if g.created_by <> u or g.status <> 'more_info' then raise exception 'This application cannot be changed now.'; end if;
  update public.garages set name = trim(p->>'name'), address = trim(p->>'address'), phone = trim(p->>'phone'),
    registration_no = trim(p->>'registration_no'), region = p->>'region', years = nullif(p->>'years','')::int,
    specialties = coalesce(array(select jsonb_array_elements_text(p->'specialties')),'{}'), status = 'applied'
  where id = p_garage;
  perform public.audit('garage','garage',p_garage::text,'resubmitted', jsonb_build_object('before',to_jsonb(g),'after',p));
  perform public.notify_admins('garage_applied','Garage application resubmitted: ' || g.name, '#/admin/garage/' || p_garage);
end $$;

create or replace function public.admin_decide_garage(p_garage uuid, p_decision text, p_note text default null) returns void
language plpgsql security definer set search_path = public as $$
declare g public.garages; new_status text; owner uuid;
begin
  perform public.require_admin();
  select * into g from public.garages where id = p_garage;
  if p_decision in ('more_info','rejected','suspended') and coalesce(trim(p_note),'') = '' then raise exception 'A note is required.'; end if;
  new_status := case p_decision when 'approve' then 'certified' when 'reinstate' then 'certified' else p_decision end;
  if new_status not in ('certified','more_info','rejected','suspended') then raise exception 'Unknown decision.'; end if;
  update public.garages set status = new_status, status_note = p_note,
    certified_at = case when new_status = 'certified' and certified_at is null then now() else certified_at end
  where id = p_garage;
  perform public.audit('admin','garage',p_garage::text,p_decision, jsonb_build_object('before',g.status,'after',new_status,'note',p_note));
  select user_id into owner from public.garage_members where garage_id = p_garage and role = 'owner' and status <> 'removed' limit 1;
  perform public.notify(owner, 'garage_' || new_status,
    case new_status when 'certified' then g.name || ' is a certified Saaz garage. Sign in as Garage team to start.'
      when 'more_info' then 'Saaz needs more information about ' || g.name || ': ' || p_note
      when 'rejected' then g.name || ' was not approved: ' || p_note
      else g.name || ' is suspended: ' || p_note end, '#/garage', '{app,email,sms}');
  if new_status = 'suspended' then
    perform public.pass_on(c.id, 'closed') from public.conversations c where c.garage_id = p_garage and c.status in ('in_play','agreed');
    delete from public.reviews where garage_id = p_garage and status = 'draft';
  end if;
end $$;

create or replace function public.admin_add_garage(p jsonb, p_owner_email text, p_owner_name text, p_owner_mobile text, p_reason text) returns uuid
language plpgsql security definer set search_path = public as $$
declare a uuid := public.require_admin(); gid uuid; owner uuid;
begin
  if coalesce(trim(p_reason),'') = '' then raise exception 'A reason is required.'; end if;
  select id into owner from public.profiles where email = lower(trim(p_owner_email));
  if owner is not null and exists (select 1 from public.garage_members where user_id = owner and status <> 'removed') then
    raise exception 'That person is already on a garage team.'; end if;
  insert into public.garages (name, business_type, country, region, address, phone, registration_no, years, specialties, honest_declaration, status, certified_at, created_by)
  values (trim(p->>'name'), p->>'business_type', p->>'country', p->>'region', trim(p->>'address'), trim(p->>'phone'),
          trim(p->>'registration_no'), nullif(p->>'years','')::int,
          coalesce(array(select jsonb_array_elements_text(p->'specialties')),'{}'), true, 'certified', now(), a)
  returning id into gid;
  if owner is not null then
    insert into public.garage_members (garage_id, user_id, role) values (gid, owner, 'owner');
    perform public.notify(owner,'garage_certified','You were added as owner of ' || (p->>'name') || ' on Saaz.','#/garage','{app,email,sms}');
  else
    insert into public.garage_invites (garage_id, email, name, mobile, role) values (gid, lower(trim(p_owner_email)), p_owner_name, p_owner_mobile, 'owner');
  end if;
  perform public.audit('admin','garage',gid::text,'added directly', jsonb_build_object('after',p,'owner',p_owner_email,'reason',p_reason));
  return gid;
end $$;

create or replace function public.add_garage_member(p_email text, p_name text, p_mobile text, p_role text) returns text
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid; target uuid;
begin
  select garage_id into gid from public.garage_members where user_id = u and role = 'owner' and status = 'active';
  if gid is null then raise exception 'Only an active garage owner can add members.'; end if;
  if p_role not in ('owner','inspector') then raise exception 'Choose Owner or Inspector.'; end if;
  select id into target from public.profiles where email = lower(trim(p_email));
  if target is not null then
    if exists (select 1 from public.garage_members where user_id = target and status <> 'removed') then
      raise exception 'That person is already on a garage team.'; end if;
    insert into public.garage_members (garage_id, user_id, role) values (gid, target, p_role);
    perform public.notify(target,'member_invited','You were added to a Saaz garage team. Sign in as Garage team to start.','#/garage','{app,email,sms}');
    perform public.audit('garage','member',target::text,'invited', jsonb_build_object('garage',gid,'role',p_role));
    return 'invited';
  end if;
  insert into public.garage_invites (garage_id, email, name, mobile, role) values (gid, lower(trim(p_email)), p_name, p_mobile, p_role);
  perform public.audit('garage','member',lower(trim(p_email)),'invited (no account yet)', jsonb_build_object('garage',gid,'role',p_role));
  return 'invite_waiting_for_signup';
end $$;

create or replace function public.remove_garage_member(p_member uuid) returns void language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); m public.garage_members;
begin
  select * into m from public.garage_members where id = p_member;
  if not exists (select 1 from public.garage_members where user_id = u and garage_id = m.garage_id and role = 'owner' and status = 'active')
     and not public.is_admin() then raise exception 'Only the garage owner can remove members.'; end if;
  if m.user_id = u then raise exception 'You cannot remove yourself.'; end if;
  update public.garage_members set status = 'removed' where id = p_member;
  delete from public.reviews where member_id = m.user_id and garage_id = m.garage_id and status = 'draft';
  perform public.audit(case when public.is_admin() then 'admin' else 'garage' end,'member',p_member::text,'removed');
end $$;
create or replace function public.vin_lookup(p_vin text) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v public.vehicles; top int; v_vin text := upper(regexp_replace(p_vin,'\s','','g'));
begin
  perform public.require_user();
  select * into v from public.vehicles where vehicles.vin = v_vin;
  if v is null then return jsonb_build_object('found','nothing','vin',v_vin); end if;
  select max(km) into top from public.odometer_readings where vehicle_id = v.id;
  return jsonb_build_object('found', case when v.source = 'saaz_import' then 'saaz_import' else 'earlier' end,
    'vin',v_vin,'vehicle',to_jsonb(v),'highest_km',top,
    'active_listing', exists (select 1 from public.listings where vehicle_id = v.id and status not in ('sold','rejected','withdrawn')));
end $$;

create or replace function public.check_vin(vin text) returns void language plpgsql immutable as $$
begin
  if vin !~ '^[A-Z0-9-]{6,20}$' then raise exception 'The VIN or chassis number must be 6 to 17 letters or digits.'; end if;
  if length(vin) = 17 and vin ~ '[IOQ]' then raise exception 'A 17-character VIN never contains I, O or Q.'; end if;
end $$;

create or replace function public.check_plate(country text, plate text) returns void language plpgsql immutable as $$
declare p text := upper(regexp_replace(plate,'\s','','g'));
begin
  if country = 'UG' and p !~ '^U[A-Z]{2}[0-9]{3}[A-Z]$' then raise exception 'Uganda plates look like UBA 123X.'; end if;
  if country = 'KE' and p !~ '^K[A-Z]{2}[0-9]{3}[A-Z]$' then raise exception 'Kenya plates look like KDA 123X.'; end if;
end $$;

create or replace function public.save_listing(p jsonb) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); saaz boolean := coalesce((p->>'saaz_owned')::boolean,false);
  v_vin text := upper(regexp_replace(coalesce(p->>'vin',''),'\s','','g'));
  v public.vehicles; l public.listings; lid uuid := nullif(p->>'id','')::uuid; top int; locked boolean;
begin
  if saaz then perform public.require_admin(); end if;
  perform public.check_vin(v_vin);
  if lid is not null then
    select * into l from public.listings where id = lid;
    if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
    if l.status not in ('draft','changes_requested') then raise exception 'Only drafts can be edited here.'; end if;
    select * into v from public.vehicles where id = l.vehicle_id;
    if v.vin <> v_vin then raise exception 'The VIN cannot change on an existing listing.'; end if;
  else
    select * into v from public.vehicles where vehicles.vin = v_vin;
    if v is null then
      insert into public.vehicles (vin, make, model, year, fuel, gearbox, body, engine)
      values (v_vin, p->>'make', p->>'model', nullif(p->>'year','')::int, p->>'fuel', p->>'gearbox', p->>'body', p->>'engine')
      returning * into v;
      perform public.audit(case when saaz then 'admin' else 'seller' end,'vehicle',v.id::text,'first Saaz record', jsonb_build_object('vin',v_vin));
    end if;
    if v.saaz_owned and not saaz then raise exception 'This car is owned by Saaz.'; end if;
  end if;
  locked := v.source = 'saaz_import';
  select max(km) into top from public.odometer_readings where vehicle_id = v.id;
  if (p->>'mileage')::int < coalesce(top,0) then
    raise exception 'Mileage cannot be lower than the highest Saaz reading for this car (% km).', top; end if;
  if nullif(p->>'year','')::int not between 1980 and extract(year from now())::int + 1 then raise exception 'Year must be 1980 to next year.'; end if;
  perform public.check_plate(p->>'country', p->>'plate');
  if lid is null then
    insert into public.listings (vehicle_id, seller_id, saaz_owned, country, region, make, model, year, fuel, gearbox, body, colour, engine,
      mileage, plate, currency, price, description, photos, logbook_name_matches, owner_authorised)
    values (v.id, case when saaz then null else u end, saaz, p->>'country', p->>'region',
      case when locked then v.make else p->>'make' end, case when locked then v.model else p->>'model' end,
      case when locked then v.year else (p->>'year')::int end, case when locked then v.fuel else p->>'fuel' end,
      case when locked then v.gearbox else p->>'gearbox' end, case when locked then v.body else p->>'body' end,
      p->>'colour', case when locked then v.engine else p->>'engine' end,
      (p->>'mileage')::int, upper(trim(p->>'plate')), case when p->>'country' = 'KE' then 'KES' else 'UGX' end,
      (p->>'price')::bigint, coalesce(p->>'description',''), coalesce(array(select jsonb_array_elements_text(p->'photos')),'{}'),
      coalesce((p->>'logbook_name_matches')::boolean,false), coalesce((p->>'owner_authorised')::boolean,false))
    returning id into lid;
    perform public.audit(case when saaz then 'admin' else 'seller' end,'listing',lid::text,'created draft', jsonb_build_object('after',p));
  else
    update public.listings set country = p->>'country', region = p->>'region',
      make = case when locked then v.make else p->>'make' end, model = case when locked then v.model else p->>'model' end,
      year = case when locked then v.year else (p->>'year')::int end, fuel = case when locked then v.fuel else p->>'fuel' end,
      gearbox = case when locked then v.gearbox else p->>'gearbox' end, body = case when locked then v.body else p->>'body' end,
      colour = p->>'colour', engine = case when locked then v.engine else p->>'engine' end,
      mileage = (p->>'mileage')::int, plate = upper(trim(p->>'plate')), currency = case when p->>'country' = 'KE' then 'KES' else 'UGX' end,
      price = (p->>'price')::bigint, description = coalesce(p->>'description',''),
      photos = coalesce(array(select jsonb_array_elements_text(p->'photos')),'{}'),
      logbook_name_matches = coalesce((p->>'logbook_name_matches')::boolean,false),
      owner_authorised = coalesce((p->>'owner_authorised')::boolean,false), updated_at = now()
    where id = lid;
    perform public.audit(case when saaz then 'admin' else 'seller' end,'listing',lid::text,'edited draft',
      jsonb_build_object('before',to_jsonb(l),'after',p));
  end if;
  return lid;
end $$;

create or replace function public.next_garage(l public.listings) returns uuid language sql stable security definer set search_path = public as $$
  select g.id from public.garages g
  join public.regions gr on gr.name = g.region
  join public.regions lr on lr.name = l.region
  where g.status = 'certified' and g.country = l.country
    and not exists (select 1 from public.garage_members m where m.garage_id = g.id and m.status <> 'removed' and m.user_id = l.seller_id)
    and not exists (select 1 from public.conversations c where c.listing_id = l.id and c.garage_id = g.id and c.round = l.line_round)
  order by sqrt(power(gr.lat - lr.lat, 2) + power((gr.lng - lr.lng) * cos(radians(lr.lat)), 2)),
    (select count(*) from public.conversations c2 where c2.garage_id = g.id and c2.status in ('in_play','agreed')),
    g.certified_at
  limit 1
$$;

create or replace function public.put_next_in_play(p_listing uuid) returns uuid language plpgsql security definer set search_path = public as $$
declare l public.listings; gid uuid; cid uuid; gname text;
begin
  select * into l from public.listings where id = p_listing;
  if l.status <> 'awaiting_review' then return null; end if;
  gid := public.next_garage(l);
  if gid is null then
    update public.listings set line_empty = true where id = p_listing;
    perform public.notify_admins('line_empty','No garage left in line for ' || l.ref || '. Assign one or restart the line.','#/admin/car/' || l.id);
    perform public.notify(u, 'line_empty', 'Saaz will find a garage for ' || l.ref || ' and let you know.', '#/my/cars/' || l.id)
      from public.seller_side_users(l) u;
    perform public.audit('system','listing',l.id::text,'garage line empty');
    return null;
  end if;
  insert into public.conversations (listing_id, garage_id, round, deadline)
  values (p_listing, gid, l.line_round, now() + make_interval(hours => (public.setting('garage_contact_hours'))::text::int))
  returning id into cid;
  update public.listings set line_empty = false where id = p_listing;
  select name into gname from public.garages where id = gid;
  perform public.notify_garage(gid,'garage_in_play','A ' || l.year || ' ' || l.make || ' ' || l.model || ' in ' || l.region ||
    ' is yours to contact. Message the seller within ' || (public.setting('garage_contact_hours')) || ' hours.','#/garage/job/' || cid);
  perform public.notify(u, 'garage_in_play', gname || ' will contact you about ' || l.ref || ' inside Saaz.', '#/my/cars/' || l.id)
    from public.seller_side_users(l) u;
  perform public.audit('system','conversation',cid::text,'garage put in play', jsonb_build_object('listing',l.ref,'garage',gname));
  return cid;
end $$;

create or replace function public.pass_on(p_conv uuid, p_status text) returns void language plpgsql security definer set search_path = public as $$
declare c public.conversations; l public.listings;
begin
  select * into c from public.conversations where id = p_conv;
  if c.status not in ('in_play','agreed') then return; end if;
  update public.conversations set status = p_status, closed_at = now() where id = p_conv;
  select * into l from public.listings where id = c.listing_id;
  if l.status = 'review_booked' then update public.listings set status = 'awaiting_review' where id = l.id; end if;
  delete from public.reviews where listing_id = l.id and garage_id = c.garage_id and status = 'draft';
  perform public.audit('system','conversation',p_conv::text,p_status);
  if p_status <> 'closed' or l.status in ('awaiting_review','review_booked') then
    perform public.put_next_in_play(l.id);
  end if;
end $$;

create or replace function public.tick() returns void language plpgsql security definer set search_path = public as $$
declare c record;
begin
  for c in select id from public.conversations where status = 'in_play' and garage_first_message_at is null and deadline < now() loop
    perform public.pass_on(c.id, 'timed_out');
  end loop;
  update public.listings l set status = 're_review_due', updated_at = now()
  from public.reviews r where r.id = l.current_review_id and l.status = 'live' and r.valid_until < current_date;
end $$;

create or replace function public.submit_listing(p_listing uuid) returns void language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); l public.listings; pr public.profiles; n int; minp bigint;
begin
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('draft','changes_requested','re_review_due') then raise exception 'This listing is already submitted.'; end if;
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
  update public.listings set status = 'awaiting_review', submitted_at = now(), admin_note = null, updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'submitted');
  perform public.put_next_in_play(l.id);
end $$;

create or replace function public.change_price(p_listing uuid, p_price bigint) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings; minp bigint;
begin
  perform public.require_user();
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('live','draft','changes_requested','awaiting_review','review_booked','awaiting_approval') then raise exception 'The price cannot change now.'; end if;
  minp := case when l.currency = 'KES' then (public.setting('min_price_kes'))::text::bigint else (public.setting('min_price_ugx'))::text::bigint end;
  if p_price < minp then raise exception 'The lowest asking price is % %.', l.currency, minp; end if;
  update public.listings set price = p_price, updated_at = now() where id = p_listing;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'price changed',
    jsonb_build_object('before',l.price,'after',p_price));
end $$;

create or replace function public.reopen_for_changes(p_listing uuid) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings;
begin
  perform public.require_user();
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('live','re_review_due') then raise exception 'Only live cars use this. Cars in review must be withdrawn to edit.'; end if;
  if exists (select 1 from public.deals where listing_id = l.id and status in ('negotiating','agreed','on_hold')) then
    raise exception 'Close or reject open offers before changing anything other than the price.'; end if;
  update public.listings set status = 'draft', updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'taken off sale to edit; needs a new Saaz review');
end $$;

create or replace function public.withdraw_listing(p_listing uuid) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings;
begin
  perform public.require_user();
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status in ('reserved','sold','withdrawn') then raise exception 'This listing cannot be withdrawn now.'; end if;
  update public.listings set status = 'withdrawn', updated_at = now() where id = l.id;
  update public.conversations set status = 'closed', closed_at = now() where listing_id = l.id and status in ('in_play','agreed');
  update public.deals set status = 'closed', updated_at = now() where listing_id = l.id and status in ('negotiating','on_hold');
  delete from public.reviews where listing_id = l.id and status = 'draft';
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'withdrawn');
end $$;

create or replace function public.set_offer_rules(p_listing uuid, p jsonb) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings;
begin
  perform public.require_user();
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  update public.listings set rule_min_pct = nullif(p->>'min_pct','')::int, rule_min_amount = nullif(p->>'min_amount','')::bigint,
    rule_no_trade_in = coalesce((p->>'no_trade_in')::boolean,false), rule_on_counters = coalesce((p->>'on_counters')::boolean,false),
    auto_reject = coalesce((p->>'auto_reject')::boolean,false), updated_at = now()
  where id = p_listing;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'offer rules changed',
    jsonb_build_object('before',jsonb_build_object('min_pct',l.rule_min_pct,'min_amount',l.rule_min_amount,'no_trade_in',l.rule_no_trade_in,
      'on_counters',l.rule_on_counters,'auto_reject',l.auto_reject),'after',p));
end $$;
create or replace function public.mask_contacts(t text) returns text language sql immutable as $$
  select regexp_replace(regexp_replace(t, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[hidden until you agree]', 'g'),
    '\+?[0-9][0-9 ()-]{7,}[0-9]', '[hidden until you agree]', 'g')
$$;

create or replace function public.send_message(p_conv uuid, p_body text) returns void language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); c public.conversations; l public.listings; side text; body text;
begin
  select * into c from public.conversations where id = p_conv;
  select * into l from public.listings where id = c.listing_id;
  if public.is_listing_seller(l) then side := 'seller';
  elsif public.my_garage_id() = c.garage_id then side := 'garage';
  else raise exception 'You are not part of this conversation.'; end if;
  if c.status not in ('in_play','agreed') then raise exception 'This conversation is closed.'; end if;
  if side = 'seller' and c.garage_first_message_at is null then raise exception 'Wait for the garage to message first.'; end if;
  body := case when c.status = 'agreed' then trim(p_body) else public.mask_contacts(trim(p_body)) end;
  insert into public.messages (conversation_id, sender_id, side, body) values (p_conv, u, side, body);
  if side = 'garage' and c.garage_first_message_at is null then
    update public.conversations set garage_first_message_at = now() where id = p_conv;
    perform public.audit('garage','conversation',p_conv::text,'garage made contact');
  end if;
  if side = 'garage' then
    perform public.notify(x, 'garage_message', 'New message from the garage about ' || l.ref || '.', '#/my/cars/' || l.id) from public.seller_side_users(l) x;
  else
    perform public.notify_garage(c.garage_id, 'seller_message', 'New message from the seller of ' || l.ref || '.', '#/garage/job/' || p_conv);
  end if;
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
    perform public.notify_garage(c.garage_id,'seller_agreed','The seller of ' || l.ref || ' agreed. Set a review date and start the review when the car is with you.','#/garage/job/' || p_conv);
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'conversation',p_conv::text,'agreed');
  else
    if coalesce(trim(p_reason),'') <> '' then insert into public.pass_reasons values (p_conv, trim(p_reason)); end if;
    perform public.notify_garage(c.garage_id,'seller_passed','The seller of ' || l.ref || ' chose another garage.','#/garage');
    perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'conversation',p_conv::text,'passed');
    perform public.pass_on(p_conv, 'passed');
  end if;
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
    perform public.notify(x,'review_date','Review date for ' || l.ref || ': ' || to_char(p_date,'Dy DD Mon YYYY') || '.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
    perform public.audit('garage','conversation',p_conv::text,'review date set', jsonb_build_object('after',p_date));
  else
    raise exception 'That action is not available now.';
  end if;
end $$;

create or replace function public.admin_assign_garage(p_listing uuid, p_garage uuid) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings; cid uuid;
begin
  perform public.require_admin();
  select * into l from public.listings where id = p_listing;
  if l.status not in ('awaiting_review','review_booked') then raise exception 'The car is not waiting for a review.'; end if;
  if not exists (select 1 from public.garages where id = p_garage and status = 'certified' and country = l.country) then
    raise exception 'Choose a certified garage in the same country.'; end if;
  update public.conversations set status = 'closed', closed_at = now() where listing_id = p_listing and status in ('in_play','agreed');
  delete from public.reviews where listing_id = p_listing and status = 'draft';
  insert into public.conversations (listing_id, garage_id, round, status, assigned_by_admin, garage_first_message_at)
  values (p_listing, p_garage, l.line_round, 'agreed', true, now()) returning id into cid;
  update public.listings set status = 'review_booked', line_empty = false, updated_at = now() where id = p_listing;
  perform public.notify_garage(p_garage,'assigned','Saaz assigned you ' || l.ref || '. Message the seller to arrange the review.','#/garage/job/' || cid);
  perform public.notify(x,'assigned','Saaz booked your Saaz review for ' || l.ref || '. The garage will message you here.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
  perform public.audit('admin','listing',l.id::text,'garage assigned directly', jsonb_build_object('garage',p_garage));
end $$;

create or replace function public.admin_restart_line(p_listing uuid) returns void language plpgsql security definer set search_path = public as $$
declare l public.listings;
begin
  perform public.require_admin();
  select * into l from public.listings where id = p_listing;
  update public.conversations set status = 'closed', closed_at = now() where listing_id = p_listing and status in ('in_play','agreed');
  delete from public.reviews where listing_id = p_listing and status = 'draft';
  update public.listings set status = 'awaiting_review', line_empty = false, line_round = line_round + 1 where id = p_listing;
  perform public.audit('admin','listing',l.id::text,'garage line restarted');
  perform public.put_next_in_play(p_listing);
end $$;
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
  if not auto_live then perform public.notify_admins('review_issued','Review issued for ' || l.ref || ': waiting for approval.','#/admin/car/' || l.id); end if;
  return jsonb_build_object('doc_no',r.doc_no,'verify_code',code,'verdict',r.verdict,'score',r.score,'live',auto_live);
end $$;

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
  perform public.notify_admins('deal_agreed','Deal agreed on ' || l.ref || ': confirm the handover to complete it.','#/deals/' || p_deal);
end $$;

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

create or replace function public.admin_conversation_counts() returns table (listing_ref text, garage text, status text, messages bigint, opened_at timestamptz)
language sql stable security definer set search_path = public as $$
  select l.ref, g.name, c.status, (select count(*) from public.messages m where m.conversation_id = c.id), c.opened_at
  from public.conversations c join public.listings l on l.id = c.listing_id join public.garages g on g.id = c.garage_id
  where public.is_admin() order by c.opened_at desc
$$;
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

revoke execute on function public.audit(text,text,text,text,jsonb) from public, anon, authenticated;
revoke execute on function public.notify(uuid,text,text,text,text[]) from public, anon, authenticated;
revoke execute on function public.notify_admins(text,text,text) from public, anon, authenticated;
revoke execute on function public.notify_garage(uuid,text,text,text) from public, anon, authenticated;
revoke execute on function public.put_next_in_play(uuid) from public, anon, authenticated;
revoke execute on function public.pass_on(uuid,text) from public, anon, authenticated;
revoke execute on function public.deal_agree(uuid,text) from public, anon, authenticated;
revoke execute on function public.handle_new_user() from public, anon, authenticated;
revoke execute on function public.seller_side_users(public.listings) from public, anon, authenticated;
revoke execute on function public.next_garage(public.listings) from public, anon, authenticated;
revoke execute on function public.review_canonical(public.reviews) from public, anon, authenticated;

alter table public.settings enable row level security;
alter table public.regions enable row level security;
alter table public.profiles enable row level security;
alter table public.vehicles enable row level security;
alter table public.odometer_readings enable row level security;
alter table public.listings enable row level security;
alter table public.garages enable row level security;
alter table public.garage_members enable row level security;
alter table public.garage_invites enable row level security;
alter table public.conversations enable row level security;
alter table public.pass_reasons enable row level security;
alter table public.messages enable row level security;
alter table public.reviews enable row level security;
alter table public.deals enable row level security;
alter table public.deal_events enable row level security;
alter table public.listing_views enable row level security;
alter table public.saves enable row level security;
alter table public.notifications enable row level security;
alter table public.audit_log enable row level security;

create policy "anyone reads settings" on public.settings for select using (true);
create policy "anyone reads regions" on public.regions for select using (true);

create policy "own profile or admin" on public.profiles for select using (id = auth.uid() or public.is_admin());

create policy "signed-in read vehicles" on public.vehicles for select using (auth.uid() is not null);
create policy "anyone reads odometer history" on public.odometer_readings for select using (true);

create policy "public cars, own cars, garage jobs, admin" on public.listings for select using (
  status in ('live','reserved','sold') or seller_id = auth.uid() or public.is_admin() or public.garage_on_listing(id));

create policy "certified garages public, own garage, admin" on public.garages for select using (
  status = 'certified' or public.is_admin() or id = public.my_team_garage());

create policy "own team or admin" on public.garage_members for select using (
  public.is_admin() or user_id = auth.uid() or garage_id = public.my_team_garage());
create policy "garage owners and admin see invites" on public.garage_invites for select using (
  public.is_admin() or garage_id in (select garage_id from public.garage_members m where m.user_id = auth.uid() and m.role = 'owner' and m.status = 'active'));

create policy "seller, garage, admin" on public.conversations for select using (
  public.is_admin() or garage_id = public.my_garage_id() or public.is_seller_of(listing_id));
create policy "seller and admin read pass reasons" on public.pass_reasons for select using (
  public.is_admin() or exists (select 1 from public.conversations c where c.id = pass_reasons.conversation_id and public.is_seller_of(c.listing_id)));
create policy "only the two sides" on public.messages for select using (
  public.can_read_messages(conversation_id));

create policy "issued reviews public, drafts to the garage, admin" on public.reviews for select using (
  status in ('issued','superseded','void') or public.is_admin() or garage_id = public.my_garage_id() or public.is_seller_of(listing_id));

create policy "buyer, seller, admin" on public.deals for select using (
  buyer_id = auth.uid() or public.is_admin() or public.is_seller_of(listing_id));
create policy "buyer, seller, admin" on public.deal_events for select using (
  public.can_see_deal(deal_id));

create policy "own saves" on public.saves for select using (user_id = auth.uid());
create policy "own notifications" on public.notifications for select using (user_id = auth.uid());
create policy "admins read audit" on public.audit_log for select using (public.is_admin());

create or replace function public.mark_read(p_ids uuid[]) returns void language sql security definer set search_path = public as
$$ update public.notifications set read = true where user_id = auth.uid() and id = any(p_ids) $$;

create policy "admins read all notifications" on public.notifications for select using (public.is_admin());

create policy "sellers upload own photos" on storage.objects for insert to authenticated
  with check (bucket_id = 'car-photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "sellers delete own photos" on storage.objects for delete to authenticated
  using (bucket_id = 'car-photos' and (storage.foldername(name))[1] = auth.uid()::text);
commit;
