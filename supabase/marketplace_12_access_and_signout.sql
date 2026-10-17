-- Part 12: one entry point, admin entry from the account menu with password + authenticator, sign-out that really ends access,
-- and garage invite stages that don't imply certification.

-- Invite acceptance time (used by my_roles and the team list below)
alter table public.garage_members add column if not exists accepted_at timestamptz;
update public.garage_members set accepted_at = added_at where status = 'active' and accepted_at is null;

-- 1. Every write needs a live session. After sign-out Supabase removes the session row, so a copied token stops working for
--    every Saaz function straight away (reads through table rules still last until the token expires, up to 1 hour).
create or replace function public.require_user() returns uuid
language plpgsql stable security definer set search_path = public as $$
declare u uuid := auth.uid();
begin
  if u is null then raise exception 'Please sign in first.'; end if;
  if not exists (select 1 from auth.sessions s where s.id = nullif(auth.jwt()->>'session_id', '')::uuid and s.user_id = u) then
    raise exception 'Your session ended. Sign in again.'; end if;
  if exists (select 1 from public.profiles where id = u and suspended) then raise exception 'This account is suspended.'; end if;
  return u;
end $$;

-- 2. Admin needs, in THIS session: the pinned authenticator (part 10) AND a password entered in the last 12 hours.
--    The admin entry in the account menu always asks for both, which starts a new session.
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(auth.jwt()->>'aal', '') = 'aal2' and exists (
    select 1
    from public.admins a
    join auth.sessions s on s.id = nullif(auth.jwt()->>'session_id', '')::uuid and s.user_id = a.user_id
    where a.user_id = auth.uid()
      and a.mfa_factor_id is not null
      and s.aal::text = 'aal2'
      and s.factor_id = a.mfa_factor_id
      and coalesce((select max((e->>'timestamp')::bigint) from jsonb_array_elements(coalesce(auth.jwt()->'amr', '[]'::jsonb)) e
                    where e->>'method' = 'totp'), 0) > extract(epoch from now() - interval '12 hours')
      and coalesce((select max((e->>'timestamp')::bigint) from jsonb_array_elements(coalesce(auth.jwt()->'amr', '[]'::jsonb)) e
                    where e->>'method' = 'password'), 0) > extract(epoch from now() - interval '12 hours'))
$$;

-- 3. The account menu shows the admin entry only to admin accounts. 'admin_account' tells the person themselves only.
--    It gives no access: 'admin' (is_admin) is what every admin rule checks.
create or replace function public.my_roles() returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'signed_in', auth.uid() is not null,
    'admin', public.is_admin(),
    'admin_account', exists (select 1 from public.admins where user_id = auth.uid()),
    'profile', (select to_jsonb(p) from public.profiles p where p.id = auth.uid()),
    'garage', (select jsonb_build_object('id',g.id,'name',g.name,'status',g.status,'status_note',g.status_note,
                 'member_role',m.role,'member_status',m.status,'accepted_at',m.accepted_at)
               from public.garage_members m join public.garages g on g.id = m.garage_id
               where m.user_id = auth.uid() and m.status <> 'removed' limit 1))
$$;

-- 4. Failed admin checks are recorded (wrong password or wrong code at the admin entry), for admin accounts only.
create or replace function public.admin_verify_failed(p_stage text) returns void
language plpgsql security definer set search_path = public as $$
declare s record;
begin
  if not exists (select 1 from public.admins where user_id = auth.uid()) then return; end if;
  if p_stage not in ('password', 'code') then return; end if;
  select ip, user_agent into s from auth.sessions where id = nullif(auth.jwt()->>'session_id', '')::uuid;
  perform public.audit('admin', 'account', auth.uid()::text, 'admin check failed: ' || p_stage,
    jsonb_build_object('ip', host(s.ip), 'browser', left(coalesce(s.user_agent, ''), 200)));
end $$;
revoke execute on function public.admin_verify_failed(text) from public, anon;
grant execute on function public.admin_verify_failed(text) to authenticated;

-- 5. Garage invites: Invited -> Accepted (the person set their password) is separate from the garage being certified.

create or replace function public.accept_garage_invite() returns jsonb
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); m record;
begin
  select m2.*, g.status as gstatus into m from public.garage_members m2 join public.garages g on g.id = m2.garage_id
  where m2.user_id = u and m2.status <> 'removed' limit 1;
  if m is null then return jsonb_build_object('member', false); end if;
  if m.accepted_at is null then
    update public.garage_members set accepted_at = now() where id = m.id;
    perform public.audit('garage', 'member', m.id::text, 'accepted the invite', jsonb_build_object('garage', m.garage_id));
  end if;
  return jsonb_build_object('member', true, 'garage_status', m.gstatus);
end $$;
revoke execute on function public.accept_garage_invite() from public, anon;
grant execute on function public.accept_garage_invite() to authenticated;

create or replace function public.garage_sign_in() returns jsonb
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); m record;
begin
  select m2.*, g.status as gstatus, g.status_note, g.name as gname into m
  from public.garage_members m2 join public.garages g on g.id = m2.garage_id
  where m2.user_id = u and m2.status <> 'removed' limit 1;
  if m is null then return jsonb_build_object('ok',false,'message','This account is not on a garage team.'); end if;
  if m.accepted_at is null then
    update public.garage_members set accepted_at = now() where id = m.id;
    perform public.audit('garage','member',m.id::text,'accepted the invite', jsonb_build_object('garage', m.garage_id));
  end if;
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

-- Team list: invite stage and the garage's own approval stage, side by side
create or replace function public.garage_team(p_garage uuid default null) returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
declare gid uuid := coalesce(p_garage, public.my_team_garage()); hrs int := coalesce((public.setting('email_link_hours')#>>'{}')::int, 24);
  gs text;
begin
  if not (public.is_admin() or gid = public.my_team_garage()) then raise exception 'Not your garage.'; end if;
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

-- 6. Only a CERTIFIED garage's owner can add team members (before, the owner of a garage still waiting for approval could)
create or replace function public.add_garage_member(p_email text, p_name text, p_mobile text, p_role text) returns text
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); gid uuid; target uuid;
begin
  select m.garage_id into gid from public.garage_members m join public.garages g on g.id = m.garage_id
  where m.user_id = u and m.role = 'owner' and m.status = 'active' and g.status = 'certified';
  if gid is null then raise exception 'Only the owner of a certified garage can add members.'; end if;
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
