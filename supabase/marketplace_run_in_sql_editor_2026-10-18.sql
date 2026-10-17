-- 18 Oct 2026. Run in the Supabase SQL Editor ONLY AFTER you have added your authenticator on the staff page.
-- Part 10 (admin needs the pinned authenticator), then pins your one authenticator. Safe to run twice.

-- Part 10: admin access needs the admin's own authenticator app.
-- is_admin() is true only when ALL of these hold for the request:
--   1. the person is in public.admins and has a pinned authenticator (admins.mfa_factor_id)
--   2. this session reached aal2 using THAT pinned authenticator (auth.sessions.factor_id), not any other one
--   3. the authenticator code was entered in the last 12 hours (amr "totp" timestamp in the token)
-- Every admin policy and admin function already calls is_admin(), so they all get this rule.
-- A stolen password alone gives nothing. A stolen password plus a new authenticator added by the thief gives nothing.
-- The pin is set only from the SQL Editor (marketplace_10b_pin_admin_authenticator.sql). No app function can set it.

alter table public.admins add column if not exists mfa_factor_id uuid;
alter table public.admins add column if not exists mfa_pinned_at timestamptz;

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
                    where e->>'method' = 'totp'), 0) > extract(epoch from now() - interval '12 hours'))
$$;

-- The pin column is never readable or writable from the app
revoke all on public.admins from anon, authenticated;
grant select (user_id, name, added_at) on public.admins to authenticated;

-- Called by the app right after an admin enters their code. Records the sign-in, with the session's IP and browser.
create or replace function public.admin_signed_in() returns void
language plpgsql security definer set search_path = public as $$
declare s record;
begin
  if not public.is_admin() then raise exception 'Not available.'; end if;
  select ip, user_agent into s from auth.sessions where id = nullif(auth.jwt()->>'session_id', '')::uuid;
  perform public.audit('admin', 'account', auth.uid()::text, 'admin signed in with authenticator',
    jsonb_build_object('ip', host(s.ip), 'browser', left(coalesce(s.user_agent, ''), 200)));
end $$;
revoke execute on function public.admin_signed_in() from public, anon;
grant execute on function public.admin_signed_in() to authenticated;

-- Run in the Supabase SQL Editor AFTER the admin has added their authenticator on the staff sign-in page.
-- Pins that one authenticator to the admin account. Change the email if pinning a different admin.
-- Refuses if the account has no verified authenticator, or more than one (then remove the extra one first).
do $$
declare u uuid; n int; f uuid; fc timestamptz;
begin
  select id into u from auth.users where lower(email) = lower('ssemujjujames@saazinvestmentsltd.com');
  if u is null or not exists (select 1 from public.admins where user_id = u) then raise exception 'That email is not an admin.'; end if;
  select count(*) into n from auth.mfa_factors where user_id = u and status = 'verified' and factor_type = 'totp';
  if n <> 1 then raise exception 'Expected exactly 1 verified authenticator, found %.', n; end if;
  select id, created_at into f, fc from auth.mfa_factors where user_id = u and status = 'verified' and factor_type = 'totp';
  update public.admins set mfa_factor_id = f, mfa_pinned_at = now() where user_id = u;
  insert into public.audit_log (actor_id, actor_role, entity, entity_id, action, detail)
  values (u, 'admin', 'account', u::text, 'admin authenticator pinned from SQL Editor', jsonb_build_object('factor_added', fc));
  raise notice 'Pinned the authenticator added at %', fc;
end $$;
