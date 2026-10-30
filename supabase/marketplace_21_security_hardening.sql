-- Part 21: security hardening (30 Oct 2026). Run after parts 1 to 20. Safe to run twice.
-- Found in the 30 Oct security audit and confirmed against the live project (read-only) and the local copy
-- (tests/db_security_test.py). Nothing here changes what anyone may legitimately do in the app.
--
-- 1. Vehicle register: any signed-in account (sign-up is free) could read every VIN, make, model and import mileage,
--    including cars that were never listed and Saaz's own imports. Only admins read it now. Nothing in the app
--    reads it outside Admin; sellers and buyers get vehicle facts through listings and reports.
-- 2. Odometer history: anyone, signed in or not, could read every reading. Admins only now. The public report
--    still shows the odometer through review_document.
-- 3. Saves: a person could save a car that isn't public (a draft or one in inspection), which also showed up in
--    that car's figures. Only public cars can be saved now; un-saving always works.
-- 4. Listing figures (listing_stats): anyone could read views, saves and offers for a car that isn't public.
--    Now only for public cars, or for the seller and admins.
-- 5. Internal helpers: visitors and signed-in people could call functions meant only for other database
--    functions. opinions_of returned Saaz's comments, with reasons, on any report, including unpublished ones.
--    These are now callable only inside the database. tick (time-outs and expiry) stays open to signed-in
--    people because the app runs it on page load (there is no scheduler); visitors lose it, and two calls at
--    once no longer both run.
-- 6. Table write rights: visitors and signed-in people held insert, update, delete and truncate on every table.
--    Row security already refused every write (the app writes only through database functions), so this
--    removes a second line of defence that should never have been open, now and for future tables.
-- 7. Seven functions had no fixed search_path (Supabase advisor warning). Four are fixed. rpt_age_band, rpt_price_band and
--    rpt_status_group are left as they are on purpose: a fixed search_path stops Postgres inlining them into the report
--    queries, which made the reports 50% slower in testing (1.58 s to 2.38 s, over the 2 s limit). They use no tables or
--    functions, only built-in comparisons, and visitors and signed-in people can't create objects in public, so the
--    warning carries no real risk for them. Expect the advisor to keep listing these three.

-- 1, 2
drop policy if exists "signed-in read vehicles" on public.vehicles;
drop policy if exists "admins read vehicles" on public.vehicles;
create policy "admins read vehicles" on public.vehicles for select using (public.is_admin());
drop policy if exists "anyone reads odometer history" on public.odometer_readings;
drop policy if exists "admins read odometer history" on public.odometer_readings;
create policy "admins read odometer history" on public.odometer_readings for select using (public.is_admin());

-- 3
create or replace function public.toggle_save(p_listing uuid) returns boolean language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user();
begin
  if exists (select 1 from public.saves where listing_id = p_listing and user_id = u) then
    delete from public.saves where listing_id = p_listing and user_id = u; return false;
  end if;
  if not exists (select 1 from public.listings where id = p_listing and status in ('live','reserved','sold')) then
    raise exception 'This car is not on the marketplace.';
  end if;
  insert into public.saves (listing_id, user_id) values (p_listing, u); return true;
end $$;

-- 4: the same function, with the visibility check first
do $$
declare src text;
begin
  select pg_get_functiondef('public.listing_stats(uuid)'::regprocedure) into src;
  if position('-- part 21 visibility' in src) = 0 then
    src := replace(src, 'if l is null then return null; end if;',
      'if l is null then return null; end if; -- part 21 visibility
  if l.status not in (''live'',''reserved'',''sold'') and not (public.is_listing_seller(l) or public.is_admin()) then return null; end if;');
    execute src;
  end if;
end $$;

-- 5
do $$
declare f text;
begin
  foreach f in array array['opinions_of(uuid)', 'saaz_stance(uuid)', 'setting(text)', 'model_sales(text, text, text)', 'require_full_admin()',
                           'cancel_on_reject()', 'stamp_deal_event()'] loop
    if to_regprocedure('public.' || f) is not null then
      execute 'revoke execute on function public.' || f || ' from public, anon, authenticated';
    end if;
  end loop;
end $$;

create or replace function public.tick() returns void language plpgsql security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
declare c record;
begin
  if not pg_try_advisory_xact_lock(hashtext('saaz.tick')) then return; end if;   -- already running for someone else
  for c in select id from public.conversations where status = 'in_play' and garage_first_message_at is null and deadline < now() loop
    perform public.pass_on(c.id, 'timed_out');
  end loop;
  update public.listings l set status = 're_review_due', updated_at = now()
    from public.reviews r where r.id = l.current_review_id and l.status = 'live' and r.valid_until < current_date;
end $$;
revoke execute on function public.tick() from public, anon;
grant execute on function public.tick() to authenticated;

-- 6
revoke insert, update, delete, truncate, references, trigger on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke insert, update, delete, truncate, references, trigger on tables from anon, authenticated;
-- Supabase also grants on tables created by its own admin role; the line below covers those where this role may change them.
do $$ begin
  execute 'alter default privileges for role postgres in schema public revoke insert, update, delete, truncate, references, trigger on tables from anon, authenticated';
exception when others then null; end $$;

-- 7 (the three report bands are deliberately left out: see the note at the top)
do $$
declare f text;
begin
  foreach f in array array['public.report_glossary()', 'public.report_glossary_2()', 'build.append_only()', 'build.can_move(text, text, text)'] loop
    if to_regprocedure(f) is not null then execute 'alter function ' || f || ' set search_path = public, pg_temp'; end if;
  end loop;
end $$;

-- Check (run after): both should return no rows
-- select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and has_table_privilege('anon', c.oid, 'INSERT');
-- select proname from pg_proc where proname in ('opinions_of','saaz_stance','setting') and has_function_privilege('anon', oid, 'execute');

-- 8. Notification links: every notice links to a Saaz page (#/...). The database now refuses any other link, so a future
--    function can't store a javascript: or outside address that the inbox would turn into a link. (The inbox also checks.)
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'notifications_link_is_saaz_page') then
    alter table public.notifications add constraint notifications_link_is_saaz_page check (link is null or link ~ '^#/[^\s"''<>]*$') not valid;
    alter table public.notifications validate constraint notifications_link_is_saaz_page;
  end if;
end $$;
