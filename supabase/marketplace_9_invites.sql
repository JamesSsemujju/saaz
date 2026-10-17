-- Saaz marketplace, part 9: invites that can be resent, revoked and timed (17 Oct 2026).
-- Adds two columns and one setting, replaces three functions, adds one. Removes nothing.

-- How long links in Saaz emails work. Must match Supabase: Authentication > Sign In / Providers > Email > Email OTP Expiration.
insert into public.settings (key, value, note)
values ('email_link_hours', '24'::jsonb, 'Hours a link in a Saaz email works. Keep equal to Email OTP Expiration in Supabase Auth (86400 seconds = 24).')
on conflict (key) do nothing;

alter table public.garage_invites add column if not exists revoked_at timestamptz;
alter table public.garage_invites add column if not exists revoked_by uuid references public.profiles(id);

-- Sign-up: revoked invites no longer make a membership
create or replace function public.handle_new_user() returns trigger language plpgsql security definer set search_path = public as $$
declare inv record;
begin
  insert into public.profiles (id, email, name, country, mobile)
  values (new.id, lower(new.email), coalesce(new.raw_user_meta_data->>'name',''),
          nullif(new.raw_user_meta_data->>'country',''), nullif(new.raw_user_meta_data->>'mobile',''));
  for inv in select * from public.garage_invites where lower(email) = lower(new.email) and not used and revoked_at is null loop
    insert into public.garage_members (garage_id, user_id, role) values (inv.garage_id, new.id, inv.role) on conflict do nothing;
    update public.garage_invites set used = true where id = inv.id;
  end loop;
  return new;
end $$;

-- Team list: invite times and link expiry, so owners and admins can see what is waiting
create or replace function public.garage_team(p_garage uuid default null) returns setof jsonb language plpgsql stable security definer set search_path = public as $$
declare gid uuid := coalesce(p_garage, public.my_team_garage()); hrs int := coalesce((public.setting('email_link_hours')#>>'{}')::int, 24);
begin
  if not (public.is_admin() or gid = public.my_team_garage()) then raise exception 'Not your garage.'; end if;
  return query
  select jsonb_build_object('id',m.id,'kind','member','name',p.name,'email',p.email,'role',m.role,'status',m.status,'user_id',m.user_id,'added_at',m.added_at,
    'invited_at',u.invited_at,'link_expires_at',u.invited_at + make_interval(hours => hrs))
  from public.garage_members m join public.profiles p on p.id = m.user_id left join auth.users u on u.id = m.user_id where m.garage_id = gid
  union all
  select jsonb_build_object('id',i.id,'kind','invite','name',coalesce(i.name,''),'email',i.email,'role',i.role,'status','not_sent','user_id',null,'added_at',i.created_at,
    'invited_at',null,'link_expires_at',null)
  from public.garage_invites i where i.garage_id = gid and not i.used and i.revoked_at is null;
end $$;

-- Revoke an invite that has no account yet (owner of that garage, or admin)
create or replace function public.revoke_garage_invite(p_invite uuid) returns void language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); i public.garage_invites;
begin
  select * into i from public.garage_invites where id = p_invite;
  if i.id is null or i.used or i.revoked_at is not null then raise exception 'This invite is no longer waiting.'; end if;
  if not (public.is_admin() or exists (select 1 from public.garage_members where user_id = u and garage_id = i.garage_id and role = 'owner' and status = 'active')) then
    raise exception 'Only an admin or this garage''s owner can revoke this invite.'; end if;
  update public.garage_invites set revoked_at = now(), revoked_by = u where id = p_invite;
  perform public.audit(case when public.is_admin() then 'admin' else 'garage' end,'member',i.email,'invite revoked', jsonb_build_object('garage',i.garage_id,'role',i.role));
end $$;
revoke execute on function public.revoke_garage_invite(uuid) from public, anon;
grant execute on function public.revoke_garage_invite(uuid) to authenticated;
