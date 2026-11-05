-- Part 25: Custom audience for Announcements (BA-0013, 4 Nov 2026). Run after part 24. Safe to run twice.
-- James chose C (4 Nov 2026, live chat): filters on data Saaz already has, plus named people picked one by one.
-- Live since 4 Nov 2026: James approved and ran it in the SQL Editor. Checked after (read-only): new functions in place, old ones gone, none callable by visitors.
--
-- Custom audience (p_audience = 'custom', p_filter jsonb):
--   roles        any of 'sellers' (listed a car), 'buyers' (saved a car or made an offer), 'garages' (certified garage team). Empty: everyone.
--   verified     true: only people whose mobile is verified
--   active_days  signed in within the last N days
--   joined_days  account made within the last N days
--   makes        car makes they listed or saved (any of, not case sensitive)
--   models       car models they listed or saved (any of, not case sensitive)
--   people       user ids picked by name, added on top of whoever the filters match
-- With people and no filters, only those people get it. Suspended accounts never do. Saaz operates in Uganda only, so there is no country filter.
-- The rules for SMS stay as in part 24: opted in to SMS news (or a promotion's marketing tick), verified, not opted out, 08:00 to 20:00 EAT.

alter table public.announcements add column if not exists filter jsonb;

-- Who matches a custom filter (no grants: only the functions below use it)
create or replace function public.custom_audience(p jsonb) returns table (user_id uuid) language plpgsql stable security definer set search_path = public as $$
declare roles text[] := coalesce((select array_agg(x) from jsonb_array_elements_text(p->'roles') x), '{}');
        makes text[] := coalesce((select array_agg(lower(btrim(x))) from jsonb_array_elements_text(p->'makes') x where btrim(x) <> ''), '{}');
        models text[] := coalesce((select array_agg(lower(btrim(x))) from jsonb_array_elements_text(p->'models') x where btrim(x) <> ''), '{}');
        people uuid[] := coalesce((select array_agg(x::uuid) from jsonb_array_elements_text(p->'people') x), '{}');
        ver boolean := coalesce((p->>'verified')::boolean, false);
        act int := nullif(p->>'active_days', '')::int; joi int := nullif(p->>'joined_days', '')::int;
        has_filter boolean;
begin
  if roles <> '{}' and not roles <@ array['sellers','buyers','garages'] then raise exception 'Roles can be sellers, buyers or garages.'; end if;
  if act is not null and act not between 1 and 3650 then raise exception 'Active within: 1 to 3650 days.'; end if;
  if joi is not null and joi not between 1 and 3650 then raise exception 'Joined within: 1 to 3650 days.'; end if;
  if cardinality(people) > 500 then raise exception 'Pick at most 500 people by name. Use filters for more.'; end if;
  has_filter := roles <> '{}' or ver or act is not null or joi is not null or makes <> '{}' or models <> '{}';
  if not has_filter and people = '{}' then raise exception 'Choose at least one filter or one person.'; end if;
  return query
  select pr.id from public.profiles pr join auth.users au on au.id = pr.id
  where not pr.suspended and (
    (has_filter
     and (roles = '{}'
          or ('sellers' = any(roles) and exists (select 1 from public.listings l where l.seller_id = pr.id))
          or ('buyers' = any(roles) and (exists (select 1 from public.saves s where s.user_id = pr.id) or exists (select 1 from public.deals d where d.buyer_id = pr.id)))
          or ('garages' = any(roles) and exists (select 1 from public.garage_members m join public.garages g on g.id = m.garage_id
                                                 where m.user_id = pr.id and m.status = 'active' and g.status = 'certified')))
     and (not ver or pr.phone_verified)
     and (act is null or au.last_sign_in_at > now() - make_interval(days => act))
     and (joi is null or pr.created_at > now() - make_interval(days => joi))
     and (makes = '{}' or exists (select 1 from public.listings l where lower(l.make) = any(makes)
                                   and (l.seller_id = pr.id or exists (select 1 from public.saves s where s.listing_id = l.id and s.user_id = pr.id))))
     and (models = '{}' or exists (select 1 from public.listings l where lower(l.model) = any(models)
                                    and (l.seller_id = pr.id or exists (select 1 from public.saves s where s.listing_id = l.id and s.user_id = pr.id)))))
    or pr.id = any(people));
end $$;
revoke execute on function public.custom_audience(jsonb) from public, anon, authenticated;

-- The audience of an announcement, now with 'custom'
drop function if exists public.announce_audience(text, uuid);
create or replace function public.announce_audience(p_audience text, p_promotion uuid, p_filter jsonb default null) returns table (user_id uuid, news_ok boolean)
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
    union select c.user_id, null::boolean from public.custom_audience(case when p_audience = 'custom' then p_filter else '{"people":["00000000-0000-0000-0000-000000000000"]}'::jsonb end) c
          where p_audience = 'custom'
  ) x left join public.notify_prefs pf on pf.user_id = x.id
  where x.id is not null
$$;
revoke execute on function public.announce_audience(text, uuid, jsonb) from public, anon, authenticated;

-- Preview and send take the filter. The old signatures go, so the page can't call a version without it.
drop function if exists public.admin_announce_preview(text, uuid, text[], text);
drop function if exists public.admin_announce(text, uuid, text[], text, text);

create or replace function public.admin_announce_preview(p_audience text, p_promotion uuid, p_channels text[], p_body text, p_filter jsonb default null) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); n int; n_sms int; reasons jsonb; sample jsonb;
        seg int := public.sms_segments(public.sms_text(coalesce(p_body, '') || ' Stop these in your Saaz account.'));
        price numeric := nullif(public.setting('sms_price_ugx')#>>'{}', '')::numeric; want boolean := 'sms' = any(coalesce(p_channels, '{}'));
begin
  if p_audience not in ('all','sellers','buyers','garages','promotion','custom') then raise exception 'Choose an audience.'; end if;
  if p_audience = 'promotion' and not exists (select 1 from public.promotions where id = p_promotion) then raise exception 'Choose the promotion.'; end if;
  if p_audience = 'custom' and p_filter is null then raise exception 'Choose at least one filter or one person.'; end if;
  with aud as (select user_id, bool_or(news_ok) ok from public.announce_audience(p_audience, p_promotion, p_filter) group by 1),
  t as (select case when s.mobile is null then s.reason when not aud.ok then 'Not opted in to SMS news' end reason
        from aud cross join lateral public.sms_target(aud.user_id, 'broadcast') s)
  select count(*), count(*) filter (where reason is null),
         coalesce((select jsonb_object_agg(r, c) from (select reason r, count(*) c from t where reason is not null group by 1) z), '{}')
    into n, n_sms, reasons from t;
  select coalesce(jsonb_agg(nm order by nm), '[]') into sample from (
    select coalesce(nullif(p.name, ''), p.email) nm from (select distinct user_id from public.announce_audience(p_audience, p_promotion, p_filter)) a
      join public.profiles p on p.id = a.user_id order by 1 limit 10) z;
  return jsonb_build_object('people', n, 'sms', case when want then n_sms else 0 end, 'sms_not_sent', case when want then reasons else '{}'::jsonb end,
    'segments', seg, 'price_ugx', price, 'cost_ugx', case when want and price is not null then price * seg * n_sms end,
    'sms_from', public.sms_send_window(now()), 'sample', sample);
end $$;

create or replace function public.admin_announce(p_audience text, p_promotion uuid, p_channels text[], p_body text, p_link text, p_filter jsonb default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); a_id bigint; n_app int := 0; n_sms int := 0; n_skip int := 0; b text := btrim(coalesce(p_body, ''));
        maxn int := coalesce((public.setting('sms_max_audience'))::text::int, 20000); total int; at_ timestamptz := public.sms_send_window(now());
begin
  if length(b) < 10 or length(b) > 450 then raise exception 'Write the message (10 to 450 characters).'; end if;
  if p_channels is null or not (p_channels <@ array['app','sms']) or not ('app' = any(p_channels)) then raise exception 'Channels: the app inbox, and SMS if wanted.'; end if;
  if p_link is not null and p_link !~ '^#/[^\s"''<>]*$' then raise exception 'The link must be a Saaz page (starting #/).'; end if;
  if p_audience not in ('all','sellers','buyers','garages','promotion','custom') then raise exception 'Choose an audience.'; end if;
  if p_audience = 'promotion' and not exists (select 1 from public.promotions where id = p_promotion) then raise exception 'Choose the promotion.'; end if;
  if p_audience = 'custom' and p_filter is null then raise exception 'Choose at least one filter or one person.'; end if;
  select count(distinct user_id) into total from public.announce_audience(p_audience, p_promotion, p_filter);
  if total = 0 then raise exception 'Nobody is in that audience.'; end if;
  if total > maxn then raise exception 'That audience is % people, more than the limit of %.', total, maxn; end if;
  insert into public.announcements (actor, audience, promotion_id, channels, body, link, filter)
    values (u, p_audience, p_promotion, p_channels, b, p_link, case when p_audience = 'custom' then p_filter end) returning id into a_id;
  insert into public.notifications (user_id, kind, body, link, channels)
    select distinct user_id, 'announcement', b, p_link, '{app}'::text[] from public.announce_audience(p_audience, p_promotion, p_filter);
  get diagnostics n_app = row_count;
  if 'sms' = any(p_channels) then
    with aud as (select user_id, bool_or(news_ok) news_ok from public.announce_audience(p_audience, p_promotion, p_filter) group by 1),
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
  perform public.audit('admin', 'setting', 'announcement', 'announcement sent', jsonb_build_object('id', a_id, 'audience', p_audience, 'filter', p_filter, 'app', n_app, 'sms', n_sms, 'skipped', n_skip));
  return jsonb_build_object('id', a_id, 'app', n_app, 'sms', n_sms, 'sms_skipped', n_skip, 'sms_from', at_);
end $$;

-- Find people by name, email or mobile to add them by name (full admins; at most 20 results)
create or replace function public.admin_people_search(p_q text) returns jsonb language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_full_admin(); q text := btrim(coalesce(p_q, ''));
begin
  if length(q) < 2 then return '[]'::jsonb; end if;
  return (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'name', p.name, 'email', p.email, 'mobile', p.mobile, 'verified', p.phone_verified) order by p.name), '[]')
    from (select * from public.profiles p where not p.suspended and (p.name ilike '%' || q || '%' or p.email ilike '%' || q || '%' or p.mobile ilike '%' || q || '%')
          order by p.name limit 20) p);
end $$;

-- The announcement list shows how a custom audience was chosen
create or replace function public.admin_announcements() returns jsonb language plpgsql stable security definer set search_path = public as $$
declare u uuid := public.require_full_admin();
begin
  return jsonb_build_object(
    'list', (select coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'at', a.at, 'audience', a.audience, 'promotion', (select title from public.promotions where id = a.promotion_id),
        'filter', a.filter, 'channels', a.channels, 'body', a.body, 'counts', a.counts,
        'by', (select coalesce(nullif(name, ''), email) from public.profiles where id = a.actor)) order by a.id desc), '[]')
      from (select * from public.announcements order by id desc limit 100) a),
    'promotions', (select coalesce(jsonb_agg(jsonb_build_object('id', id, 'title', title) order by created_at desc), '[]') from public.promotions where status <> 'draft'),
    'optouts', (select coalesce(jsonb_agg(jsonb_build_object('mobile', mobile, 'at', at, 'reason', reason) order by at desc), '[]') from public.sms_optout),
    'price_ugx', nullif(public.setting('sms_price_ugx')#>>'{}', ''));
end $$;

insert into public.request_limits (path, max_hits, per_seconds, note) values
  ('/rpc/admin_people_search', 300, 3600, 'Admin search for people by name')
on conflict (path) do nothing;

do $$ declare f text; begin
  foreach f in array array['public.admin_announce_preview(text,uuid,text[],text,jsonb)','public.admin_announce(text,uuid,text[],text,text,jsonb)',
      'public.admin_people_search(text)','public.admin_announcements()'] loop
    execute 'revoke execute on function ' || f || ' from public, anon';
    execute 'grant execute on function ' || f || ' to authenticated';
  end loop;
end $$;
