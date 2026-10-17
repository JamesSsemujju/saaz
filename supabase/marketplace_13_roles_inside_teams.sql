-- Part 13: access inside each team.
--   Garage: the owner sees and runs everything of the garage. An inspector sees only the jobs the owner gave them and the
--           reports they wrote. Offered cars, the team list and other inspectors' work are the owner's.
--   Saaz:   Saaz never changes an inspection report. Saaz staff can SUPPORT or OBJECT to a report, always with a reason,
--           and the garage can reply. All of it shows on the report. Voiding is replaced by an objection.
--   Saaz team: two roles. Admin (everything, including settings and the Saaz team) and Staff (daily work: cars, garages,
--           deals, acting for sellers and buyers, supporting or objecting to reports). Admins add, change and remove staff.
-- Run in the Supabase SQL Editor (it replaces table rules, which the database tool can't do).

-- ===== Garage: owner and inspector =====
alter table public.conversations add column if not exists inspector_id uuid references auth.users(id);

-- My role in my CERTIFIED garage (null if none)
create or replace function public.my_garage_role() returns text
language sql stable security definer set search_path = public as $$
  select m.role from public.garage_members m join public.garages g on g.id = m.garage_id
  where m.user_id = auth.uid() and m.status <> 'removed' and g.status = 'certified' limit 1
$$;
-- Can I see this garage job? Owner: every job of the garage. Inspector: only jobs given to them.
create or replace function public.garage_sees(p_garage uuid, p_inspector uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select p_garage = public.my_garage_id() and (public.my_garage_role() = 'owner' or p_inspector = auth.uid())
$$;

drop policy if exists "seller, garage, admin" on public.conversations;
create policy "seller, garage owner or the job's inspector, admin" on public.conversations for select
  using (public.is_admin() or public.garage_sees(garage_id, inspector_id) or public.is_seller_of(listing_id));

drop policy if exists "current inspection of a public car, own garage, seller, admin" on public.reviews;
create policy "current inspection of a public car, garage owner or its author, seller, admin" on public.reviews for select
  using ((status = 'issued' and public.is_public_review(id)) or public.is_admin()
    or (garage_id = public.my_garage_id() and (public.my_garage_role() = 'owner' or member_id = auth.uid()))
    or public.is_seller_of(listing_id));

drop policy if exists "own team or admin" on public.garage_members;
-- Am I the owner of this garage's team? (a function, so the team rule doesn't read its own table)
create or replace function public.i_own_team(p_garage uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.garage_members where user_id = auth.uid() and garage_id = p_garage and role = 'owner' and status <> 'removed')
$$;
create policy "own row, the garage owner, admin" on public.garage_members for select
  using (public.is_admin() or user_id = auth.uid() or public.i_own_team(garage_id));

create or replace function public.garage_on_listing(p_listing uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.conversations c where c.listing_id = p_listing and public.garage_sees(c.garage_id, c.inspector_id))
$$;

create or replace function public.can_read_messages(p_conv uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.conversations c join public.listings l on l.id = c.listing_id
    where c.id = p_conv and (public.garage_sees(c.garage_id, c.inspector_id) or l.seller_id = auth.uid() or (l.saaz_owned and public.is_admin())))
$$;

-- Garage notices go to the owners, and to the inspector of the job when the link is a job
create or replace function public.notify_garage(p_garage uuid, p_kind text, p_body text, p_link text default null) returns void
language sql security definer set search_path = public as $$
  insert into public.notifications (user_id, kind, body, link, channels)
  select distinct x, p_kind, p_body, p_link, '{app,sms}'::text[] from (
    select user_id x from public.garage_members where garage_id = p_garage and status <> 'removed' and role = 'owner'
    union
    select c.inspector_id from public.conversations c
    where p_link like '#/garage/job/%' and c.id::text = substr(p_link, 14) and c.garage_id = p_garage and c.inspector_id is not null
  ) t
$$;

create or replace function public.garage_jobs() returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
declare gid uuid := public.my_garage_id();
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  return query
  select jsonb_build_object('conversation', to_jsonb(c), 'listing',
      jsonb_build_object('id',l.id,'ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'region',l.region,'mileage',l.mileage,'status',l.status,'photos',l.photos),
      'inspector', (select name from public.profiles where id = c.inspector_id),
      'mine', c.inspector_id = auth.uid(),
      'draft', (select jsonb_build_object('id',r.id,'doc_no',r.doc_no,'member',p.name,'mine',r.member_id = auth.uid())
                from public.reviews r join public.profiles p on p.id = r.member_id
                where r.listing_id = l.id and r.garage_id = gid and r.status = 'draft' limit 1),
      'unread_from_seller', (select count(*) from public.messages m where m.conversation_id = c.id and m.side = 'seller'))
  from public.conversations c join public.listings l on l.id = c.listing_id
  where public.garage_sees(c.garage_id, c.inspector_id)
  order by (c.status in ('in_play','agreed')) desc, c.opened_at desc;
end $$;

-- The owner gives a job to a team member (or takes it back with null)
create or replace function public.assign_job(p_conv uuid, p_member uuid) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); c public.conversations; l public.listings; who text; writer text;
begin
  select * into c from public.conversations where id = p_conv;
  if c is null or c.garage_id is distinct from public.my_garage_id() or public.my_garage_role() <> 'owner' then
    raise exception 'Only the garage owner can give out jobs.'; end if;
  if c.status not in ('in_play','agreed') then raise exception 'This job is closed.'; end if;
  if p_member is not null and not exists (select 1 from public.garage_members where garage_id = c.garage_id and user_id = p_member and status = 'active') then
    raise exception 'Choose an active member of your garage.'; end if;
  select p.name into writer from public.reviews r join public.profiles p on p.id = r.member_id
    where r.listing_id = c.listing_id and r.garage_id = c.garage_id and r.status = 'draft' and r.member_id is distinct from p_member;
  if writer is not null then raise exception '% is writing this inspection report. They discard the draft first.', writer; end if;
  update public.conversations set inspector_id = p_member where id = p_conv;
  select * into l from public.listings where id = c.listing_id;
  select name into who from public.profiles where id = p_member;
  if p_member is not null and p_member <> u then
    perform public.notify(p_member, 'job_assigned', 'You have a new job: ' || l.year || ' ' || l.make || ' ' || l.model || ' (' || l.ref || ').', '#/garage/job/' || p_conv, '{app,sms}');
  end if;
  perform public.audit('garage', 'conversation', p_conv::text, case when p_member is null then 'job taken back by the owner' else 'job given to ' || who end);
end $$;
revoke execute on function public.assign_job(uuid, uuid) from public, anon;
grant execute on function public.assign_job(uuid, uuid) to authenticated;

-- Decline and release are the owner's decisions; the inspection date can be set by the owner or the job's inspector
create or replace function public.garage_respond(p_conv uuid, p_action text, p_date date default null) returns void
language plpgsql security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
declare c public.conversations; l public.listings;
begin
  perform public.require_user();
  select * into c from public.conversations where id = p_conv;
  if c is null or not public.garage_sees(c.garage_id, c.inspector_id) then raise exception 'Not your job.'; end if;
  if p_action in ('decline','release') and public.my_garage_role() <> 'owner' then raise exception 'Only the garage owner can decline or release a job.'; end if;
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

create or replace function public.send_message(p_conv uuid, p_body text) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); c public.conversations; l public.listings; side text; body text;
begin
  select * into c from public.conversations where id = p_conv;
  select * into l from public.listings where id = c.listing_id;
  if public.is_listing_seller(l) then side := 'seller';
  elsif public.garage_sees(c.garage_id, c.inspector_id) then side := 'garage';
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

-- Only the job's inspector writes its report. An owner starting an unassigned job takes it.
create or replace function public.start_review(p_listing uuid) returns uuid
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid := public.my_garage_id(); l public.listings; rid uuid; other text; c public.conversations;
begin
  if gid is null then raise exception 'Sign in as a member of a certified garage.'; end if;
  select * into l from public.listings where id = p_listing;
  select * into c from public.conversations where listing_id = p_listing and garage_id = gid and status = 'agreed' limit 1;
  if c is null then raise exception 'This car is not booked with your garage.'; end if;
  if c.inspector_id is null and public.my_garage_role() = 'owner' then
    update public.conversations set inspector_id = u where id = c.id; c.inspector_id := u;
    perform public.audit('garage','conversation',c.id::text,'job taken by the owner');
  end if;
  if c.inspector_id is distinct from u then raise exception 'This job is given to someone else in your garage.'; end if;
  select p.name into other from public.reviews r join public.profiles p on p.id = r.member_id
    where r.listing_id = p_listing and r.garage_id = gid and r.status = 'draft' and r.member_id <> u;
  if other is not null then raise exception 'In progress: % is writing this inspection report.', other; end if;
  select id into rid from public.reviews where listing_id = p_listing and member_id = u and status = 'draft';
  if rid is null then
    -- The inspection ID is given when the inspection starts, and stays the report's number when it is issued
    insert into public.reviews (listing_id, vehicle_id, garage_id, member_id, doc_no)
    values (p_listing, l.vehicle_id, gid, u, 'SZR-' || to_char(now() at time zone 'Africa/Kampala','YYYY') || '-' || lpad(nextval('public.review_doc_seq')::text, 6, '0'))
    returning id into rid;
    perform public.audit('garage','review',rid::text,'inspection started', jsonb_build_object('listing',l.ref,'inspection_id',(select doc_no from public.reviews where id = rid)));
  end if;
  return rid;
end $$;

-- The team list is the owner's (and Saaz's)
create or replace function public.garage_team(p_garage uuid default null) returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
declare gid uuid := coalesce(p_garage, public.my_team_garage()); hrs int := coalesce((public.setting('email_link_hours')#>>'{}')::int, 24);
  gs text;
begin
  if not (public.is_admin() or (gid = public.my_team_garage() and exists (select 1 from public.garage_members
          where user_id = auth.uid() and garage_id = gid and role = 'owner' and status <> 'removed'))) then
    raise exception 'Only the garage owner sees the team.'; end if;
  select status into gs from public.garages where id = gid;
  return query
  select jsonb_build_object('id',m.id,'kind','member','name',p.name,'email',p.email,'role',m.role,'status',m.status,'user_id',m.user_id,'added_at',m.added_at,
    'invited_at',u.invited_at,'link_expires_at',u.invited_at + make_interval(hours => hrs),'accepted_at',m.accepted_at,'garage_status',gs)
  from public.garage_members m join public.profiles p on p.id = m.user_id left join auth.users u on u.id = m.user_id where m.garage_id = gid
  union all
  select jsonb_build_object('id',i.id,'kind','invite','name',coalesce(i.name,''),'email',i.email,'role',i.role,'status','not_sent','user_id',null,'added_at',i.created_at,
    'invited_at',null,'link_expires_at',null,'accepted_at',null,'garage_status',gs)
  from public.garage_invites i where i.garage_id = gid and not i.used and i.revoked_at is null;
end $$;

-- ===== Saaz team: Admin and Staff =====
alter table public.admins add column if not exists role text not null default 'admin';
alter table public.admins add column if not exists added_by uuid references auth.users(id);
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'admins_role_check') then
    alter table public.admins add constraint admins_role_check check (role in ('admin','staff')); end if;
end $$;

create or replace function public.is_full_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select public.is_admin() and exists (select 1 from public.admins where user_id = auth.uid() and role = 'admin')
$$;
create or replace function public.require_full_admin() returns uuid
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Admins only.'; end if;
  if not public.is_full_admin() then raise exception 'Only a Saaz admin can do this (not staff).'; end if;
  return auth.uid();
end $$;

create or replace function public.my_roles() returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'signed_in', auth.uid() is not null,
    'admin', public.is_admin(),
    'full_admin', public.is_full_admin(),
    'admin_account', exists (select 1 from public.admins where user_id = auth.uid()),
    'admin_role', (select role from public.admins where user_id = auth.uid()),
    'profile', (select to_jsonb(p) from public.profiles p where p.id = auth.uid()),
    'garage', (select jsonb_build_object('id',g.id,'name',g.name,'status',g.status,'status_note',g.status_note,
                 'member_role',m.role,'member_status',m.status,'accepted_at',m.accepted_at)
               from public.garage_members m join public.garages g on g.id = m.garage_id
               where m.user_id = auth.uid() and m.status <> 'removed' limit 1))
$$;

-- Settings: admins only
create or replace function public.admin_set_setting(p_key text, p_value jsonb) returns void
language plpgsql security definer set search_path = public as $$
declare before jsonb;
begin
  perform public.require_full_admin();
  select value into before from public.settings where key = p_key;
  if before is null then raise exception 'Unknown setting.'; end if;
  update public.settings set value = p_value, updated_at = now() where key = p_key;
  perform public.audit('admin','setting',p_key,'changed', jsonb_build_object('before',before,'after',p_value));
end $$;

-- Account flags: staff can mark trusted or phone verified; suspending is for admins; Saaz team changes go through the team page
create or replace function public.admin_set_user(p_user uuid, p_field text, p_value boolean, p_note text default null) returns void
language plpgsql security definer set search_path = public as $$
declare a uuid := public.require_admin(); before boolean;
begin
  if p_user = a then raise exception 'You cannot change your own access.'; end if;
  if p_field = 'trusted' then select trusted into before from public.profiles where id = p_user; update public.profiles set trusted = p_value where id = p_user;
  elsif p_field = 'suspended' then
    perform public.require_full_admin();
    select suspended into before from public.profiles where id = p_user;
    update public.profiles set suspended = p_value where id = p_user;
    if p_value then update public.listings set status = 'withdrawn', admin_note = 'Account suspended', updated_at = now()
      where seller_id = p_user and status in ('live','re_review_due','awaiting_approval','awaiting_review','review_booked'); end if;
  elsif p_field = 'phone_verified' then select phone_verified into before from public.profiles where id = p_user; update public.profiles set phone_verified = p_value where id = p_user;
  elsif p_field = 'admin' then raise exception 'Add or remove Saaz team members on the Saaz team page.';
  else raise exception 'Unknown field.'; end if;
  perform public.audit('admin','account',p_user::text,p_field, jsonb_build_object('before',before,'after',p_value,'note',p_note));
end $$;

create or replace function public.admin_staff_list() returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_admin();
  return query
  select jsonb_build_object('user_id',a.user_id,'name',p.name,'email',p.email,'role',a.role,'added_at',a.added_at,
    'pinned', a.mfa_factor_id is not null, 'pinned_at', a.mfa_pinned_at,
    'authenticators', (select count(*) from auth.mfa_factors f where f.user_id = a.user_id and f.status = 'verified' and f.factor_type = 'totp'),
    'authenticator_added_at', (select max(f.created_at) from auth.mfa_factors f where f.user_id = a.user_id and f.status = 'verified' and f.factor_type = 'totp'),
    'me', a.user_id = auth.uid())
  from public.admins a join public.profiles p on p.id = a.user_id order by a.role, p.name;
end $$;

create or replace function public.admin_add_staff(p_email text, p_role text) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := public.require_full_admin(); u uuid; n text;
begin
  if p_role not in ('admin','staff') then raise exception 'Choose Admin or Staff.'; end if;
  select id, name into u, n from public.profiles where email = lower(trim(p_email));
  if u is null then raise exception 'No Saaz account has this email. Ask them to create one first, then add them.'; end if;
  if exists (select 1 from public.admins where user_id = u) then raise exception 'Already on the Saaz team.'; end if;
  insert into public.admins (user_id, name, role, added_by) values (u, coalesce(nullif(n,''), p_email), p_role, me);
  perform public.notify(u, 'saaz_team_added', 'You were added to the Saaz team as ' || initcap(p_role) ||
    '. Sign in as Seller, open the menu under your initials and choose Admin panel to set up your authenticator.', '#/my/cars', '{app,email}');
  perform public.audit('admin','account',u::text,'added to the Saaz team', jsonb_build_object('role',p_role));
end $$;

create or replace function public.admin_set_staff_role(p_user uuid, p_role text) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := public.require_full_admin(); before text;
begin
  if p_user = me then raise exception 'You cannot change your own role.'; end if;
  if p_role not in ('admin','staff') then raise exception 'Choose Admin or Staff.'; end if;
  select role into before from public.admins where user_id = p_user;
  if before is null then raise exception 'Not on the Saaz team.'; end if;
  update public.admins set role = p_role where user_id = p_user;
  perform public.audit('admin','account',p_user::text,'Saaz team role changed', jsonb_build_object('before',before,'after',p_role));
end $$;

create or replace function public.admin_remove_staff(p_user uuid, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := public.require_full_admin(); r text;
begin
  if p_user = me then raise exception 'You cannot remove yourself.'; end if;
  if length(trim(coalesce(p_reason,''))) < 10 then raise exception 'Write the reason (10 characters or more).'; end if;
  select role into r from public.admins where user_id = p_user;
  if r is null then raise exception 'Not on the Saaz team.'; end if;
  delete from public.admins where user_id = p_user;
  delete from auth.sessions where user_id = p_user;  -- their Admin access ends now, on every device
  perform public.audit('admin','account',p_user::text,'removed from the Saaz team', jsonb_build_object('role',r,'reason',trim(p_reason)));
end $$;

-- An admin approves a staff member's authenticator in the app (the first admin's is pinned from the SQL Editor)
create or replace function public.admin_pin_staff_authenticator(p_user uuid) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := public.require_full_admin(); n int; f uuid; fc timestamptz;
begin
  if p_user = me then raise exception 'Another admin approves your authenticator.'; end if;
  if not exists (select 1 from public.admins where user_id = p_user) then raise exception 'Not on the Saaz team.'; end if;
  select count(*) into n from auth.mfa_factors where user_id = p_user and status = 'verified' and factor_type = 'totp';
  if n <> 1 then raise exception 'Expected exactly 1 authenticator on their account, found %. They remove extras first.', n; end if;
  select id, created_at into f, fc from auth.mfa_factors where user_id = p_user and status = 'verified' and factor_type = 'totp';
  update public.admins set mfa_factor_id = f, mfa_pinned_at = now() where user_id = p_user;
  perform public.notify(p_user, 'saaz_team_ready', 'Your authenticator is approved. Choose Admin panel in your menu to start.', '#/my/cars', '{app}');
  perform public.audit('admin','account',p_user::text,'authenticator approved', jsonb_build_object('added_at',fc));
end $$;

revoke execute on function public.admin_staff_list() from public, anon;
revoke execute on function public.admin_add_staff(text, text) from public, anon;
revoke execute on function public.admin_set_staff_role(uuid, text) from public, anon;
revoke execute on function public.admin_remove_staff(uuid, text) from public, anon;
revoke execute on function public.admin_pin_staff_authenticator(uuid) from public, anon;
grant execute on function public.admin_staff_list(), public.admin_add_staff(text, text), public.admin_set_staff_role(uuid, text),
  public.admin_remove_staff(uuid, text), public.admin_pin_staff_authenticator(uuid) to authenticated;

-- ===== Reports: Saaz supports or objects, never edits =====
create table if not exists public.review_opinions (
  id uuid primary key default gen_random_uuid(),
  review_id uuid not null references public.reviews(id) on delete cascade,
  by_user uuid references auth.users(id),
  stance text not null check (stance in ('support','object','garage_reply')),
  reason text not null,
  created_at timestamptz not null default now()
);
alter table public.review_opinions enable row level security;
drop policy if exists "saaz, the garage and the seller read opinions" on public.review_opinions;
create policy "saaz, the garage and the seller read opinions" on public.review_opinions for select
  using (public.is_admin() or exists (select 1 from public.reviews r where r.id = review_id
    and ((r.garage_id = public.my_garage_id() and (public.my_garage_role() = 'owner' or r.member_id = auth.uid())) or public.is_seller_of(r.listing_id))));
revoke insert, update, delete on public.review_opinions from anon, authenticated;

-- Latest Saaz stance on a report: 'support', 'object' or null
create or replace function public.saaz_stance(p_review uuid) returns text
language sql stable security definer set search_path = public as $$
  select stance from public.review_opinions where review_id = p_review and stance in ('support','object') order by created_at desc limit 1
$$;
create or replace function public.opinions_of(p_review uuid) returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object('stance',stance,'reason',reason,'at',created_at,
    'by', case when stance = 'garage_reply' then 'Garage' else 'Saaz' end) order by created_at), '[]'::jsonb)
  from public.review_opinions where review_id = p_review
$$;

create or replace function public.review_opinion(p_review uuid, p_stance text, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := public.require_admin(); r public.reviews; l public.listings; why text := trim(coalesce(p_reason,'')); cid uuid;
begin
  if p_stance not in ('support','object') then raise exception 'Choose support or object.'; end if;
  if length(why) < 10 then raise exception 'Write the reason (10 characters or more). The garage and the seller see it.'; end if;
  select * into r from public.reviews where id = p_review;
  if r is null or r.status not in ('issued','superseded') then raise exception 'Only an issued inspection report can be supported or objected to.'; end if;
  insert into public.review_opinions (review_id, by_user, stance, reason) values (p_review, me, p_stance, why);
  select * into l from public.listings where id = r.listing_id;
  if p_stance = 'object' and l.current_review_id = r.id and l.status in ('live','re_review_due') then
    -- Off sale while Saaz's objection stands; open offers wait
    update public.listings set status = 'awaiting_approval', updated_at = now() where id = l.id;
    update public.deals set status = 'on_hold', updated_at = now() where listing_id = l.id and status = 'negotiating';
  end if;
  select id into cid from public.conversations where listing_id = l.id and garage_id = r.garage_id order by opened_at desc limit 1;
  perform public.notify(t.x, 'review_' || p_stance, 'Saaz ' || case p_stance when 'object' then 'objected to' else 'supports' end ||
      ' inspection report ' || r.doc_no || ' (' || l.ref || '): ' || why, '#/garage/job/' || cid, '{app,email}')
    from (select r.member_id x union select user_id from public.garage_members where garage_id = r.garage_id and role = 'owner' and status <> 'removed') t;
  perform public.notify(x, 'review_' || p_stance, 'Saaz ' || case p_stance when 'object' then 'objected to' else 'supports' end ||
      ' the inspection report for ' || l.ref || ': ' || why, '#/my/cars/' || l.id, '{app,email}') from public.seller_side_users(l) x;
  perform public.audit('admin','review',r.id::text, case p_stance when 'object' then 'Saaz objected' else 'Saaz supported' end, jsonb_build_object('reason',why));
end $$;
revoke execute on function public.review_opinion(uuid, text, text) from public, anon;
grant execute on function public.review_opinion(uuid, text, text) to authenticated;

create or replace function public.garage_reply_opinion(p_review uuid, p_text text) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); r public.reviews; l public.listings; t text := trim(coalesce(p_text,''));
begin
  select * into r from public.reviews where id = p_review;
  if r is null or r.garage_id is distinct from public.my_garage_id() or not (public.my_garage_role() = 'owner' or r.member_id = u) then
    raise exception 'Only the garage owner or the report''s author can reply.'; end if;
  if public.saaz_stance(p_review) is null then raise exception 'Saaz has not commented on this report.'; end if;
  if length(t) < 10 then raise exception 'Write your reply (10 characters or more).'; end if;
  insert into public.review_opinions (review_id, by_user, stance, reason) values (p_review, u, 'garage_reply', t);
  select * into l from public.listings where id = r.listing_id;
  perform public.notify_admins('review_reply', 'The garage replied about report ' || r.doc_no || ' (' || l.ref || '): ' || t, '#/admin/car/' || l.id);
  perform public.audit('garage','review',r.id::text,'garage replied to Saaz', jsonb_build_object('reply',t));
end $$;
revoke execute on function public.garage_reply_opinion(uuid, text) from public, anon;
grant execute on function public.garage_reply_opinion(uuid, text) to authenticated;

-- Voiding is replaced: Saaz objects with a reason instead, and the report stays exactly as the garage wrote it
create or replace function public.admin_void_review(p_review uuid, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
begin
  raise exception 'Saaz does not change inspection reports. Object to it with a reason instead.';
end $$;

-- Approving needs no standing objection; requesting a new inspection no longer touches the report itself
create or replace function public.admin_decide_listing(p_listing uuid, p_decision text, p_note text default null, p_new_review boolean default false) returns void
language plpgsql security definer set search_path = public as $$
declare l public.listings; r public.reviews;
begin
  perform public.require_admin();
  select * into l from public.listings where id = p_listing;
  select * into r from public.reviews where id = l.current_review_id;
  if p_decision in ('changes','reject','unlist') and coalesce(trim(p_note),'') = '' then raise exception 'A note to the seller is required.'; end if;
  if p_decision = 'approve' then
    if l.status <> 'awaiting_approval' then raise exception 'Nothing to approve.'; end if;
    if r.verdict = 'fail' then raise exception 'A safety Fail cannot be approved.'; end if;
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
end $$;

-- The report and the public check both show what Saaz said about the report, and the garage's replies
create or replace function public.review_document(p_code text) returns jsonb
language plpgsql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
declare r public.reviews; l public.listings; v public.vehicles;
begin
  select * into r from public.reviews where verify_code = upper(trim(p_code)) and status <> 'draft';
  if r is null then return null; end if;
  select * into l from public.listings where id = r.listing_id;
  select * into v from public.vehicles where id = r.vehicle_id;
  return jsonb_build_object('review', to_jsonb(r) - 'notes' || jsonb_build_object('notes', r.notes),
    'status', case when r.status = 'issued' and r.valid_until < current_date then 'expired' else r.status end,
    'intact', encode(sha256(convert_to(public.review_canonical(r),'UTF8')),'hex') = r.fingerprint,
    'saaz_stance', public.saaz_stance(r.id), 'opinions', public.opinions_of(r.id),
    'listing', jsonb_build_object('ref',l.ref,'make',l.make,'model',l.model,'year',l.year,'plate',l.plate,'colour',l.colour,'engine',l.engine,
       'fuel',l.fuel,'gearbox',l.gearbox,'body',l.body,'country',l.country,'mileage',l.mileage),
    'vehicle', jsonb_build_object('vin',v.vin,'source',v.source,'first_record_date',v.first_record_date,'import_mileage',v.import_mileage),
    'odometer', (select jsonb_agg(jsonb_build_object('km',o.km,'source',o.source,'at',o.recorded_at,'flagged',o.flagged) order by o.recorded_at)
                 from public.odometer_readings o where o.vehicle_id = v.id));
end $$;

create or replace function public.verify_review(p_code text) returns jsonb
language plpgsql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
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
    'garage', r.garage_name, 'member', r.member_name, 'fingerprint', r.fingerprint,
    'saaz_stance', public.saaz_stance(r.id), 'opinions', public.opinions_of(r.id));
end $$;

-- ===== Inspection IDs =====
-- Every inspection has its own ID from the moment it starts (start_review). A car can have many; each is separate.
-- issue_review keeps that ID as the report number (older drafts without one get one at issue, as before).
create or replace function public.issue_review(p_review uuid) returns jsonb
language plpgsql security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
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
    doc_no = coalesce(doc_no, 'SZR-' || to_char(now(),'YYYY') || '-' || lpad(nextval('public.review_doc_seq')::text, 6, '0')),
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

-- Open an inspection by its ID (garage: the owner, or the inspector who wrote it; Saaz staff: any)
create or replace function public.open_inspection(p_id text) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare r public.reviews;
begin
  perform public.require_user();
  select * into r from public.reviews where doc_no = upper(trim(p_id));
  if r is null or not (public.is_admin() or (r.garage_id = public.my_garage_id() and (public.my_garage_role() = 'owner' or r.member_id = auth.uid()))) then
    raise exception 'No inspection with this ID for you.'; end if;
  return jsonb_build_object('id', r.id, 'status', r.status, 'verify_code', r.verify_code, 'listing_id', r.listing_id);
end $$;
revoke execute on function public.open_inspection(text) from public, anon;
grant execute on function public.open_inspection(text) to authenticated;

-- Every inspection of this car (the vehicle, across all its listings), each with its own ID and garage.
-- Saaz staff and the seller see all; a garage owner sees its own garage's; an inspector sees their own.
create or replace function public.car_inspections(p_listing uuid) returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
declare l public.listings; sees_all boolean;
begin
  select * into l from public.listings where id = p_listing;
  if l is null then return; end if;
  sees_all := public.is_admin() or public.is_listing_seller(l);
  return query
  select jsonb_build_object('id', r.id, 'doc_no', r.doc_no, 'status', r.status, 'garage', coalesce(r.garage_name, g.name),
    'inspector', coalesce(r.member_name, p.name), 'verdict', r.verdict, 'score', r.score, 'issued_at', r.issued_at,
    'started_at', r.created_at, 'verify_code', r.verify_code, 'saaz_stance', public.saaz_stance(r.id), 'listing_ref', l2.ref)
  from public.reviews r join public.listings l2 on l2.id = r.listing_id join public.garages g on g.id = r.garage_id
    left join public.profiles p on p.id = r.member_id
  where r.vehicle_id = l.vehicle_id
    and (sees_all or (r.garage_id = public.my_garage_id() and (public.my_garage_role() = 'owner' or r.member_id = auth.uid())))
    and (r.status <> 'draft' or r.garage_id = public.my_garage_id() or public.is_admin())
  order by r.created_at;
end $$;
revoke execute on function public.car_inspections(uuid) from public, anon;
grant execute on function public.car_inspections(uuid) to authenticated;
