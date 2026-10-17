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
