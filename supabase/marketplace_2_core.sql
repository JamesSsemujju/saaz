-- Saaz marketplace, part 2 of 4: helpers, accounts, garages, listings, garage line.
-- Every function checks who is calling. "security definer" lets it write tables the caller can't touch directly.

create or replace function public.setting(k text) returns jsonb language sql stable security definer set search_path = public as
$$ select value from public.settings where key = k $$;

create or replace function public.audit(p_role text, p_entity text, p_id text, p_action text, p_detail jsonb default '{}'::jsonb)
returns void language sql security definer set search_path = public as
$$ insert into public.audit_log (actor_id, actor_role, entity, entity_id, action, detail)
   values (auth.uid(), p_role, p_entity, p_id, p_action, coalesce(p_detail, '{}'::jsonb)) $$;

create or replace function public.notify(p_user uuid, p_kind text, p_body text, p_link text default null, p_channels text[] default '{app}')
returns void language sql security definer set search_path = public as
$$ insert into public.notifications (user_id, kind, body, link, channels)
   select p_user, p_kind, p_body, p_link, p_channels where p_user is not null $$;

create or replace function public.notify_admins(p_kind text, p_body text, p_link text default null)
returns void language sql security definer set search_path = public as
$$ insert into public.notifications (user_id, kind, body, link) select user_id, p_kind, p_body, p_link from public.admins $$;

create or replace function public.notify_garage(p_garage uuid, p_kind text, p_body text, p_link text default null)
returns void language sql security definer set search_path = public as
$$ insert into public.notifications (user_id, kind, body, link, channels)
   select user_id, p_kind, p_body, p_link, '{app,sms}' from public.garage_members where garage_id = p_garage and status <> 'removed' $$;

create or replace function public.my_garage_id() returns uuid language sql stable security definer set search_path = public as
$$ select m.garage_id from public.garage_members m join public.garages g on g.id = m.garage_id
   where m.user_id = auth.uid() and m.status <> 'removed' and g.status = 'certified' limit 1 $$;

create or replace function public.require_user() returns uuid language plpgsql stable security definer set search_path = public as $$
declare u uuid := auth.uid();
begin
  if u is null then raise exception 'Please sign in first.'; end if;
  if exists (select 1 from public.profiles where id = u and suspended) then raise exception 'This account is suspended.'; end if;
  return u;
end $$;

create or replace function public.require_admin() returns uuid language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Admins only.'; end if;
  return auth.uid();
end $$;

-- Who acts as seller for a listing: its seller, or any admin for a Saaz-owned car
create or replace function public.is_listing_seller(l public.listings) returns boolean language sql stable security definer set search_path = public as
$$ select coalesce(l.seller_id = auth.uid(), false) or (l.saaz_owned and public.is_admin()) $$;

create or replace function public.seller_side_users(l public.listings) returns setof uuid language sql stable security definer set search_path = public as
$$ select l.seller_id where not l.saaz_owned union all select user_id from public.admins where l.saaz_owned $$;

-- Access helpers (also used by the read rules in part 4). They run as owner so the rules don't loop through each other.
create or replace function public.my_team_garage() returns uuid language sql stable security definer set search_path = public as
$$ select garage_id from public.garage_members where user_id = auth.uid() and status <> 'removed' limit 1 $$;
create or replace function public.is_seller_of(p_listing uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.listings where id = p_listing and (seller_id = auth.uid() or (saaz_owned and public.is_admin()))) $$;
create or replace function public.garage_on_listing(p_listing uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.conversations where listing_id = p_listing and garage_id = public.my_garage_id()) $$;
create or replace function public.can_see_deal(p_deal uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.deals d where d.id = p_deal and (d.buyer_id = auth.uid() or public.is_admin() or public.is_seller_of(d.listing_id))) $$;
create or replace function public.can_read_messages(p_conv uuid) returns boolean language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.conversations c join public.listings l on l.id = c.listing_id
   where c.id = p_conv and (c.garage_id = public.my_garage_id() or l.seller_id = auth.uid() or (l.saaz_owned and public.is_admin()))) $$;

-- ===== Accounts =====
-- New sign-up: make the profile, and turn any garage invites for this email into memberships.
create or replace function public.handle_new_user() returns trigger language plpgsql security definer set search_path = public as $$
declare inv record;
begin
  insert into public.profiles (id, email, name, country, mobile)
  values (new.id, lower(new.email), coalesce(new.raw_user_meta_data->>'name',''),
          nullif(new.raw_user_meta_data->>'country',''), nullif(new.raw_user_meta_data->>'mobile',''));
  for inv in select * from public.garage_invites where lower(email) = lower(new.email) and not used loop
    insert into public.garage_members (garage_id, user_id, role) values (inv.garage_id, new.id, inv.role) on conflict do nothing;
    update public.garage_invites set used = true where id = inv.id;
  end loop;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();
-- Accounts that existed before this script (for example the first admin) get their profile now
insert into public.profiles (id, email, name)
select u.id, lower(u.email), coalesce(u.raw_user_meta_data->>'name', a.name, '')
from auth.users u left join public.admins a on a.user_id = u.id
on conflict (id) do nothing;

create or replace function public.update_profile(p_name text, p_country text, p_mobile text) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); old public.profiles;
begin
  select * into old from public.profiles where id = u;
  if length(trim(p_name)) < 2 then raise exception 'Enter your full name.'; end if;
  if p_country not in ('UG','KE') then raise exception 'Choose Uganda or Kenya.'; end if;
  update public.profiles set name = trim(p_name), country = p_country, mobile = trim(p_mobile),
    phone_verified = case when trim(p_mobile) is distinct from old.mobile then false else phone_verified end
  where id = u;
  perform public.audit('account','account',u::text,'profile updated',
    jsonb_build_object('before',jsonb_build_object('name',old.name,'country',old.country,'mobile',old.mobile),
                       'after',jsonb_build_object('name',p_name,'country',p_country,'mobile',p_mobile)));
end $$;

-- What the header needs: roles this account holds
create or replace function public.my_roles() returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'signed_in', auth.uid() is not null,
    'admin', public.is_admin(),
    'profile', (select to_jsonb(p) from public.profiles p where p.id = auth.uid()),
    'garage', (select jsonb_build_object('id',g.id,'name',g.name,'status',g.status,'status_note',g.status_note,
                 'member_role',m.role,'member_status',m.status)
               from public.garage_members m join public.garages g on g.id = m.garage_id
               where m.user_id = auth.uid() and m.status <> 'removed' limit 1))
$$;

-- Garage sign-in: blocked with a status message until certified and on the team. Invited members become Active.
create or replace function public.garage_sign_in() returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); m record;
begin
  select m2.*, g.status as gstatus, g.status_note, g.name as gname into m
  from public.garage_members m2 join public.garages g on g.id = m2.garage_id
  where m2.user_id = u and m2.status <> 'removed' limit 1;
  if m is null then return jsonb_build_object('ok',false,'message','This account is not on a garage team.'); end if;
  if m.gstatus <> 'certified' then
    return jsonb_build_object('ok',false,'message', case m.gstatus
      when 'applied' then 'Your garage application is with Saaz. Expect an answer within ' || (public.setting('garage_response')#>>'{}') || '.'
      when 'more_info' then 'Saaz asked for more information: ' || coalesce(m.status_note,'')
      when 'rejected' then 'Your garage application was not approved: ' || coalesce(m.status_note,'')
      else 'Your garage is suspended: ' || coalesce(m.status_note,'') end);
  end if;
  if m.status = 'invited' then
    update public.garage_members set status = 'active' where id = m.id;
    perform public.audit('garage','member',m.id::text,'became active on first garage sign-in');
  end if;
  return jsonb_build_object('ok',true,'garage_id',m.garage_id,'garage',m.gname,'role',m.role);
end $$;

-- ===== Garages =====
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
    -- Cars where it is in play pass to the next garage; booked jobs go back to the line; drafts are discarded.
    perform public.pass_on(c.id, 'closed') from public.conversations c where c.garage_id = p_garage and c.status in ('in_play','agreed');
    delete from public.reviews where garage_id = p_garage and status = 'draft';
  end if;
end $$;

-- Route 2: admin adds a certified garage directly. The owner must sign up with that email if they have no account yet.
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

-- ===== Listings =====
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

-- Create or update a draft. Vehicle record is made the first time Saaz sees the VIN.
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

-- Garage line order: same country, not the seller's own garage, not tried before for this car.
-- Nearest region first, then fewest open jobs, then longest certified.
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

-- Close a conversation with a status and bring in the next garage
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

-- Timeouts and expiry are applied whenever someone loads a dashboard (no scheduler needed).
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

-- Live cars: price changes stay live. Any other change goes back to draft for a new Saaz review, and is blocked while offers are open.
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
  if l.status not in ('live','re_review_due') then raise exception 'Only live cars use this. Cars in inspection must be withdrawn to edit.'; end if;
  if exists (select 1 from public.deals where listing_id = l.id and status in ('negotiating','agreed','on_hold')) then
    raise exception 'Close or reject open offers before changing anything other than the price.'; end if;
  update public.listings set status = 'draft', updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'taken off sale to edit; needs a new Saaz inspection');
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

-- ===== Conversations (garage line) =====
-- Contact details typed before agreement are hidden.
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
    perform public.notify_garage(c.garage_id,'seller_agreed','The seller of ' || l.ref || ' agreed. Set an inspection date and start the inspection when the car is with you.','#/garage/job/' || p_conv);
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
    perform public.notify(x,'review_date','Inspection date for ' || l.ref || ': ' || to_char(p_date,'Dy DD Mon YYYY') || '.','#/my/cars/' || l.id) from public.seller_side_users(l) x;
    perform public.audit('garage','conversation',p_conv::text,'inspection date set', jsonb_build_object('after',p_date));
  else
    raise exception 'That action is not available now.';
  end if;
end $$;

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
