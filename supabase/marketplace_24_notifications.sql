-- Part 24: Notifications: SMS through Africa's Talking, outbox, preferences, phone check, announcements (3 Nov 2026).
-- Run after part 23. Safe to run twice. NOT LIVE. Tested on the local copy only (tests/db_notify_test.py). Needs James's approval in a live chat.
--
-- How it works
--   Every notice the marketplace already writes (public.notifications, with its channels) now also goes to an outbox:
--   one row per SMS or email. The Edge Function send-outbox takes SMS rows from the outbox and sends them through
--   Africa's Talking. Its keys live in Supabase function secrets (AT_USERNAME, AT_API_KEY, AT_SENDER_ID), never here.
--   Until those secrets are set, rows wait in the outbox and every notice still lands in the in-app inbox, as today.
--   Email rows are held: no email sender is connected yet (project-docs/email-and-notifications.md).
--
-- Rules
--   - SMS alerts go only to a verified Ugandan mobile (setting sms_needs_verified, on), when the person allows SMS alerts,
--     and the number isn't on the opt-out list. Each skipped SMS is kept with the reason, so "why didn't I get it" has an answer.
--   - Admins can change which channels each kind of notice uses (notify_kinds) without a code change.
--   - Announcements (news to many people) go to the in-app inbox for everyone in the audience; by SMS only to people who opted in
--     (Account, or the marketing tick on a promotion they entered). SMS announcements wait for 08:00 to 20:00 East Africa Time.
--   - Phone check: a 6-digit code by SMS, valid 10 minutes, 5 tries, at most 5 codes a day. The code is stored only as a hash,
--     and its text is removed from the outbox once sent.
--   - The sender functions (claim, result) are callable only by the Edge Function (service role). Nobody else reads the outbox
--     except admins, through admin_outbox.

-- ---------- tables ----------
create table if not exists public.notify_prefs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  alerts_sms boolean not null default true,      -- service notices about your own cars, offers, jobs
  alerts_email boolean not null default true,
  news_sms boolean not null default false,       -- announcements and offers from Saaz: opt in only
  news_email boolean not null default false,
  updated_at timestamptz not null default now()
);
create table if not exists public.notify_kinds (
  kind text primary key check (kind ~ '^[a-z_]{3,40}$'),
  channels text[] not null check (channels <@ array['app','sms','email'] and 'app' = any(channels)),
  updated_by uuid references auth.users(id),
  updated_at timestamptz not null default now()
);
create table if not exists public.announcements (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor uuid references auth.users(id),
  audience text not null,
  promotion_id uuid references public.promotions(id),
  channels text[] not null,
  body text not null,
  link text,
  counts jsonb not null default '{}'::jsonb
);
create table if not exists public.outbox (
  id bigint generated always as identity primary key,
  notification_id uuid references public.notifications(id) on delete set null,
  announcement_id bigint references public.announcements(id),
  user_id uuid references auth.users(id) on delete set null,
  kind text not null,
  channel text not null check (channel in ('sms','email')),
  purpose text not null check (purpose in ('alert','news','code')),
  to_addr text,
  body text not null,
  status text not null default 'queued' check (status in ('queued','sending','sent','failed','held','skipped')),
  reason text,
  attempts int not null default 0,
  next_try_at timestamptz not null default now(),
  lease_until timestamptz,
  provider_id text,
  cost text,
  created_at timestamptz not null default now(),
  sent_at timestamptz
);
create index if not exists outbox_ready on public.outbox (status, next_try_at) where status in ('queued','sending');
create index if not exists outbox_user on public.outbox (user_id, created_at);
create table if not exists public.sms_optout (
  mobile text primary key check (mobile ~ '^\+2567[0-9]{8}$'),
  at timestamptz not null default now(),
  by uuid references auth.users(id),
  reason text not null
);
create table if not exists public.phone_codes (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  mobile text not null,
  code_hash text not null,
  expires_at timestamptz not null,
  tries int not null default 0,
  used_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists phone_codes_user on public.phone_codes (user_id, created_at);
create table if not exists public.outbox_runs (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  configured boolean not null,
  claimed int not null default 0,
  sent int not null default 0,
  failed int not null default 0,
  note text
);

do $$ declare t text; begin
  foreach t in array array['notify_prefs','notify_kinds','announcements','outbox','sms_optout','phone_codes','outbox_runs'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated', t);
  end loop;
end $$;

insert into public.settings (key, value, note) values
  ('sms_needs_verified', 'true'::jsonb, 'SMS alerts only to mobiles verified with a code'),
  ('sms_price_ugx', 'null'::jsonb, 'Placeholder: price of one SMS segment in UGX (from Africa''s Talking), for the announcement cost estimate'),
  ('sms_max_audience', '20000'::jsonb, 'Most people one announcement can reach')
on conflict (key) do nothing;

insert into public.request_limits (path, max_hits, per_seconds, note) values
  ('/rpc/phone_send_code', 5, 3600, 'Phone check codes sent'),
  ('/rpc/phone_check_code', 20, 3600, 'Phone check code tries'),
  ('/rpc/admin_announce', 10, 3600, 'Announcements sent')
on conflict (path) do nothing;

-- Channels per kind of notice. Seeded from what each notice already asks for (email-and-notifications.md), plus SMS for
-- the steps someone must act on that only had the app before (review date, assignments, counter-offers). Admins change these.
insert into public.notify_kinds (kind, channels) values
  ('review_date', '{app,sms}'), ('assigned', '{app,sms}'), ('inspection_assigned', '{app,sms}'), ('deal_counter', '{app,sms}'),
  ('deal_propose', '{app,sms}'), ('promotion_winner', '{app,sms,email}'), ('announcement', '{app}'), ('phone_code', '{app}')
on conflict (kind) do nothing;

-- ---------- helpers (no grants) ----------
create or replace function public.sms_text(p text) returns text language sql immutable set search_path = public as
$$ select left('Saaz: ' || replace(regexp_replace(coalesce(p, ''), '\s+', ' ', 'g'), '%', ' percent'), 459) $$;   -- 3 segments at most; % can make the gateway fail

create or replace function public.sms_segments(p text) returns int language sql immutable set search_path = public as
$$ select case when length(p) <= 160 then 1 else ceil(length(p) / 153.0)::int end $$;

-- Next time inside 08:00 to 20:00 East Africa Time (now, if it is inside)
create or replace function public.sms_send_window(p_at timestamptz) returns timestamptz language sql stable set search_path = public as $$
  select case when extract(hour from p_at at time zone 'Africa/Kampala') between 8 and 19 then p_at
              when extract(hour from p_at at time zone 'Africa/Kampala') >= 20
                then ((date_trunc('day', p_at at time zone 'Africa/Kampala') + interval '1 day 8 hours') at time zone 'Africa/Kampala')
              else ((date_trunc('day', p_at at time zone 'Africa/Kampala') + interval '8 hours') at time zone 'Africa/Kampala') end $$;

-- Who may get an SMS, and why not. Returns the number to use, or null with the reason.
create or replace function public.sms_target(p_user uuid, p_purpose text, out mobile text, out reason text) language plpgsql stable security definer set search_path = public as $$
declare pr public.profiles; pf public.notify_prefs;
begin
  select * into pr from public.profiles where id = p_user;
  select * into pf from public.notify_prefs where user_id = p_user;
  mobile := public.promo_mobile(pr.mobile);
  if pr.id is null then reason := 'No profile'; mobile := null; return; end if;
  if mobile is null then reason := 'No Ugandan mobile number on the account'; return; end if;
  if exists (select 1 from public.sms_optout o where o.mobile = sms_target.mobile) then reason := 'Number is on the opt-out list'; mobile := null; return; end if;
  if p_purpose = 'alert' and coalesce(pf.alerts_sms, true) = false then reason := 'Turned off SMS alerts'; mobile := null; return; end if;
  if p_purpose = 'news' and coalesce(pf.news_sms, false) = false then reason := 'Not opted in to SMS news'; mobile := null; return; end if;
  -- 'broadcast' (announcements): consent is decided by the caller (news setting or a promotion's marketing tick)
  if p_purpose in ('alert','news','broadcast') and coalesce((public.setting('sms_needs_verified'))::text::boolean, true) and not pr.phone_verified then
    reason := 'Mobile not verified yet'; mobile := null; return; end if;
end $$;

-- Before a notice is stored: an admin override for its kind decides the channels
create or replace function public.notify_channels_trg() returns trigger language plpgsql security definer set search_path = public as $$
declare k text[];
begin
  select channels into k from public.notify_kinds where kind = new.kind;
  if k is not null then new.channels := k; end if;
  return new;
end $$;
-- After: one outbox row per SMS and email
create or replace function public.notify_fanout_trg() returns trigger language plpgsql security definer set search_path = public as $$
declare t record; v_email text; pf public.notify_prefs;
begin
  if new.kind in ('announcement', 'phone_code') then return null; end if;   -- handled by their own functions
  if 'sms' = any(new.channels) then
    select * into t from public.sms_target(new.user_id, 'alert');
    insert into public.outbox (notification_id, user_id, kind, channel, purpose, to_addr, body, status, reason)
      values (new.id, new.user_id, new.kind, 'sms', 'alert', t.mobile, public.sms_text(new.body),
              case when t.mobile is null then 'skipped' else 'queued' end, t.reason);
  end if;
  if 'email' = any(new.channels) then
    select email into v_email from public.profiles where id = new.user_id;
    select * into pf from public.notify_prefs where user_id = new.user_id;
    insert into public.outbox (notification_id, user_id, kind, channel, purpose, to_addr, body, status, reason)
      values (new.id, new.user_id, new.kind, 'email', 'alert', v_email, new.body,
              case when coalesce(pf.alerts_email, true) then 'held' else 'skipped' end,
              case when coalesce(pf.alerts_email, true) then 'No email sender connected yet' else 'Turned off email alerts' end);
  end if;
  return null;
end $$;
drop trigger if exists notify_channels on public.notifications;
create trigger notify_channels before insert on public.notifications for each row execute function public.notify_channels_trg();
drop trigger if exists notify_fanout on public.notifications;
create trigger notify_fanout after insert on public.notifications for each row execute function public.notify_fanout_trg();

do $$ declare f text; begin
  foreach f in array array['public.sms_text(text)','public.sms_segments(text)','public.sms_send_window(timestamptz)','public.sms_target(uuid,text)',
                           'public.notify_channels_trg()','public.notify_fanout_trg()'] loop
    execute 'revoke execute on function ' || f || ' from public, anon, authenticated';
  end loop;
end $$;

-- ---------- the sender (Edge Function send-outbox, service role only) ----------
-- Takes up to p_limit SMS rows that are due: codes first, then alerts, then news. Each is leased for 5 minutes.
create or replace function public.outbox_claim(p_limit int) returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare r jsonb;
begin
  with due as (
    select id from public.outbox
    where channel = 'sms' and next_try_at <= now() and (status = 'queued' or (status = 'sending' and lease_until < now()))
    order by case purpose when 'code' then 0 when 'alert' then 1 else 2 end, next_try_at, id
    limit least(greatest(coalesce(p_limit, 50), 1), 200) for update skip locked),
  upd as (
    update public.outbox o set status = 'sending', attempts = o.attempts + 1, lease_until = now() + interval '5 minutes'
    from due where o.id = due.id returning o.id, o.to_addr, o.body, o.attempts, o.purpose)
  select coalesce(jsonb_agg(jsonb_build_object('id', id, 'to', to_addr, 'body', body, 'attempts', attempts)
           order by case purpose when 'code' then 0 when 'alert' then 1 else 2 end, id), '[]') into r from upd;
  return r;
end $$;

-- p_permanent: the number or account can't receive (InvalidPhoneNumber, UserInBlacklist...). Otherwise up to 3 tries: 1, 5, then 30 minutes apart.
create or replace function public.outbox_result(p_id bigint, p_ok boolean, p_provider_id text, p_cost text, p_error text, p_permanent boolean)
returns text language plpgsql security definer set search_path = public as $$
declare o public.outbox; v text;
begin
  select * into o from public.outbox where id = p_id for update;
  if o.id is null or o.status <> 'sending' then return 'ignored'; end if;
  if p_ok then
    update public.outbox set status = 'sent', sent_at = now(), lease_until = null, provider_id = left(p_provider_id, 100), cost = left(p_cost, 40), reason = null,
      body = case when purpose = 'code' then '(code removed after sending)' else body end where id = p_id;
    return 'sent';
  end if;
  v := case when coalesce(p_permanent, false) or o.attempts >= 3 then 'failed' else 'queued' end;
  update public.outbox set status = v, lease_until = null, reason = left(coalesce(p_error, 'Unknown error'), 300),
    next_try_at = now() + case o.attempts when 1 then interval '1 minute' when 2 then interval '5 minutes' else interval '30 minutes' end,
    body = case when v = 'failed' and purpose = 'code' then '(code removed)' else body end where id = p_id;
  return v;
end $$;

-- Puts leased rows back untouched (the account can't send right now): the try doesn't count
create or replace function public.outbox_release(p_ids bigint[]) returns int language plpgsql security definer set search_path = public as $$
declare n int;
begin
  update public.outbox set status = 'queued', attempts = greatest(attempts - 1, 0), lease_until = null, next_try_at = now() + interval '1 minute'
  where id = any(p_ids) and status = 'sending';
  get diagnostics n = row_count; return n;
end $$;

-- One row per run that did something; idle runs with the same result only move the last row's time (no flood of rows)
create or replace function public.outbox_run(p_configured boolean, p_claimed int, p_sent int, p_failed int, p_note text) returns void
language plpgsql security definer set search_path = public as $$
declare l public.outbox_runs;
begin
  select * into l from public.outbox_runs order by id desc limit 1;
  if coalesce(p_claimed, 0) = 0 and l.id is not null and l.claimed = 0 and l.configured = p_configured and l.note is not distinct from left(p_note, 300) then
    update public.outbox_runs set at = now() where id = l.id; return;
  end if;
  insert into public.outbox_runs (configured, claimed, sent, failed, note) values (p_configured, coalesce(p_claimed,0), coalesce(p_sent,0), coalesce(p_failed,0), left(p_note, 300));
end $$;

do $$ declare f text; begin
  foreach f in array array['public.outbox_claim(int)','public.outbox_result(bigint,boolean,text,text,text,boolean)','public.outbox_run(boolean,int,int,int,text)','public.outbox_release(bigint[])'] loop
    execute 'revoke execute on function ' || f || ' from public, anon, authenticated';
    execute 'grant execute on function ' || f || ' to service_role';
  end loop;
end $$;

-- ---------- signed in: preferences and phone check ----------
create or replace function public.my_notify_prefs() returns jsonb language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_user(); pf public.notify_prefs; pr public.profiles;
begin
  select * into pf from public.notify_prefs where user_id = u;
  select * into pr from public.profiles where id = u;
  return jsonb_build_object('alerts_sms', coalesce(pf.alerts_sms, true), 'alerts_email', coalesce(pf.alerts_email, true),
    'news_sms', coalesce(pf.news_sms, false), 'news_email', coalesce(pf.news_email, false),
    'mobile', pr.mobile, 'mobile_ok', public.promo_mobile(pr.mobile) is not null, 'phone_verified', pr.phone_verified,
    'needs_verified', coalesce((public.setting('sms_needs_verified'))::text::boolean, true));
end $$;

create or replace function public.set_notify_prefs(p jsonb) returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); o public.notify_prefs;
begin
  select * into o from public.notify_prefs where user_id = u;
  insert into public.notify_prefs (user_id, alerts_sms, alerts_email, news_sms, news_email, updated_at)
    values (u, coalesce((p->>'alerts_sms')::boolean, true), coalesce((p->>'alerts_email')::boolean, true),
            coalesce((p->>'news_sms')::boolean, false), coalesce((p->>'news_email')::boolean, false), now())
    on conflict (user_id) do update set alerts_sms = excluded.alerts_sms, alerts_email = excluded.alerts_email,
      news_sms = excluded.news_sms, news_email = excluded.news_email, updated_at = now();
  perform public.audit('account', 'account', u::text, 'message settings changed',
    jsonb_build_object('before', case when o.user_id is null then null else jsonb_build_object('alerts_sms', o.alerts_sms, 'alerts_email', o.alerts_email, 'news_sms', o.news_sms, 'news_email', o.news_email) end,
                       'after', p));
  return public.my_notify_prefs();
end $$;

create or replace function public.phone_send_code() returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare u uuid := public.require_user(); pr public.profiles; m text; c text; last timestamptz;
begin
  select * into pr from public.profiles where id = u;
  m := public.promo_mobile(pr.mobile);
  if m is null then raise exception 'Save a Ugandan mobile number first, for example 0772 123456.'; end if;
  if pr.phone_verified then raise exception 'Your mobile number is already verified.'; end if;
  if exists (select 1 from public.sms_optout o where o.mobile = m) then raise exception 'This number asked Saaz not to send SMS. Contact Saaz to undo that.'; end if;
  select max(created_at) into last from public.phone_codes where user_id = u;
  if last > now() - interval '60 seconds' then raise exception 'Wait a minute before asking for another code.'; end if;
  if (select count(*) from public.phone_codes where user_id = u and created_at > now() - interval '1 day') >= 5 then
    raise exception 'Too many codes today. Try again tomorrow.'; end if;
  c := lpad((floor(random() * 1000000))::int::text, 6, '0');
  update public.phone_codes set used_at = now() where user_id = u and used_at is null;   -- only the newest code works
  insert into public.phone_codes (user_id, mobile, code_hash, expires_at)
    values (u, m, encode(sha256(convert_to(u::text || ':' || c, 'UTF8')), 'hex'), now() + interval '10 minutes');
  insert into public.outbox (user_id, kind, channel, purpose, to_addr, body)
    values (u, 'phone_code', 'sms', 'code', m, 'Saaz: your code is ' || c || '. It works for 10 minutes. Saaz never asks for this code.');
  perform public.audit('account', 'account', u::text, 'phone code sent', jsonb_build_object('to', left(m, 7) || '***' || right(m, 2)));
  return jsonb_build_object('sent_to', left(m, 7) || '***' || right(m, 2), 'expires_in_minutes', 10);
end $$;

create or replace function public.phone_check_code(p_code text) returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare u uuid := public.require_user(); pc public.phone_codes; pr public.profiles;
begin
  select * into pr from public.profiles where id = u;
  select * into pc from public.phone_codes where user_id = u and used_at is null order by id desc limit 1 for update;
  if pc.id is null or pc.expires_at < now() then raise exception 'That code has expired. Ask for a new one.'; end if;
  if pc.mobile is distinct from public.promo_mobile(pr.mobile) then raise exception 'Your number changed after the code was sent. Ask for a new one.'; end if;
  if pc.tries >= 5 then raise exception 'Too many wrong tries. Ask for a new code.'; end if;
  if encode(sha256(convert_to(u::text || ':' || btrim(coalesce(p_code, '')), 'UTF8')), 'hex') <> pc.code_hash then
    update public.phone_codes set tries = tries + 1 where id = pc.id;
    return jsonb_build_object('ok', false, 'tries_left', 4 - pc.tries);
  end if;
  update public.phone_codes set used_at = now() where id = pc.id;
  update public.profiles set phone_verified = true, mobile = pc.mobile where id = u;
  perform public.audit('account', 'account', u::text, 'phone verified', '{}'::jsonb);
  return jsonb_build_object('ok', true);
end $$;

do $$ declare f text; begin
  foreach f in array array['public.my_notify_prefs()','public.set_notify_prefs(jsonb)','public.phone_send_code()','public.phone_check_code(text)'] loop
    execute 'revoke execute on function ' || f || ' from public, anon';
    execute 'grant execute on function ' || f || ' to authenticated';
  end loop;
end $$;

-- ---------- admin ----------
-- The audience of an announcement: user ids, and whether each has opted in to SMS news for it
create or replace function public.announce_audience(p_audience text, p_promotion uuid) returns table (user_id uuid, news_ok boolean)
language sql stable security definer set search_path = public as $$
  select x.id, coalesce(pf.news_sms, false) or coalesce(x.promo_ok, false)
  from (
    select p.id, null::boolean promo_ok from public.profiles p where p_audience = 'all' and not p.suspended
    union select distinct l.seller_id, null::boolean from public.listings l join public.profiles p on p.id = l.seller_id where p_audience = 'sellers' and not p.suspended
    union select distinct d.buyer_id, null::boolean from public.deals d join public.profiles p on p.id = d.buyer_id where p_audience = 'buyers' and not p.suspended
    union select distinct s.user_id, null::boolean from public.saves s join public.profiles p on p.id = s.user_id where p_audience = 'buyers' and not p.suspended
    union select distinct m.user_id, null::boolean from public.garage_members m join public.garages g on g.id = m.garage_id
          where p_audience = 'garages' and m.status = 'active' and g.status = 'certified'
    union select e.user_id, e.marketing_ok from public.promo_entries e where p_audience = 'promotion' and e.promotion_id = p_promotion and e.status <> 'invalid' and not e.purged
  ) x left join public.notify_prefs pf on pf.user_id = x.id
  where x.id is not null
$$;
revoke execute on function public.announce_audience(text, uuid) from public, anon, authenticated;

create or replace function public.admin_announce_preview(p_audience text, p_promotion uuid, p_channels text[], p_body text) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); n int; n_sms int; reasons jsonb; seg int := public.sms_segments(public.sms_text(coalesce(p_body, '') || ' Stop these in your Saaz account.'));
        price numeric := nullif(public.setting('sms_price_ugx')#>>'{}', '')::numeric; want boolean := 'sms' = any(coalesce(p_channels, '{}'));
begin
  if p_audience not in ('all','sellers','buyers','garages','promotion') then raise exception 'Choose an audience.'; end if;
  if p_audience = 'promotion' and not exists (select 1 from public.promotions where id = p_promotion) then raise exception 'Choose the promotion.'; end if;
  with aud as (select user_id, bool_or(news_ok) ok from public.announce_audience(p_audience, p_promotion) group by 1),
  t as (select case when s.mobile is null then s.reason when not aud.ok then 'Not opted in to SMS news' end reason
        from aud cross join lateral public.sms_target(aud.user_id, 'broadcast') s)
  select count(*), count(*) filter (where reason is null),
         coalesce((select jsonb_object_agg(r, c) from (select reason r, count(*) c from t where reason is not null group by 1) z), '{}')
    into n, n_sms, reasons from t;
  return jsonb_build_object('people', n, 'sms', case when want then n_sms else 0 end, 'sms_not_sent', case when want then reasons else '{}'::jsonb end,
    'segments', seg, 'price_ugx', price, 'cost_ugx', case when want and price is not null then price * seg * n_sms end,
    'sms_from', public.sms_send_window(now()));
end $$;

-- Sends one announcement. App inbox for everyone in the audience; SMS for those who opted in, inside 08:00 to 20:00 EAT.
create or replace function public.admin_announce(p_audience text, p_promotion uuid, p_channels text[], p_body text, p_link text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); a_id bigint; n_app int := 0; n_sms int := 0; n_skip int := 0; b text := btrim(coalesce(p_body, ''));
        maxn int := coalesce((public.setting('sms_max_audience'))::text::int, 20000); total int; at_ timestamptz := public.sms_send_window(now());
begin
  if length(b) < 10 or length(b) > 450 then raise exception 'Write the message (10 to 450 characters).'; end if;
  if p_channels is null or not (p_channels <@ array['app','sms']) or not ('app' = any(p_channels)) then raise exception 'Channels: the app inbox, and SMS if wanted.'; end if;
  if p_link is not null and p_link !~ '^#/[^\s"''<>]*$' then raise exception 'The link must be a Saaz page (starting #/).'; end if;
  if p_audience not in ('all','sellers','buyers','garages','promotion') then raise exception 'Choose an audience.'; end if;
  if p_audience = 'promotion' and not exists (select 1 from public.promotions where id = p_promotion) then raise exception 'Choose the promotion.'; end if;
  select count(distinct user_id) into total from public.announce_audience(p_audience, p_promotion);
  if total = 0 then raise exception 'Nobody is in that audience.'; end if;
  if total > maxn then raise exception 'That audience is % people, more than the limit of %.', total, maxn; end if;
  insert into public.announcements (actor, audience, promotion_id, channels, body, link) values (u, p_audience, p_promotion, p_channels, b, p_link) returning id into a_id;
  insert into public.notifications (user_id, kind, body, link, channels)
    select distinct user_id, 'announcement', b, p_link, '{app}'::text[] from public.announce_audience(p_audience, p_promotion);
  get diagnostics n_app = row_count;
  if 'sms' = any(p_channels) then
    with aud as (select user_id, bool_or(news_ok) news_ok from public.announce_audience(p_audience, p_promotion) group by 1),
    t as (select aud.user_id, aud.news_ok, s.mobile, s.reason from aud cross join lateral public.sms_target(aud.user_id, 'broadcast') s),
    ins as (
      insert into public.outbox (announcement_id, user_id, kind, channel, purpose, to_addr, body, status, reason, next_try_at)
      select a_id, t.user_id, 'announcement', 'sms', 'news', t.mobile, public.sms_text(b || ' Stop these in your Saaz account.'),
             case when t.mobile is not null and t.news_ok then 'queued' else 'skipped' end,
             case when t.mobile is null then t.reason when not t.news_ok then 'Not opted in to SMS news' end, at_
      from t returning status)
    select count(*) filter (where status = 'queued'), count(*) filter (where status = 'skipped') into n_sms, n_skip from ins;
  end if;
  update public.announcements set counts = jsonb_build_object('app', n_app, 'sms', n_sms, 'sms_skipped', n_skip, 'sms_from', at_) where id = a_id;
  perform public.audit('admin', 'setting', 'announcement', 'announcement sent', jsonb_build_object('id', a_id, 'audience', p_audience, 'app', n_app, 'sms', n_sms, 'skipped', n_skip));
  return jsonb_build_object('id', a_id, 'app', n_app, 'sms', n_sms, 'sms_skipped', n_skip, 'sms_from', at_);
end $$;

-- Outbox for admins: rows, counts, the sender's last run. Codes never show.
create or replace function public.admin_outbox(p_status text default null, p_channel text default null, p_page int default 1) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_admin(); lim int := 50; off int := (greatest(coalesce(p_page, 1), 1) - 1) * 50;
begin
  return jsonb_build_object(
    'counts', (select coalesce(jsonb_object_agg(channel || ':' || status, n), '{}') from (select channel, status, count(*) n from public.outbox group by 1, 2) s),
    'total', (select count(*) from public.outbox where (p_status is null or status = p_status) and (p_channel is null or channel = p_channel)),
    'last_run', (select jsonb_build_object('at', at, 'configured', configured, 'claimed', claimed, 'sent', sent, 'failed', failed, 'note', note) from public.outbox_runs order by id desc limit 1),
    'rows', (select coalesce(jsonb_agg(x order by (x->>'id')::bigint desc), '[]') from (
      select jsonb_build_object('id', o.id, 'at', o.created_at, 'kind', o.kind, 'channel', o.channel, 'purpose', o.purpose, 'status', o.status, 'reason', o.reason,
        'attempts', o.attempts, 'sent_at', o.sent_at, 'next_try_at', o.next_try_at, 'cost', o.cost,
        'to', o.to_addr, 'name', (select coalesce(nullif(name, ''), email) from public.profiles where id = o.user_id), 'user_id', o.user_id,
        'body', case when o.purpose = 'code' then '(phone check code, hidden)' else o.body end) x
      from public.outbox o where (p_status is null or o.status = p_status) and (p_channel is null or o.channel = p_channel)
      order by o.id desc limit lim offset off) s),
    'page', greatest(coalesce(p_page, 1), 1), 'size', lim);
end $$;

create or replace function public.admin_outbox_retry(p_id bigint) returns text language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_admin(); o public.outbox;
begin
  select * into o from public.outbox where id = p_id for update;
  if o.id is null then raise exception 'Not found.'; end if;
  if o.status <> 'failed' or o.channel <> 'sms' or o.purpose = 'code' then raise exception 'Only a failed SMS (not a code) can be sent again.'; end if;
  update public.outbox set status = 'queued', attempts = 0, next_try_at = case when purpose = 'news' then public.sms_send_window(now()) else now() end, reason = null where id = p_id;
  perform public.audit('admin', 'setting', 'outbox', 'SMS sent again', jsonb_build_object('outbox', p_id, 'kind', o.kind));
  return 'queued';
end $$;

-- Channels per kind: every kind seen so far, with any override
create or replace function public.admin_notify_kinds() returns jsonb language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_admin();
begin
  return (select coalesce(jsonb_agg(jsonb_build_object('kind', k, 'override', o.channels, 'by_admin', o.updated_by is not null, 'seen', s.ch, 'count', s.n) order by k), '[]') from (
      select kind k from public.notifications union select kind from public.notify_kinds) kk
    left join public.notify_kinds o on o.kind = kk.k
    left join lateral (select array_agg(distinct c) ch, count(*) n from public.notifications n cross join unnest(n.channels) c where n.kind = kk.k) s on true);
end $$;

create or replace function public.admin_notify_kind(p_kind text, p_channels text[]) returns void language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); o text[];
begin
  if p_kind in ('announcement', 'phone_code') then raise exception 'This kind is sent by its own page.'; end if;
  select channels into o from public.notify_kinds where kind = p_kind;
  if p_channels is null then
    delete from public.notify_kinds where kind = p_kind;   -- cleared: the notice uses the channels its code asks for
  else
    insert into public.notify_kinds (kind, channels, updated_by) values (p_kind, p_channels, u)
      on conflict (kind) do update set channels = excluded.channels, updated_by = u, updated_at = now();
  end if;
  perform public.audit('admin', 'setting', 'notify_kinds', 'notice channels changed', jsonb_build_object('kind', p_kind, 'before', o, 'after', p_channels));
end $$;

create or replace function public.admin_sms_optout(p_mobile text, p_reason text, p_add boolean) returns text language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); m text := public.promo_mobile(p_mobile);
begin
  if m is null then raise exception 'Write a Ugandan mobile number.'; end if;
  if p_add then
    if length(btrim(coalesce(p_reason, ''))) < 10 then raise exception 'Write how they asked (10 characters or more).'; end if;
    insert into public.sms_optout (mobile, by, reason) values (m, u, btrim(p_reason)) on conflict (mobile) do nothing;
    update public.outbox set status = 'skipped', reason = 'Number is on the opt-out list' where to_addr = m and status = 'queued' and purpose <> 'code';
  else
    delete from public.sms_optout where mobile = m;
  end if;
  perform public.audit('admin', 'setting', 'sms_optout', case when p_add then 'number opted out of SMS' else 'number removed from opt-out list' end, jsonb_build_object('to', left(m, 7) || '***' || right(m, 2)));
  return m;
end $$;

create or replace function public.admin_announcements() returns jsonb language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_full_admin();
begin
  return jsonb_build_object(
    'list', (select coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'at', a.at, 'audience', a.audience, 'promotion', (select title from public.promotions where id = a.promotion_id),
        'channels', a.channels, 'body', a.body, 'counts', a.counts, 'by', (select coalesce(nullif(name, ''), email) from public.profiles where id = a.actor)) order by a.id desc), '[]')
      from (select * from public.announcements order by id desc limit 100) a),
    'promotions', (select coalesce(jsonb_agg(jsonb_build_object('id', id, 'title', title) order by created_at desc), '[]') from public.promotions where status <> 'draft'),
    'optouts', (select coalesce(jsonb_agg(jsonb_build_object('mobile', mobile, 'at', at, 'reason', reason) order by at desc), '[]') from public.sms_optout),
    'price_ugx', nullif(public.setting('sms_price_ugx')#>>'{}', ''));
end $$;

do $$ declare f text; begin
  foreach f in array array['public.admin_announce_preview(text,uuid,text[],text)','public.admin_announce(text,uuid,text[],text,text)',
      'public.admin_outbox(text,text,int)','public.admin_outbox_retry(bigint)','public.admin_notify_kinds()','public.admin_notify_kind(text,text[])',
      'public.admin_sms_optout(text,text,boolean)','public.admin_announcements()'] loop
    execute 'revoke execute on function ' || f || ' from public, anon';
    execute 'grant execute on function ' || f || ' to authenticated';
  end loop;
end $$;

-- The sender (service role) goes through the same API request check as everyone (part 22). Supabase already grants this;
-- said here so it holds on any copy.
grant execute on function public.check_request() to service_role;
