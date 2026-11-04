-- Part 23: Promotions, first type: prize draw (3 Nov 2026). Run after part 22. Safe to run twice.
-- Asked for in "IT Integration Proposal" (giveaway draw). Built as one branch so later promotions reuse it.
-- Live since 4 Nov 2026: James approved in a live chat and ran it in the SQL Editor. Checked after (read-only): 8 tables locked, visitors can call only promotion_public, helpers not callable, switch off.
--
-- What it adds
--   1. A master switch for every promotion (starts OFF; full admins only; a reason to switch off; history kept).
--   2. Promotions: one row each (title, prize, dates, T&C, permit number, winners and reserves). Status:
--      draft -> open -> closed -> drawn, or cancelled. A promotion can't open without a permit number and T&C text.
--   3. Entries: signed-in account, one per account per promotion, Saaz team excluded. Name, mobile, current car,
--      dream car, T&C version accepted, marketing and WhatsApp consent (separate ticks), source link, promo code.
--      NIN and TIN are NOT collected (waiting on Allan). Entries lock on submit; only an admin changes their status, with a reason.
--   4. Fraud flags: many entries from one network address in a promotion are flagged and kept out of the draw until an admin clears them.
--      The address is stored only as a salted hash.
--   5. The draw: random, recorded, and checkable. The seed is saved; the order is md5(seed || entry id), so anyone with the
--      entry list and the seed gets the same winners. Reserves step up when a winner declines, doesn't reply or isn't eligible.
--   6. Tracked links per channel, promo codes (with use limits), a report, CSV export (logged), personal data cleared after the retention period.
-- Nothing in the marketplace tables changes. Winner notices use the existing in-app inbox (notify).

-- ---------- tables (read and written only through the functions below) ----------
create table if not exists public.promo_toggles (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor uuid references auth.users(id),
  enabled boolean not null,
  reason text
);
create table if not exists public.promotions (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{2,39}$'),
  kind text not null default 'draw' check (kind in ('draw')),          -- later: offer, referral, competition
  title text not null check (length(title) between 3 and 80),
  prize text not null default '' check (length(prize) <= 200),
  summary text not null default '' check (length(summary) <= 600),
  opens_at timestamptz,
  closes_at timestamptz,
  status text not null default 'draft' check (status in ('draft','open','closed','drawn','cancelled')),
  winners int not null default 1 check (winners between 1 and 100),
  reserves int not null default 2 check (reserves between 0 and 20),
  needs_code boolean not null default false,                           -- true: only people with a promo code can enter
  permit_no text not null default '' check (length(permit_no) <= 60),  -- LGRB permit (placeholder until issued)
  terms_version text not null default '' check (length(terms_version) <= 20),
  terms text not null default '' check (length(terms) <= 20000),
  retention_days int not null default 180 check (retention_days between 30 and 1095),
  purged_at timestamptz,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (opens_at is null or closes_at is null or opens_at < closes_at)
);
create table if not exists public.promo_links (
  id uuid primary key default gen_random_uuid(),
  promotion_id uuid not null references public.promotions(id),
  channel text not null check (channel ~ '^[a-z0-9][a-z0-9-]{1,29}$'),
  label text not null default '' check (length(label) <= 80),
  created_at timestamptz not null default now(),
  unique (promotion_id, channel)
);
create table if not exists public.promo_codes (
  id uuid primary key default gen_random_uuid(),
  promotion_id uuid not null references public.promotions(id),
  code text not null check (code ~ '^[A-Z0-9]{4,16}$'),
  label text not null default '' check (length(label) <= 80),          -- for example the garage that hands it out
  max_uses int check (max_uses is null or max_uses > 0),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (promotion_id, code)
);
create table if not exists public.promo_entries (
  id uuid primary key default gen_random_uuid(),
  promotion_id uuid not null references public.promotions(id),
  user_id uuid not null references auth.users(id),
  name text not null,
  mobile text,
  email text,
  current_car text not null default '',
  dream_car text not null default '',
  source text not null default 'direct',
  code_id uuid references public.promo_codes(id),
  terms_version text not null,
  marketing_ok boolean not null default false,
  whatsapp_ok boolean not null default false,
  ip_hash text,
  status text not null default 'valid' check (status in ('valid','flagged','invalid')),
  status_reason text,
  status_by uuid references auth.users(id),
  purged boolean not null default false,
  created_at timestamptz not null default now(),
  unique (promotion_id, user_id)
);
create index if not exists promo_entries_promo_ip on public.promo_entries (promotion_id, ip_hash);
create index if not exists promo_entries_promo_at on public.promo_entries (promotion_id, created_at);
create table if not exists public.promo_draws (
  id bigint generated always as identity primary key,
  promotion_id uuid not null unique references public.promotions(id),
  at timestamptz not null default now(),
  actor uuid references auth.users(id),
  seed text not null,
  entries_in_draw int not null,
  witness text not null
);
create table if not exists public.promo_results (
  id uuid primary key default gen_random_uuid(),
  promotion_id uuid not null references public.promotions(id),
  entry_id uuid not null references public.promo_entries(id),
  rank int not null,
  role text not null check (role in ('winner','reserve','stepped_down')),
  state text not null default 'pending' check (state in ('pending','contacted','confirmed','declined','no_reply','ineligible','handed_over')),
  note text,
  updated_at timestamptz not null default now(),
  unique (promotion_id, rank)
);
create table if not exists public.promo_secret (one boolean primary key default true check (one), salt text not null);
insert into public.promo_secret (salt) values (md5(gen_random_uuid()::text || clock_timestamp()::text) || md5(gen_random_uuid()::text)) on conflict do nothing;

do $$ declare t text; begin
  foreach t in array array['promo_toggles','promotions','promo_links','promo_codes','promo_entries','promo_draws','promo_results','promo_secret'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated', t);
  end loop;
end $$;

-- History can't be rewritten: switch history and draws accept new rows only
create or replace function public.promo_append_only() returns trigger language plpgsql set search_path = public as
$$ begin raise exception 'This history can''t be changed.'; end $$;
revoke execute on function public.promo_append_only() from public, anon, authenticated;
drop trigger if exists promo_toggles_append_only on public.promo_toggles;
create trigger promo_toggles_append_only before update or delete on public.promo_toggles for each row execute function public.promo_append_only();
drop trigger if exists promo_draws_append_only on public.promo_draws;
create trigger promo_draws_append_only before update or delete on public.promo_draws for each row execute function public.promo_append_only();

insert into public.settings (key, value, note) values
  ('promo_flag_same_address', '3'::jsonb, 'Promotions: entries from one network address before new ones are flagged (assumption)'),
  ('promo_contact_phone', '""'::jsonb, 'Promotions: the one number Saaz calls winners from, shown on every promotion page (placeholder until set)')
on conflict (key) do nothing;

insert into public.request_limits (path, max_hits, per_seconds, note) values
  ('/rpc/promotion_enter', 10, 3600, 'Promotion entries')
on conflict (path) do nothing;

-- ---------- helpers (no grants: only the functions below use them) ----------
create or replace function public.promo_on() returns boolean language sql stable security definer set search_path = public as
$$ select coalesce((select enabled from public.promo_toggles order by id desc limit 1), false) $$;

create or replace function public.promo_is_open(p public.promotions) returns boolean language sql stable security definer set search_path = public as
$$ select public.promo_on() and p.status = 'open' and p.opens_at <= now() and now() < p.closes_at $$;

create or replace function public.promo_mobile(p text) returns text language sql immutable set search_path = public as $$
  select case when x ~ '^\+2567[0-9]{8}$' then x when x ~ '^07[0-9]{8}$' then '+256' || substr(x, 2)
              when x ~ '^2567[0-9]{8}$' then '+' || x when x ~ '^7[0-9]{8}$' then '+256' || x end
  from (select regexp_replace(coalesce(p, ''), '[\s()-]', '', 'g') x) s $$;

create or replace function public.promo_ip_hash(p_promo uuid) returns text language sql stable security definer set search_path = public as $$
  select md5((select salt from public.promo_secret) || p_promo::text ||
    coalesce(nullif(h->>'cf-connecting-ip', ''), nullif(trim(split_part(h->>'x-forwarded-for', ',', 1)), ''), nullif(h->>'x-real-ip', ''), 'unknown'))
  from (select coalesce(nullif(current_setting('request.headers', true), ''), '{}')::json h) s $$;

-- Clears personal details once a promotion is past its retention period (runs when an admin opens Promotions)
create or replace function public.promo_purge() returns int language plpgsql security definer set search_path = public as $$
declare n int := 0; p record;
begin
  for p in select id from public.promotions where purged_at is null and status in ('drawn','closed','cancelled')
             and coalesce(closes_at, updated_at) < now() - make_interval(days => retention_days) loop
    update public.promo_entries set name = '', mobile = null, email = null, ip_hash = null, purged = true where promotion_id = p.id and not purged;
    get diagnostics n = row_count;
    update public.promotions set purged_at = now() where id = p.id;
    perform public.audit('system', 'promotion', p.id::text, 'personal details cleared after retention period', jsonb_build_object('entries', n));
  end loop;
  return n;
end $$;

-- What visitors may see of a promotion
create or replace function public.promo_public_row(p public.promotions) returns jsonb language sql stable security definer set search_path = public as $$
  select jsonb_build_object('slug', p.slug, 'kind', p.kind, 'title', p.title, 'prize', p.prize, 'summary', p.summary,
    'opens_at', p.opens_at, 'closes_at', p.closes_at, 'status', p.status, 'winners', p.winners, 'needs_code', p.needs_code,
    'permit_no', p.permit_no, 'terms_version', p.terms_version, 'terms', p.terms, 'open', public.promo_is_open(p),
    'contact_phone', coalesce(public.setting('promo_contact_phone')#>>'{}', '')) $$;

do $$ declare f text; begin
  foreach f in array array['public.promo_on()','public.promo_is_open(public.promotions)','public.promo_mobile(text)','public.promo_ip_hash(uuid)',
                           'public.promo_purge()','public.promo_public_row(public.promotions)'] loop
    execute 'revoke execute on function ' || f || ' from public, anon, authenticated';
  end loop;
end $$;

-- ---------- public: the promotion page ----------
-- p_slug 'current' means the promotion that is open now (the newest if several). Returns {running:false} when the switch is off
-- or nothing public matches. Drafts are never shown here. Signed-in callers also get their own entry and their profile details.
create or replace function public.promotion_public(p_slug text) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare p public.promotions; e public.promo_entries; me public.profiles;
begin
  if not public.promo_on() then return jsonb_build_object('running', false); end if;
  if p_slug = 'current' then
    select * into p from public.promotions x where public.promo_is_open(x) order by x.opens_at desc limit 1;
  else
    select * into p from public.promotions x where x.slug = lower(p_slug) and x.status in ('open','closed','drawn');
  end if;
  if p.id is null then return jsonb_build_object('running', false); end if;
  if auth.uid() is not null then
    select * into e from public.promo_entries where promotion_id = p.id and user_id = auth.uid();
    select * into me from public.profiles where id = auth.uid();
  end if;
  return jsonb_build_object('running', true, 'promotion', public.promo_public_row(p),
    'my_entry', case when e.id is null then null else jsonb_build_object('at', e.created_at, 'status', case when e.status = 'invalid' then 'invalid' else 'entered' end) end,
    'me', case when me.id is null then null else jsonb_build_object('name', me.name, 'mobile', me.mobile,
      'saaz_team', exists (select 1 from public.admins where user_id = auth.uid())) end);
end $$;
revoke execute on function public.promotion_public(text) from public;
grant execute on function public.promotion_public(text) to anon, authenticated;

-- ---------- signed in: enter ----------
-- p: {name, mobile, current_car, dream_car, terms_version, terms (true), marketing_ok, whatsapp_ok, source, code}
create or replace function public.promotion_enter(p_slug text, p jsonb) returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare u uuid := public.require_user(); pr public.promotions; c public.promo_codes; v_mobile text; v_name text; v_src text;
        v_ip text; v_same int; v_status text := 'valid'; v_reason text; e_id uuid; v_at timestamptz;
begin
  if not public.promo_on() then raise exception 'No promotion is running right now.'; end if;
  select * into pr from public.promotions where slug = lower(coalesce(p_slug, '')) for update;
  if pr.id is null or not public.promo_is_open(pr) then raise exception 'This promotion is not open for entries.'; end if;
  if exists (select 1 from public.admins where user_id = u) then raise exception 'Saaz team members can''t enter Saaz promotions.'; end if;
  if (select email_confirmed_at from auth.users where id = u) is null then raise exception 'Confirm your email first: open the link Saaz sent you.'; end if;
  if exists (select 1 from public.promo_entries where promotion_id = pr.id and user_id = u) then raise exception 'You have already entered this draw. One entry per person.'; end if;
  if coalesce((p->>'terms')::boolean, false) is not true then raise exception 'Tick that you accept the terms and conditions.'; end if;
  if coalesce(p->>'terms_version', '') <> pr.terms_version then raise exception 'The terms changed while you were reading. Reload the page and read them again.'; end if;
  v_name := btrim(regexp_replace(coalesce(p->>'name', ''), '\s+', ' ', 'g'));
  if length(v_name) < 3 or length(v_name) > 80 then raise exception 'Write your full name (3 to 80 characters).'; end if;
  v_mobile := public.promo_mobile(p->>'mobile');
  if v_mobile is null then raise exception 'Write a Ugandan mobile number, for example 0772 123456.'; end if;
  -- Once SMS is connected and require_phone_verified is on, entries need the verified mobile on the account (part 24 phone check)
  if coalesce((public.setting('require_phone_verified'))::text::boolean, false) then
    if not coalesce((select phone_verified from public.profiles where id = u), false) then raise exception 'Verify your mobile number first: My account, Mobile number.'; end if;
    if v_mobile is distinct from public.promo_mobile((select mobile from public.profiles where id = u)) then raise exception 'Use the verified mobile number on your account.'; end if;
  end if;
  if length(btrim(coalesce(p->>'current_car', ''))) > 80 or length(btrim(coalesce(p->>'dream_car', ''))) > 80 then raise exception 'Keep car names under 80 characters.'; end if;
  if length(btrim(coalesce(p->>'current_car', ''))) < 2 then raise exception 'Write the car you drive now, or "None".'; end if;
  if length(btrim(coalesce(p->>'dream_car', ''))) < 2 then raise exception 'Write the car you would like next.'; end if;
  if nullif(btrim(coalesce(p->>'code', '')), '') is not null then
    select * into c from public.promo_codes where promotion_id = pr.id and code = upper(btrim(p->>'code')) and active for update;
    if c.id is null then raise exception 'That promo code isn''t valid for this promotion.'; end if;
    if c.max_uses is not null and (select count(*) from public.promo_entries where code_id = c.id) >= c.max_uses then raise exception 'That promo code has been used up.'; end if;
  elsif pr.needs_code then raise exception 'This promotion needs a promo code.'; end if;
  v_src := lower(coalesce(p->>'source', ''));
  if not exists (select 1 from public.promo_links where promotion_id = pr.id and channel = v_src) then v_src := 'direct'; end if;
  v_ip := public.promo_ip_hash(pr.id);
  select count(*) into v_same from public.promo_entries where promotion_id = pr.id and ip_hash = v_ip;
  if v_same >= coalesce((public.setting('promo_flag_same_address'))::text::int, 3) then
    v_status := 'flagged'; v_reason := 'Many entries from one network address (' || (v_same + 1) || ')';
  end if;
  insert into public.promo_entries (promotion_id, user_id, name, mobile, email, current_car, dream_car, source, code_id, terms_version,
      marketing_ok, whatsapp_ok, ip_hash, status, status_reason)
    values (pr.id, u, v_name, v_mobile, (select email from public.profiles where id = u), btrim(p->>'current_car'), btrim(p->>'dream_car'), v_src, c.id,
      pr.terms_version, coalesce((p->>'marketing_ok')::boolean, false), coalesce((p->>'whatsapp_ok')::boolean, false), v_ip, v_status, v_reason)
    returning id, created_at into e_id, v_at;
  perform public.audit('buyer', 'promotion', pr.id::text, 'entered promotion', jsonb_build_object('entry', e_id, 'source', v_src, 'flagged', v_status = 'flagged'));
  return jsonb_build_object('entered', true, 'at', v_at, 'closes_at', pr.closes_at);
end $$;
revoke execute on function public.promotion_enter(text, jsonb) from public, anon;
grant execute on function public.promotion_enter(text, jsonb) to authenticated;

-- ---------- admin (full admins only: the entries are personal data) ----------
create or replace function public.admin_promotions() returns jsonb language plpgsql volatile security definer set search_path = public as $$
begin
  perform public.require_full_admin();
  perform public.promo_purge();
  return jsonb_build_object('enabled', public.promo_on(),
    'toggles', (select coalesce(jsonb_agg(jsonb_build_object('at', t.at, 'enabled', t.enabled, 'reason', t.reason,
        'by', (select coalesce(nullif(name, ''), email) from public.profiles where id = t.actor)) order by t.id desc), '[]') from public.promo_toggles t),
    'promotions', (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'slug', p.slug, 'kind', p.kind, 'title', p.title, 'status', p.status,
        'opens_at', p.opens_at, 'closes_at', p.closes_at, 'open', public.promo_is_open(p), 'purged_at', p.purged_at,
        'entries', (select count(*) from public.promo_entries e where e.promotion_id = p.id),
        'flagged', (select count(*) from public.promo_entries e where e.promotion_id = p.id and e.status = 'flagged')) order by p.created_at desc), '[]') from public.promotions p));
end $$;

create or replace function public.admin_promotion_switch(p_on boolean, p_reason text) returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); r text := nullif(btrim(coalesce(p_reason, '')), '');
begin
  if p_on is null then raise exception 'Say on or off.'; end if;
  if p_on = public.promo_on() then raise exception 'Promotions are already %.', case when p_on then 'on' else 'off' end; end if;
  if not p_on and (r is null or length(r) < 10) then raise exception 'Write why promotions are being switched off (10 characters or more).'; end if;
  insert into public.promo_toggles (actor, enabled, reason) values (u, p_on, r);
  perform public.audit('admin', 'setting', 'promotions', case when p_on then 'promotions switched on' else 'promotions switched off' end,
    jsonb_build_object('reason', r, 'open', (select count(*) from public.promotions where status = 'open')));
  return jsonb_build_object('enabled', p_on);
end $$;

-- Create (p_id null) or edit. After a promotion opens, only the summary and a later closing time can change.
create or replace function public.admin_promotion_save(p_id uuid, p jsonb) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); o public.promotions; n public.promotions; k text;
begin
  if p_id is null then
    insert into public.promotions (slug, title, created_by) values (lower(btrim(coalesce(p->>'slug', ''))), btrim(coalesce(p->>'title', '')), u) returning * into o;
    p_id := o.id;
    perform public.audit('admin', 'promotion', p_id::text, 'promotion created', jsonb_build_object('slug', o.slug));
  end if;
  select * into o from public.promotions where id = p_id for update;
  if o.id is null then raise exception 'Promotion not found.'; end if;
  if o.status in ('drawn','cancelled','closed') then raise exception 'This promotion is % and can''t be changed.', o.status; end if;
  if o.status = 'open' then
    for k in select jsonb_object_keys(p) loop
      if k not in ('summary', 'closes_at') then raise exception 'Only the summary and the closing time can change once a promotion is open.'; end if;
    end loop;
    if p ? 'closes_at' and (p->>'closes_at')::timestamptz <= greatest(now(), o.closes_at) then raise exception 'An open promotion can only close later, not earlier.'; end if;
  end if;
  update public.promotions set
    slug = case when p ? 'slug' then lower(btrim(p->>'slug')) else slug end,
    title = case when p ? 'title' then btrim(p->>'title') else title end,
    prize = case when p ? 'prize' then btrim(p->>'prize') else prize end,
    summary = case when p ? 'summary' then btrim(p->>'summary') else summary end,
    opens_at = case when p ? 'opens_at' then nullif(p->>'opens_at', '')::timestamptz else opens_at end,
    closes_at = case when p ? 'closes_at' then nullif(p->>'closes_at', '')::timestamptz else closes_at end,
    winners = case when p ? 'winners' then (p->>'winners')::int else winners end,
    reserves = case when p ? 'reserves' then (p->>'reserves')::int else reserves end,
    needs_code = case when p ? 'needs_code' then (p->>'needs_code')::boolean else needs_code end,
    permit_no = case when p ? 'permit_no' then btrim(p->>'permit_no') else permit_no end,
    terms_version = case when p ? 'terms_version' then btrim(p->>'terms_version') else terms_version end,
    terms = case when p ? 'terms' then btrim(p->>'terms') else terms end,
    retention_days = case when p ? 'retention_days' then (p->>'retention_days')::int else retention_days end,
    updated_at = now()
  where id = p_id returning * into n;
  perform public.audit('admin', 'promotion', p_id::text, 'promotion edited', jsonb_build_object('fields', (select jsonb_agg(x) from jsonb_object_keys(p) x)));
  return p_id;
end $$;

-- draft -> open (needs title, prize, dates, permit number, T&C text and version), open -> closed, draft or open -> cancelled
create or replace function public.admin_promotion_status(p_id uuid, p_to text, p_reason text) returns text language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); o public.promotions; r text := nullif(btrim(coalesce(p_reason, '')), '');
begin
  select * into o from public.promotions where id = p_id for update;
  if o.id is null then raise exception 'Promotion not found.'; end if;
  if not ((o.status = 'draft' and p_to in ('open','cancelled')) or (o.status = 'open' and p_to in ('closed','cancelled'))) then
    raise exception 'A % promotion can''t move to %.', o.status, coalesce(p_to, 'nothing'); end if;
  if p_to = 'open' then
    if o.permit_no = '' then raise exception 'Add the permit number before opening. A draw can''t open without it.'; end if;
    if o.terms = '' or o.terms_version = '' then raise exception 'Add the terms and conditions and their version before opening.'; end if;
    if o.prize = '' then raise exception 'Say what the prize is before opening.'; end if;
    if o.opens_at is null or o.closes_at is null then raise exception 'Set the opening and closing times before opening.'; end if;
    if o.closes_at <= now() then raise exception 'The closing time has passed. Set a later one.'; end if;
  end if;
  if p_to = 'cancelled' and (r is null or length(r) < 10) then raise exception 'Write why it is cancelled (10 characters or more).'; end if;
  update public.promotions set status = p_to, updated_at = now(), closes_at = case when p_to = 'closed' and closes_at > now() then now() else closes_at end where id = p_id;
  perform public.audit('admin', 'promotion', p_id::text, 'promotion ' || p_to, jsonb_build_object('from', o.status, 'reason', r));
  return p_to;
end $$;

create or replace function public.admin_promotion_link(p_promotion uuid, p_channel text, p_label text) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); i uuid;
begin
  if not exists (select 1 from public.promotions where id = p_promotion and status in ('draft','open')) then raise exception 'Links can be added only to a draft or open promotion.'; end if;
  insert into public.promo_links (promotion_id, channel, label) values (p_promotion, lower(btrim(coalesce(p_channel, ''))), btrim(coalesce(p_label, '')))
    on conflict (promotion_id, channel) do update set label = excluded.label returning id into i;
  perform public.audit('admin', 'promotion', p_promotion::text, 'promotion link saved', jsonb_build_object('channel', lower(p_channel)));
  return i;
end $$;

create or replace function public.admin_promotion_code(p_promotion uuid, p_code text, p_label text, p_max int, p_active boolean) returns uuid language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); i uuid;
begin
  if not exists (select 1 from public.promotions where id = p_promotion and status in ('draft','open')) then raise exception 'Codes can be changed only on a draft or open promotion.'; end if;
  insert into public.promo_codes (promotion_id, code, label, max_uses, active) values (p_promotion, upper(btrim(coalesce(p_code, ''))), btrim(coalesce(p_label, '')), p_max, coalesce(p_active, true))
    on conflict (promotion_id, code) do update set label = excluded.label, max_uses = excluded.max_uses, active = excluded.active returning id into i;
  perform public.audit('admin', 'promotion', p_promotion::text, 'promotion code saved', jsonb_build_object('code', upper(p_code), 'active', coalesce(p_active, true), 'max', p_max));
  return i;
end $$;

-- One promotion: details, links, codes, the draw and results. Entries are paged (p_export: up to 10,000 rows, logged).
create or replace function public.admin_promotion(p_id uuid, p_q text default null, p_status text default null, p_source text default null,
  p_page int default 1, p_size int default 50, p_export boolean default false) returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); o public.promotions; lim int; off int; total int; rows jsonb; q text := nullif(btrim(coalesce(p_q, '')), '');
begin
  select * into o from public.promotions where id = p_id;
  if o.id is null then raise exception 'Promotion not found.'; end if;
  lim := case when p_export then 10000 else least(greatest(coalesce(p_size, 50), 1), 200) end;
  off := case when p_export then 0 else (greatest(coalesce(p_page, 1), 1) - 1) * lim end;
  select count(*) into total from public.promo_entries e where e.promotion_id = p_id
    and (p_status is null or e.status = p_status) and (p_source is null or e.source = p_source)
    and (q is null or e.name ilike '%' || q || '%' or e.email ilike '%' || q || '%' or e.mobile ilike '%' || q || '%' or e.dream_car ilike '%' || q || '%');
  select coalesce(jsonb_agg(x order by x->>'at' desc), '[]') into rows from (
    select jsonb_build_object('id', e.id, 'at', e.created_at, 'name', e.name, 'email', e.email, 'mobile', e.mobile, 'current_car', e.current_car,
      'dream_car', e.dream_car, 'source', e.source, 'code', c.code, 'marketing_ok', e.marketing_ok, 'whatsapp_ok', e.whatsapp_ok,
      'status', e.status, 'status_reason', e.status_reason, 'terms_version', e.terms_version, 'user_id', e.user_id) x
    from public.promo_entries e left join public.promo_codes c on c.id = e.code_id
    where e.promotion_id = p_id and (p_status is null or e.status = p_status) and (p_source is null or e.source = p_source)
      and (q is null or e.name ilike '%' || q || '%' or e.email ilike '%' || q || '%' or e.mobile ilike '%' || q || '%' or e.dream_car ilike '%' || q || '%')
    order by e.created_at desc limit lim offset off) s;
  if p_export then
    perform public.audit('admin', 'promotion', p_id::text, 'promotion entries exported', jsonb_build_object('rows', total, 'status', p_status, 'source', p_source, 'search', q));
  end if;
  return jsonb_build_object('promotion', to_jsonb(o) - 'created_by', 'open', public.promo_is_open(o), 'switch_on', public.promo_on(),
    'links', (select coalesce(jsonb_agg(jsonb_build_object('channel', l.channel, 'label', l.label,
        'entries', (select count(*) from public.promo_entries e where e.promotion_id = p_id and e.source = l.channel)) order by l.created_at), '[]') from public.promo_links l where l.promotion_id = p_id),
    'codes', (select coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'code', c.code, 'label', c.label, 'max_uses', c.max_uses, 'active', c.active,
        'uses', (select count(*) from public.promo_entries e where e.code_id = c.id)) order by c.created_at), '[]') from public.promo_codes c where c.promotion_id = p_id),
    'draw', (select jsonb_build_object('at', d.at, 'seed', d.seed, 'entries_in_draw', d.entries_in_draw, 'witness', d.witness,
        'by', (select coalesce(nullif(name, ''), email) from public.profiles where id = d.actor)) from public.promo_draws d where d.promotion_id = p_id),
    'results', (select coalesce(jsonb_agg(jsonb_build_object('id', r.id, 'rank', r.rank, 'role', r.role, 'state', r.state, 'note', r.note, 'updated_at', r.updated_at,
        'entry_id', e.id, 'name', e.name, 'mobile', e.mobile, 'email', e.email) order by r.rank), '[]')
      from public.promo_results r join public.promo_entries e on e.id = r.entry_id where r.promotion_id = p_id),
    'total', total, 'page', case when p_export then 1 else greatest(coalesce(p_page, 1), 1) end, 'size', lim, 'rows', rows);
end $$;

create or replace function public.admin_promotion_entry(p_entry uuid, p_to text, p_reason text) returns text language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); e public.promo_entries; r text := nullif(btrim(coalesce(p_reason, '')), '');
begin
  select * into e from public.promo_entries where id = p_entry for update;
  if e.id is null then raise exception 'Entry not found.'; end if;
  if p_to not in ('valid','flagged','invalid') then raise exception 'Status must be valid, flagged or invalid.'; end if;
  if r is null or length(r) < 10 then raise exception 'Write the reason (10 characters or more). It goes in the history.'; end if;
  if exists (select 1 from public.promo_draws where promotion_id = e.promotion_id) then raise exception 'The draw has run. Use the winner steps instead.'; end if;
  update public.promo_entries set status = p_to, status_reason = r, status_by = u where id = p_entry;
  perform public.audit('admin', 'promotion', e.promotion_id::text, 'promotion entry ' || p_to, jsonb_build_object('entry', p_entry, 'from', e.status, 'reason', r));
  return p_to;
end $$;

-- The draw. Only a closed promotion, once. Valid entries only (flagged and invalid are left out).
create or replace function public.admin_promotion_draw(p_id uuid, p_witness text) returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); o public.promotions; v_seed text; n int; w text := nullif(btrim(coalesce(p_witness, '')), '');
begin
  select * into o from public.promotions where id = p_id for update;
  if o.id is null then raise exception 'Promotion not found.'; end if;
  if o.status <> 'closed' then raise exception 'Close the promotion before the draw.'; end if;
  if exists (select 1 from public.promo_draws where promotion_id = p_id) then raise exception 'The draw for this promotion has already run.'; end if;
  if w is null or length(w) < 3 then raise exception 'Name the witness (for example the regulator''s supervisor).'; end if;
  if exists (select 1 from public.promo_entries where promotion_id = p_id and status = 'flagged') then raise exception 'Clear or invalidate every flagged entry first.'; end if;
  select count(*) into n from public.promo_entries where promotion_id = p_id and status = 'valid';
  if n = 0 then raise exception 'No valid entries to draw from.'; end if;
  v_seed := md5(gen_random_uuid()::text || clock_timestamp()::text) || md5(gen_random_uuid()::text);
  insert into public.promo_draws (promotion_id, actor, seed, entries_in_draw, witness) values (p_id, u, v_seed, n, w);
  insert into public.promo_results (promotion_id, entry_id, rank, role)
    select p_id, id, rk, case when rk <= o.winners then 'winner' else 'reserve' end from (
      select id, row_number() over (order by md5(v_seed || id::text), id) rk from public.promo_entries where promotion_id = p_id and status = 'valid') s
    where rk <= o.winners + o.reserves;
  update public.promotions set status = 'drawn', updated_at = now() where id = p_id;
  perform public.audit('admin', 'promotion', p_id::text, 'promotion drawn', jsonb_build_object('seed', v_seed, 'entries', n, 'witness', w));
  return jsonb_build_object('seed', v_seed, 'entries_in_draw', n, 'picked', least(n, o.winners + o.reserves));
end $$;

-- Winner steps. pending -> contacted (sends the in-app notice) -> confirmed -> handed_over; contacted or pending -> declined,
-- no_reply or ineligible: that winner steps down and the next reserve becomes a winner (still pending, to be contacted).
create or replace function public.admin_promotion_result(p_result uuid, p_to text, p_note text) returns jsonb language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); r public.promo_results; o public.promotions; e public.promo_entries; nx uuid; t text := nullif(btrim(coalesce(p_note, '')), '');
begin
  select * into r from public.promo_results where id = p_result for update;
  if r.id is null then raise exception 'Result not found.'; end if;
  if r.role <> 'winner' then raise exception 'Only a current winner moves through these steps.'; end if;
  if not ((r.state = 'pending' and p_to in ('contacted','declined','no_reply','ineligible'))
       or (r.state = 'contacted' and p_to in ('confirmed','declined','no_reply','ineligible'))
       or (r.state = 'confirmed' and p_to in ('handed_over','ineligible'))) then raise exception 'A % winner can''t move to %.', r.state, coalesce(p_to, 'nothing'); end if;
  if p_to in ('declined','no_reply','ineligible') and (t is null or length(t) < 10) then raise exception 'Write what happened (10 characters or more).'; end if;
  select * into o from public.promotions where id = r.promotion_id;
  select * into e from public.promo_entries where id = r.entry_id;
  update public.promo_results set state = p_to, note = coalesce(t, note), updated_at = now(),
    role = case when p_to in ('declined','no_reply','ineligible') then 'stepped_down' else role end where id = r.id;
  if p_to = 'contacted' then
    perform public.notify(e.user_id, 'promotion_winner', 'You were drawn in ' || o.title || '. Saaz contacts winners only through this inbox and the number on the promotion page. Saaz never asks for money to release a prize.', '#/promotions/' || o.slug, '{app,email,sms}');
  end if;
  if p_to in ('declined','no_reply','ineligible') then
    select id into nx from public.promo_results where promotion_id = r.promotion_id and role = 'reserve' order by rank limit 1;
    if nx is not null then update public.promo_results set role = 'winner', updated_at = now() where id = nx; end if;
  end if;
  perform public.audit('admin', 'promotion', r.promotion_id::text, 'promotion winner ' || p_to, jsonb_build_object('rank', r.rank, 'note', t, 'next_reserve', nx));
  return jsonb_build_object('state', p_to, 'next_reserve', nx);
end $$;

-- Report: entries by day (East Africa Time), by source and code; consent counts; entrants who went on to list a car or make an offer
create or replace function public.admin_promotion_report(p_id uuid) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); o public.promotions;
begin
  select * into o from public.promotions where id = p_id;
  if o.id is null then raise exception 'Promotion not found.'; end if;
  return jsonb_build_object(
    'total', (select count(*) from public.promo_entries where promotion_id = p_id),
    'valid', (select count(*) from public.promo_entries where promotion_id = p_id and status = 'valid'),
    'flagged', (select count(*) from public.promo_entries where promotion_id = p_id and status = 'flagged'),
    'invalid', (select count(*) from public.promo_entries where promotion_id = p_id and status = 'invalid'),
    'marketing_ok', (select count(*) from public.promo_entries where promotion_id = p_id and marketing_ok),
    'whatsapp_ok', (select count(*) from public.promo_entries where promotion_id = p_id and whatsapp_ok),
    'by_day', (select coalesce(jsonb_agg(jsonb_build_object('day', d, 'n', n) order by d), '[]') from (
        select (created_at at time zone 'Africa/Kampala')::date d, count(*) n from public.promo_entries where promotion_id = p_id group by 1) s),
    'by_source', (select coalesce(jsonb_agg(jsonb_build_object('source', source, 'n', n) order by n desc, source), '[]') from (
        select source, count(*) n from public.promo_entries where promotion_id = p_id group by 1) s),
    'by_code', (select coalesce(jsonb_agg(jsonb_build_object('code', code, 'label', label, 'n', n) order by n desc, code), '[]') from (
        select c.code, c.label, count(e.id) n from public.promo_codes c left join public.promo_entries e on e.code_id = c.id where c.promotion_id = p_id group by 1, 2) s),
    'listed_after', (select count(distinct e.user_id) from public.promo_entries e join public.listings l on l.seller_id = e.user_id and l.created_at > e.created_at where e.promotion_id = p_id),
    'offered_after', (select count(distinct e.user_id) from public.promo_entries e join public.deals d on d.buyer_id = e.user_id and d.created_at > e.created_at where e.promotion_id = p_id),
    'top_dream_cars', (select coalesce(jsonb_agg(jsonb_build_object('car', car, 'n', n) order by n desc, car), '[]') from (
        select initcap(lower(dream_car)) car, count(*) n from public.promo_entries where promotion_id = p_id and dream_car <> '' group by 1 order by 2 desc, 1 limit 10) s));
end $$;

-- Grants: admin functions to signed-in sessions only (each checks for a full admin first)
do $$ declare f text; begin
  foreach f in array array['public.admin_promotions()','public.admin_promotion_switch(boolean,text)','public.admin_promotion_save(uuid,jsonb)',
      'public.admin_promotion_status(uuid,text,text)','public.admin_promotion_link(uuid,text,text)','public.admin_promotion_code(uuid,text,text,int,boolean)',
      'public.admin_promotion(uuid,text,text,text,int,int,boolean)','public.admin_promotion_entry(uuid,text,text)','public.admin_promotion_draw(uuid,text)',
      'public.admin_promotion_result(uuid,text,text)','public.admin_promotion_report(uuid)'] loop
    execute 'revoke execute on function ' || f || ' from public, anon';
    execute 'grant execute on function ' || f || ' to authenticated';
  end loop;
end $$;
