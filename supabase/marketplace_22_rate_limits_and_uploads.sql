-- Part 22: request limits and upload rules (30 Oct 2026). Run after part 21. Safe to run twice.
-- From the 30 Oct security checklist, verified on the local copy (tests/db_rate_limit_test.py, tests/api_security_test.py).
--
-- 1. Request limits. Supabase Auth already limits sign-in, sign-up, password reset, OTP and email sends (dashboard,
--    Authentication > Rate Limits). The app's own database calls had no limit, so one account or script could send
--    thousands of messages, offers or garage applications, inflate view counts, or walk through inspection numbers.
--    One check now runs before every write to the API (Supabase's documented pgrst.db_pre_request hook): one place,
--    with every limit in one table, public.request_limits. Reads (GET) and calls to read-only functions are not counted,
--    except the three look-ups in 1d.
--    Counted per signed-in account, or per network address for visitors.
--    Over the limit the API answers 429 "Too many requests. Wait a few minutes and try again."
-- 2. Uploads (car-photos). Already: images only (webp, jpeg, png), 2 MB, only into your own folder.
--    Now also: the file name must be the shape the app makes (<your id>/<letters and digits>.<webp|jpg|jpeg|png>),
--    so no "..", no sub-folders, no odd characters; and at most 300 photos per account.

-- 1a. The limits (path = the API path; per_seconds = the window)
create table if not exists public.request_limits (path text primary key, max_hits int not null check (max_hits > 0),
  per_seconds int not null check (per_seconds > 0), note text);
alter table public.request_limits enable row level security;
revoke all on public.request_limits from public, anon, authenticated;
insert into public.request_limits (path, max_hits, per_seconds, note) values
  ('*',                         600, 600,   'Any other write: 600 per 10 minutes'),
  ('/rpc/send_message',          40, 600,   'Messages between garage and seller'),
  ('/rpc/make_offer',            10, 3600,  'New offers'),
  ('/rpc/deal_action',           60, 3600,  'Counter, accept, decline in a deal'),
  ('/rpc/apply_garage',           5, 86400, 'Garage applications'),
  ('/rpc/resubmit_garage',       10, 86400, 'Garage re-applications'),
  ('/rpc/add_garage_member',     30, 3600,  'Garage invites'),
  ('/rpc/save_listing',         120, 3600,  'Saving a listing'),
  ('/rpc/submit_listing',        20, 3600,  'Sending a listing for inspection'),
  ('/rpc/toggle_save',          200, 3600,  'Saving cars'),
  ('/rpc/record_view',          300, 3600,  'Car page views'),
  ('/rpc/lookup_inspection',     60, 600,   'Look up an inspection ID'),
  ('/rpc/verify_review',         60, 600,   'Verify a report code'),
  ('/rpc/review_document',      120, 600,   'Open a report'),
  ('/rpc/vin_lookup',            60, 3600,  'VIN look-ups'),
  ('/rpc/update_profile',        30, 3600,  'Profile changes'),
  ('/rpc/build_submit',         120, 3600,  'Build Assistant comments'),
  ('/rpc/admin_verify_failed',   20, 3600,  'Failed admin checks recorded')
on conflict (path) do nothing;

-- 1b. The hits (kept one day)
create table if not exists public.request_hits (who text not null, path text not null, at timestamptz not null default now());
create index if not exists request_hits_who_path_at on public.request_hits (who, path, at);
alter table public.request_hits enable row level security;
revoke all on public.request_hits from public, anon, authenticated;

-- 1c. The check. Runs as its owner so it can count; the API roles may call it because PostgREST runs it as them.
create or replace function public.check_request() returns void language plpgsql security definer set search_path = public as $$
declare
  v_method text := upper(coalesce(current_setting('request.method', true), ''));
  v_path text := coalesce(current_setting('request.path', true), '');
  v_headers json := coalesce(nullif(current_setting('request.headers', true), ''), '{}')::json;
  v_who text; v_ip text; v_lim public.request_limits; v_n int;
begin
  if v_method not in ('POST', 'PATCH', 'PUT', 'DELETE') then return; end if;     -- reads are not counted (and run read-only)
  if current_setting('transaction_read_only', true) = 'on' then return; end if;  -- calls to read-only functions can't be counted here (see 1d)
  v_ip := coalesce(nullif(v_headers->>'cf-connecting-ip', ''), nullif(trim(split_part(v_headers->>'x-forwarded-for', ',', 1)), ''),
                   nullif(v_headers->>'x-real-ip', ''), 'unknown');
  v_who := coalesce(auth.uid()::text, 'ip:' || v_ip);
  select * into v_lim from public.request_limits where path = v_path;
  if v_lim is null then select * into v_lim from public.request_limits where path = '*'; v_path := '*'; end if;
  if v_lim is null then return; end if;
  select count(*) into v_n from public.request_hits h
    where h.who = v_who and h.path = v_path and h.at > now() - make_interval(secs => v_lim.per_seconds);
  if v_n >= v_lim.max_hits then
    raise sqlstate 'PGRST' using
      message = json_build_object('code', 'PT429', 'message', 'Too many requests. Wait a few minutes and try again.')::text,
      detail = json_build_object('status', 429, 'headers', json_build_object('Retry-After', '120'))::text;
  end if;
  insert into public.request_hits (who, path) values (v_who, v_path);
  if random() < 0.01 then delete from public.request_hits where at < now() - interval '1 day'; end if;
end $$;
revoke execute on function public.check_request() from public;
grant execute on function public.check_request() to anon, authenticated;

-- Register it. Supabase's API connects as "authenticator"; the local test stack sets db-pre-request in its config instead.
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'authenticator') then
    execute format('alter role authenticator set pgrst.db_pre_request = %L', 'public.check_request');
  end if;
end $$;

-- 1d. PostgREST runs calls to read-only (stable) functions in a read-only transaction, where nothing can be counted.
--     The three look-ups a script could use to walk through inspection numbers and report codes are marked volatile,
--     so their calls are counted. They change nothing; this only changes how the API runs them.
alter function public.lookup_inspection(text) volatile;
alter function public.verify_review(text) volatile;
alter function public.review_document(text) volatile;

-- 2. Uploads. Photos an account has uploaded, counted as the database owner (the uploader can't read storage rows).
create or replace function public.my_photo_count() returns int language sql stable security definer set search_path = public as $$
  select count(*)::int from storage.objects o where o.bucket_id = 'car-photos' and o.owner_id = (auth.uid())::text $$;
revoke execute on function public.my_photo_count() from public, anon;
grant execute on function public.my_photo_count() to authenticated;

drop policy if exists "sellers upload own photos" on storage.objects;
create policy "sellers upload own photos" on storage.objects for insert to authenticated with check (
  bucket_id = 'car-photos'
  and (storage.foldername(name))[1] = (auth.uid())::text
  and name ~ ('^' || (auth.uid())::text || '/[a-z0-9]{6,40}\.(webp|jpe?g|png)$')
  and public.my_photo_count() < 300);
drop policy if exists "admins upload photos" on storage.objects;
create policy "admins upload photos" on storage.objects for insert with check (
  bucket_id = 'car-photos' and public.is_admin() and name ~ '^[0-9a-f-]{36}/[a-z0-9]{6,40}\.(webp|jpe?g|png)$');

-- Make the API pick up the hook and the look-ups' new setting
notify pgrst, 'reload config';
notify pgrst, 'reload schema';

-- Check (run after): the hook is set, and the two upload policies
-- select rolconfig from pg_roles where rolname = 'authenticator';
-- select policyname, with_check from pg_policies where schemaname = 'storage' and cmd = 'INSERT';
