-- Part 16: Admin reports, slice 1 (Inventory, Listing funnel).
-- Reads only. No table changes, no new events: everything these two reports need is already recorded
-- (listings, listing_views, saves, deals, audit_log). Adds indexes, the metric glossary, one facts function and one report function.
-- Every formula lives here once. The admin page shows the definitions from report_glossary() and never computes a metric itself.
-- Dates are East Africa Time (Africa/Kampala). Timestamps stay stored in UTC.
-- jit is off for these functions (the live project already has it off): compiling the query costs more than running it.

-- ---------- indexes for report queries ----------
create index if not exists listing_views_day on public.listing_views (day, listing_id);
create index if not exists deals_listing_created on public.deals (listing_id, created_at);
create index if not exists deals_created on public.deals (created_at);
create index if not exists saves_created on public.saves (created_at);
create index if not exists audit_listing_action on public.audit_log (entity, action, entity_id, at);
create index if not exists listings_status on public.listings (status);
create index if not exists listings_make_model on public.listings (make, model);

-- ---------- groupings (one definition each) ----------
create or replace function public.rpt_status_group(p_status text) returns text language sql immutable as $$
  select case
    when p_status = 'draft' then 'draft'
    when p_status in ('awaiting_review','review_booked','awaiting_approval','changes_requested') then 'pending'
    when p_status in ('live','reserved') then 'live'
    when p_status = 'sold' then 'sold'
    when p_status = 're_review_due' then 'expired'
    when p_status in ('withdrawn','rejected') then 'removed'
    else 'other' end $$;

-- Same bands as the public browse page (build.py PRICE_BANDS)
create or replace function public.rpt_price_band(p_price bigint) returns text language sql immutable as $$
  select case when p_price is null then 'No price'
    when p_price < 20000000 then 'Under 20m' when p_price < 40000000 then '20m to 40m' when p_price < 70000000 then '40m to 70m'
    when p_price < 100000000 then '70m to 100m' else 'Over 100m' end $$;

create or replace function public.rpt_age_band(p_days int) returns text language sql immutable as $$
  select case when p_days is null then null when p_days <= 7 then '0 to 7 days' when p_days <= 30 then '8 to 30 days'
    when p_days <= 60 then '31 to 60 days' when p_days <= 90 then '61 to 90 days' else 'Over 90 days' end $$;

-- ---------- the glossary: label and definition of every metric and column ----------
-- Thresholds used in definitions are settings-free constants here, written into the text, so the words and the formula can't drift.
create or replace function public.report_glossary() returns jsonb language sql immutable as $$
  select jsonb_build_object(
    'listings',            jsonb_build_object('label','Listings','def','Cars in the database that match the filters, in any status.'),
    'status_group',        jsonb_build_object('label','Status','def','Draft: not sent. Pending: sent, in inspection or awaiting Saaz approval, or changes requested. Live: on the marketplace (live or reserved). Sold. Expired: the inspection lapsed and the car is off sale until re-inspected. Removed: withdrawn, unlisted or rejected.'),
    'live_now',            jsonb_build_object('label','Live now','def','Listings buyers can see right now: status live or reserved.'),
    'pending_now',         jsonb_build_object('label','Pending now','def','Listings sent by the seller and not yet live: awaiting inspection, inspection booked, awaiting Saaz approval, or changes requested.'),
    'draft_now',           jsonb_build_object('label','Drafts','def','Listings started and never sent, right now.'),
    'expired_now',         jsonb_build_object('label','Expired now','def','Listings whose inspection lapsed: off sale until re-inspected.'),
    'added',               jsonb_build_object('label','Added','def','Listings created in the period (East Africa Time).'),
    'sold',                jsonb_build_object('label','Sold','def','Listings marked sold in the period (sold date, East Africa Time).'),
    'removed',             jsonb_build_object('label','Removed','def','Listings withdrawn by the seller, unlisted or rejected by Saaz in the period (date of that action).'),
    'stale',               jsonb_build_object('label','Not updated in 30 days','def','Live, pending or expired listings whose record has not changed for more than 30 days.'),
    'no_photos',           jsonb_build_object('label','No photos','def','Listings in any status other than removed or sold with no photo.'),
    'make',                jsonb_build_object('label','Make','def','The make on the listing.'),
    'price_band',          jsonb_build_object('label','Price band','def','Asking price in UGX: under 20m, 20m to 40m, 40m to 70m, 70m to 100m, over 100m. Same bands as the marketplace filters.'),
    'age_days',            jsonb_build_object('label','Days on site','def','Whole days from the first time the listing went live to today (or to when it sold or was removed). For listings never live: days since it was created.'),
    'age_band',            jsonb_build_object('label','Age on site','def','Days on site in bands: 0 to 7, 8 to 30, 31 to 60, 61 to 90, over 90.'),
    'photos',              jsonb_build_object('label','Photos','def','Number of photos on the listing now.'),
    'desc_len',            jsonb_build_object('label','Description length','def','Characters in the seller''s description now.'),
    'updated_at',          jsonb_build_object('label','Last updated','def','Last change to the listing record (any field or status), East Africa Time.'),
    'views',               jsonb_build_object('label','Views','def','Listing views in the period. One view per person (or device, signed out) per listing per day; the seller''s own views are not counted.'),
    'saves',               jsonb_build_object('label','Saves','def','Times a signed-in buyer saved the listing in the period. A save removed later is not counted.'),
    'enquiries',           jsonb_build_object('label','Enquiries','def','Offers made by buyers in Saaz in the period. Saaz has no enquiry form, call or WhatsApp button: an offer is the only way a buyer contacts a seller, so it is the enquiry.'),
    'enquiry_rate',        jsonb_build_object('label','Enquiry rate','def','Enquiries per 100 views in the period. Blank when there were no views.'),
    'days_to_first_enquiry', jsonb_build_object('label','Days to first enquiry','def','Days from the first time the listing went live to its first offer ever (not limited to the period). Blank if no offer yet.'),
    'days_to_close',       jsonb_build_object('label','Days to sold or removed','def','Days from the first time the listing went live to the day it sold or was removed. Blank while still on sale.'),
    'similar_median',      jsonb_build_object('label','Similar cars median','def','Median asking price of all listings with the same make and model that are live, reserved or sold, in the same currency (this car included if it is one of them). Shown only when there are 3 or more other such cars.'),
    'price_vs_similar',    jsonb_build_object('label','Price vs similar','def','How far the asking price is above (+) or below (-) the similar cars median, in percent.'),
    'reason',              jsonb_build_object('label','Why','def','Visible reasons a listing may under- or over-perform: priced 10% or more above or below similar cars, fewer than 6 photos, description under 150 characters.'),
    'median_days_to_first_enquiry', jsonb_build_object('label','Median days to first enquiry','def','Median of days to first enquiry, over listings whose first offer was in the period.'),
    'median_days_to_sold', jsonb_build_object('label','Median days to sold','def','Median of days from first live to sold, over listings sold in the period.'),
    'seller',              jsonb_build_object('label','Seller','def','The seller''s name, or Saaz for cars Saaz owns.'),
    'ref',                 jsonb_build_object('label','Ref','def','The listing''s Saaz reference.'),
    'car',                 jsonb_build_object('label','Car','def','Year, make and model.'),
    'price',               jsonb_build_object('label','Price','def','Asking price now.'),
    'status',              jsonb_build_object('label','Detailed status','def','The listing''s exact status in Saaz.')
  ) $$;

-- ---------- one row per listing with every metric ----------
-- p_from / p_to: the period, as East Africa Time dates, both included.
create or replace function public.rpt_listing_facts(p_from date, p_to date)
returns table (
  id uuid, ref text, car text, make text, model text, year int, price bigint, currency text, status text, status_group text,
  seller_id uuid, seller text, saaz_owned boolean, photos int, desc_len int, created_at timestamptz, updated_at timestamptz,
  first_live_at timestamptz, sold_at timestamptz, removed_at timestamptz, age_days int, age_band text, price_band text,
  stale boolean, added_in_period boolean, sold_in_period boolean, removed_in_period boolean,
  views int, saves int, enquiries int, enquiry_rate numeric, first_enquiry_at timestamptz,
  days_to_first_enquiry numeric, days_to_close numeric, similar_count int, similar_median numeric, price_vs_similar numeric, reason text)
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  -- Set-based: each source table is read once and grouped, then joined to the listings (no per-row subqueries).
  with appr as (select a.entity_id, min(a.at) at from public.audit_log a where a.entity = 'listing' and a.action = 'approve' group by 1),
  remv as (select a.entity_id, max(a.at) at from public.audit_log a where a.entity = 'listing' and a.action in ('withdrawn','reject','unlist') group by 1),
  vw as (select v.listing_id, count(*)::int n from public.listing_views v where v.day between p_from and p_to group by 1),
  sv as (select s.listing_id, count(*)::int n from public.saves s where s.created_at >= p_from::timestamptz and s.created_at < (p_to + 1)::timestamptz group by 1),
  dl as (select d.listing_id, count(*) filter (where d.created_at >= p_from::timestamptz and d.created_at < (p_to + 1)::timestamptz)::int n, min(d.created_at) first_at
         from public.deals d group by 1),
  pool as (select o.make, o.model, o.currency, count(*)::int n, (percentile_cont(0.5) within group (order by o.price))::numeric med
           from public.listings o where o.status in ('live','reserved','sold') group by 1, 2, 3),
  f as (
    select l.*, public.rpt_status_group(l.status) sg, coalesce(p.name, case when l.saaz_owned then 'Saaz' end) seller_name,
      least(l.live_at, appr.at) flive,
      case when public.rpt_status_group(l.status) = 'removed' then remv.at end rem_at,
      coalesce(vw.n, 0) nviews, coalesce(sv.n, 0) nsaves, coalesce(dl.n, 0) nenq, dl.first_at fenq,
      -- other cars in the pool: the pool minus this listing if it is in it
      greatest(coalesce(pool.n, 0) - case when l.status in ('live','reserved','sold') then 1 else 0 end, 0) simn,
      case when coalesce(pool.n, 0) - case when l.status in ('live','reserved','sold') then 1 else 0 end >= 3 then pool.med end simmed
    from public.listings l
    left join public.profiles p on p.id = l.seller_id
    left join appr on appr.entity_id = l.id::text left join remv on remv.entity_id = l.id::text
    left join vw on vw.listing_id = l.id left join sv on sv.listing_id = l.id left join dl on dl.listing_id = l.id
    left join pool on pool.make = l.make and pool.model = l.model and pool.currency = l.currency
  )
  select f.id, f.ref, f.year || ' ' || f.make || ' ' || f.model, f.make, f.model, f.year, f.price, f.currency, f.status, f.sg,
    f.seller_id, f.seller_name, f.saaz_owned, coalesce(cardinality(f.photos), 0), coalesce(length(f.description), 0), f.created_at, f.updated_at,
    f.flive, f.sold_at, f.rem_at,
    x.age, public.rpt_age_band(x.age), public.rpt_price_band(f.price),
    (f.sg in ('live','pending','expired') and f.updated_at < now() - interval '30 days'),
    f.created_at >= p_from::timestamptz and f.created_at < (p_to + 1)::timestamptz,
    f.sg = 'sold' and f.sold_at >= p_from::timestamptz and f.sold_at < (p_to + 1)::timestamptz,
    f.sg = 'removed' and f.rem_at >= p_from::timestamptz and f.rem_at < (p_to + 1)::timestamptz,
    f.nviews, f.nsaves, f.nenq,
    case when f.nviews > 0 then round(f.nenq * 100.0 / f.nviews, 1) end,
    f.fenq,
    case when f.fenq is not null and f.flive is not null and f.fenq >= f.flive then round(extract(epoch from f.fenq - f.flive) / 86400, 1) end,
    case when f.flive is not null and coalesce(case when f.sg = 'sold' then f.sold_at end, f.rem_at) is not null
      then round(extract(epoch from coalesce(case when f.sg = 'sold' then f.sold_at end, f.rem_at) - f.flive) / 86400, 1) end,
    f.simn, round(f.simmed), case when f.simmed > 0 then round((f.price / f.simmed - 1) * 100, 1) end,
    nullif(concat_ws('; ',
      case when f.simmed > 0 and f.price >= f.simmed * 1.10 then 'Priced ' || round((f.price / f.simmed - 1) * 100) || '% above similar cars' end,
      case when f.simmed > 0 and f.price <= f.simmed * 0.90 then 'Priced ' || round((1 - f.price / f.simmed) * 100) || '% below similar cars' end,
      case when coalesce(cardinality(f.photos), 0) < 6 then coalesce(cardinality(f.photos), 0) || ' photos' end,
      case when coalesce(length(f.description), 0) < 150 then 'Short description (' || coalesce(length(f.description), 0) || ' characters)' end), '')
  from f cross join lateral (select (coalesce(
      case when f.sg = 'sold' then f.sold_at::date when f.sg = 'removed' then f.rem_at::date end, current_date)
      - coalesce(f.flive, f.created_at)::date)::int age) x
$$;
revoke execute on function public.rpt_listing_facts(date, date) from public, anon, authenticated;

-- the row type of rpt_listing_facts, so a report can hold its rows in a variable (no work tables)
do $t$ begin
  if not exists (select 1 from pg_type where typname = 'rpt_listing' and typnamespace = 'public'::regnamespace) then
    create type public.rpt_listing as (
      id uuid, ref text, car text, make text, model text, year int, price bigint, currency text, status text, status_group text,
      seller_id uuid, seller text, saaz_owned boolean, photos int, desc_len int, created_at timestamptz, updated_at timestamptz,
      first_live_at timestamptz, sold_at timestamptz, removed_at timestamptz, age_days int, age_band text, price_band text,
      stale boolean, added_in_period boolean, sold_in_period boolean, removed_in_period boolean,
      views int, saves int, enquiries int, enquiry_rate numeric, first_enquiry_at timestamptz,
      days_to_first_enquiry numeric, days_to_close numeric, similar_count int, similar_median numeric, price_vs_similar numeric, reason text);
  end if;
end $t$;

-- ---------- the report function: key numbers, groups, trend, rows. Admin only. ----------
-- p_filters: make, price_band, status_group, seller_type (private|saaz), age_band, flag, q (ref or car text)
--   flag: added | sold | removed | stale | no_photos | live_now | pending_now | draft_now | expired_now | has_views | has_enquiries
-- p_group: status_group | make | price_band | age_band (Inventory) to return grouped counts instead of rows
-- p_export: true returns up to 10,000 rows and records who exported what
create or replace function public.admin_report(p_report text, p_from date, p_to date, p_compare boolean default false,
  p_filters jsonb default '{}'::jsonb, p_group text default null, p_sort text default null, p_desc boolean default true,
  p_page int default 1, p_size int default 25, p_export boolean default false)
returns jsonb language plpgsql volatile security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
declare
  me uuid := public.require_admin();
  f jsonb := coalesce(p_filters, '{}'::jsonb);
  rfa public.rpt_listing[]; rva public.rpt_listing[];
  len int; pf date; pt date; res jsonb; kpis jsonb; trend jsonb := null; groups jsonb := null; rows jsonb; total int;
  cols text[]; sortcol text; lim int; off int; started timestamptz := clock_timestamp();
begin
  if p_report not in ('inventory','funnel') then raise exception 'Unknown report.'; end if;
  if p_from is null or p_to is null or p_to < p_from then raise exception 'Choose a date range.'; end if;
  if p_to - p_from > 731 then raise exception 'Choose a range of two years or less.'; end if;
  len := p_to - p_from + 1; pt := p_from - 1; pf := pt - len + 1;
  lim := case when p_export then 10000 else least(greatest(coalesce(p_size, 25), 1), 200) end;
  off := case when p_export then 0 else (greatest(coalesce(p_page, 1), 1) - 1) * lim end;

  -- the rows this report covers, held in a variable: rfa (filters applied), then rva (drill-down applied)
  select coalesce(array_agg(row(r.*)::public.rpt_listing), '{}') into rfa from public.rpt_listing_facts(p_from, p_to) r
  where (f->>'make' is null or r.make = f->>'make')
    and (f->>'price_band' is null or r.price_band = f->>'price_band')
    and (f->>'status_group' is null or r.status_group = f->>'status_group')
    and (f->>'age_band' is null or r.age_band = f->>'age_band')
    and (f->>'seller_type' is null or (f->>'seller_type' = 'saaz') = r.saaz_owned)
    and (p_report <> 'funnel' or r.first_live_at is not null)  -- the funnel is about listings that have been live
    and (f->>'q' is null or r.ref ilike '%' || (f->>'q') || '%' or r.car ilike '%' || (f->>'q') || '%' or coalesce(r.seller,'') ilike '%' || (f->>'q') || '%');

  if p_report = 'inventory' then
    kpis := jsonb_build_array(
      jsonb_build_object('key','live_now','value',(select count(*) from unnest(rfa) _rf where status_group = 'live'),'flag','live_now'),
      jsonb_build_object('key','pending_now','value',(select count(*) from unnest(rfa) _rf where status_group = 'pending'),'flag','pending_now'),
      jsonb_build_object('key','added','value',(select count(*) from unnest(rfa) _rf where added_in_period),'flag','added'),
      jsonb_build_object('key','sold','value',(select count(*) from unnest(rfa) _rf where sold_in_period),'flag','sold'),
      jsonb_build_object('key','removed','value',(select count(*) from unnest(rfa) _rf where removed_in_period),'flag','removed'),
      jsonb_build_object('key','stale','value',(select count(*) from unnest(rfa) _rf where stale),'flag','stale'),
      jsonb_build_object('key','no_photos','value',(select count(*) from unnest(rfa) _rf where photos = 0 and status_group not in ('removed','sold')),'flag','no_photos'));
    if p_compare then
      -- the period-based numbers again for the previous period of the same length (snapshot numbers have no previous value)
      kpis := (select jsonb_agg(case when k->>'key' in ('added','sold','removed') then k || jsonb_build_object('prev',
          (select count(*) from public.rpt_listing_facts(pf, pt) r
            where (f->>'make' is null or r.make = f->>'make') and (f->>'price_band' is null or r.price_band = f->>'price_band')
              and (f->>'status_group' is null or r.status_group = f->>'status_group') and (f->>'age_band' is null or r.age_band = f->>'age_band')
              and (f->>'seller_type' is null or (f->>'seller_type' = 'saaz') = r.saaz_owned)
              and case k->>'key' when 'added' then r.added_in_period when 'sold' then r.sold_in_period else r.removed_in_period end)) else k end)
        from jsonb_array_elements(kpis) k);
    end if;
  else
    kpis := jsonb_build_array(
      jsonb_build_object('key','views','value',(select coalesce(sum(views),0) from unnest(rfa) _rf),'flag','has_views'),
      jsonb_build_object('key','saves','value',(select coalesce(sum(saves),0) from unnest(rfa) _rf),'flag','has_saves'),
      jsonb_build_object('key','enquiries','value',(select coalesce(sum(enquiries),0) from unnest(rfa) _rf),'flag','has_enquiries'),
      jsonb_build_object('key','enquiry_rate','value',(select case when sum(views) > 0 then round(sum(enquiries) * 100.0 / sum(views), 1) end from unnest(rfa) _rf),'flag','has_views'),
      jsonb_build_object('key','median_days_to_first_enquiry','value',(select round((percentile_cont(0.5) within group (order by days_to_first_enquiry))::numeric, 1) from unnest(rfa) _rf where first_enquiry_at::date between p_from and p_to),'flag','first_enquiry'),
      jsonb_build_object('key','median_days_to_sold','value',(select round((percentile_cont(0.5) within group (order by days_to_close))::numeric, 1) from unnest(rfa) _rf where sold_in_period),'flag','sold'));
    if p_compare then
      kpis := (select jsonb_agg(k || jsonb_build_object('prev', (
          select case k->>'key' when 'views' then coalesce(sum(views),0) when 'saves' then coalesce(sum(saves),0) when 'enquiries' then coalesce(sum(enquiries),0)
            when 'enquiry_rate' then case when sum(views) > 0 then round(sum(enquiries) * 100.0 / sum(views), 1) end
            when 'median_days_to_first_enquiry' then round((percentile_cont(0.5) within group (order by days_to_first_enquiry) filter (where first_enquiry_at::date between pf and pt))::numeric, 1)
            else round((percentile_cont(0.5) within group (order by days_to_close) filter (where sold_in_period))::numeric, 1) end
          from public.rpt_listing_facts(pf, pt) r
          where r.first_live_at is not null and (f->>'make' is null or r.make = f->>'make') and (f->>'price_band' is null or r.price_band = f->>'price_band')
            and (f->>'status_group' is null or r.status_group = f->>'status_group') and (f->>'age_band' is null or r.age_band = f->>'age_band')
            and (f->>'seller_type' is null or (f->>'seller_type' = 'saaz') = r.saaz_owned))))
        from jsonb_array_elements(kpis) k);
    end if;
    -- trend: views and enquiries per day, this period and (if asked) the previous one, aligned by day number
    trend := (select jsonb_agg(jsonb_build_object('day', d::date, 'views', coalesce(v.n, 0), 'enquiries', coalesce(e.n, 0))
                || case when p_compare then jsonb_build_object('prev_day', (d - make_interval(days => len))::date,
                     'prev_views', coalesce(pv.n, 0), 'prev_enquiries', coalesce(pe.n, 0)) else '{}'::jsonb end order by d)
      from generate_series(p_from::timestamp, p_to::timestamp, interval '1 day') d
      left join (select x.day, count(*) n from public.listing_views x join unnest(rfa) _rf on _rf.id = x.listing_id where x.day between p_from and p_to group by x.day) v on v.day = d::date
      left join (select x.created_at::date dd, count(*) n from public.deals x join unnest(rfa) _rf on _rf.id = x.listing_id where x.created_at::date between p_from and p_to group by 1) e on e.dd = d::date
      left join (select x.day, count(*) n from public.listing_views x join unnest(rfa) _rf on _rf.id = x.listing_id where p_compare and x.day between pf and pt group by x.day) pv on pv.day = (d - make_interval(days => len))::date
      left join (select x.created_at::date dd, count(*) n from public.deals x join unnest(rfa) _rf on _rf.id = x.listing_id where p_compare and x.created_at::date between pf and pt group by 1) pe on pe.dd = (d - make_interval(days => len))::date);
  end if;

  -- drill-down: the flag behind a key number
  select coalesce(array_agg(_rf), '{}') into rva from unnest(rfa) _rf where case coalesce(f->>'flag','')
    when '' then true
    when 'live_now' then status_group = 'live' when 'pending_now' then status_group = 'pending'
    when 'draft_now' then status_group = 'draft' when 'expired_now' then status_group = 'expired'
    when 'added' then added_in_period when 'sold' then sold_in_period when 'removed' then removed_in_period
    when 'stale' then stale when 'no_photos' then photos = 0 and status_group not in ('removed','sold')
    when 'has_views' then views > 0 when 'has_saves' then saves > 0 when 'has_enquiries' then enquiries > 0
    when 'first_enquiry' then first_enquiry_at::date between p_from and p_to
    else false end;

  if p_group is not null and p_report = 'inventory' then
    if p_group not in ('status_group','make','price_band','age_band') then raise exception 'Unknown grouping.'; end if;
    execute format('select coalesce(jsonb_agg(jsonb_build_object(''value'', g, ''count'', n) order by n desc, g), ''[]''::jsonb) from (select %I g, count(*) n from unnest($1) _rv group by 1) s', p_group) into groups using rva;
  end if;

  cols := case when p_report = 'inventory'
    then array['ref','car','status_group','status','price','price_band','photos','age_days','updated_at','seller']
    else array['ref','car','price','price_vs_similar','similar_median','photos','desc_len','views','saves','enquiries','enquiry_rate','days_to_first_enquiry','days_to_close','reason'] end;
  sortcol := coalesce(nullif(p_sort, ''), case when p_report = 'inventory' then 'updated_at' else 'views' end);
  if not (sortcol = any(cols || array['created_at','age_days'])) then raise exception 'Unknown sort column.'; end if;
  total := cardinality(rva);
  execute format('select coalesce(jsonb_agg(to_jsonb(r) order by rn), ''[]''::jsonb) from (select _rv.*, row_number() over (order by %I %s nulls last, ref) rn from unnest($1) _rv order by %I %s nulls last, ref limit %s offset %s) r',
    sortcol, case when p_desc then 'desc' else 'asc' end, sortcol, case when p_desc then 'desc' else 'asc' end, lim, off) into rows using rva;

  if p_export then
    perform public.audit('admin', 'report', p_report, 'report exported',
      jsonb_build_object('from', p_from, 'to', p_to, 'filters', f, 'rows', jsonb_array_length(rows)));
  end if;
  return jsonb_build_object('report', p_report, 'from', p_from, 'to', p_to, 'prev_from', pf, 'prev_to', pt, 'compare', p_compare,
    'timezone', 'East Africa Time (UTC+3)', 'generated_at', now(), 'ms', round(extract(epoch from clock_timestamp() - started) * 1000),
    'filters', f, 'kpis', kpis, 'trend', trend, 'groups', groups, 'columns', to_jsonb(cols), 'sort', sortcol, 'desc', p_desc,
    'total', total, 'page', case when p_export then 1 else greatest(coalesce(p_page, 1), 1) end, 'size', lim, 'rows', rows);
end $$;
revoke execute on function public.admin_report(text, date, date, boolean, jsonb, text, text, boolean, int, int, boolean) from public, anon;
grant execute on function public.admin_report(text, date, date, boolean, jsonb, text, text, boolean, int, int, boolean) to authenticated;

-- Filter options for the control bar (makes on file). Admin only.
create or replace function public.admin_report_options() returns jsonb language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_admin();
  return jsonb_build_object('makes', (select coalesce(jsonb_agg(distinct make order by make), '[]'::jsonb) from public.listings),
    'price_bands', '["Under 20m","20m to 40m","40m to 70m","70m to 100m","Over 100m"]'::jsonb,
    'status_groups', '["draft","pending","live","sold","expired","removed"]'::jsonb,
    'age_bands', '["0 to 7 days","8 to 30 days","31 to 60 days","61 to 90 days","Over 90 days"]'::jsonb,
    'glossary', public.report_glossary(), 'today', (now() at time zone 'Africa/Kampala')::date);
end $$;
revoke execute on function public.admin_report_options() from public, anon;
grant execute on function public.admin_report_options() to authenticated;
