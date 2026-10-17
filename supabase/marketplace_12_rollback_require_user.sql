-- ONLY if, after part 12, every signed-in action says "Your session ended. Sign in again." even right after signing in.
-- Puts require_user back to the part 2 version (no live-session check). Everything else in part 12 stays.
create or replace function public.require_user() returns uuid
language plpgsql stable security definer set search_path = public as $$
declare u uuid := auth.uid();
begin
  if u is null then raise exception 'Please sign in first.'; end if;
  if exists (select 1 from public.profiles where id = u and suspended) then raise exception 'This account is suspended.'; end if;
  return u;
end $$;
