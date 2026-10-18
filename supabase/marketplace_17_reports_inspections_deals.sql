-- Part 17: Admin reports, slice 1b: Inspections and garages, Deals and sales.
-- Reads only. No table changes, no new events: reviews, conversations (the garage line), deals, deal_events and audit_log already hold it all.
-- The Deals report learns how far below asking each kind of car agrees: from every agreed deal so far, by model, make and price band.
-- Same rules as part 16: every formula here once, East Africa Time, admin only, exports recorded.

create index if not exists reviews_requested on public.reviews (requested_at);
create index if not exists reviews_issued on public.reviews (issued_at);
create index if not exists conversations_opened on public.conversations (opened_at);
create index if not exists deal_events_kind on public.deal_events (kind, deal_id, created_at);

-- ---------- definitions (added to the glossary) ----------
create or replace function public.report_glossary_2() returns jsonb language sql immutable as $$
  select jsonb_build_object(
    'doc_no',            jsonb_build_object('label','Inspection ID','def','The inspection''s Saaz ID (SZR-…).'),
    'garage',            jsonb_build_object('label','Garage','def','The certified garage doing the inspection.'),
    'scope',             jsonb_build_object('label','Scope','def','General (the full inspection) or a single area: engine, body, electrics, brakes.'),
    'insp_status',       jsonb_build_object('label','Inspection status','def','Requested (waiting for a garage to start), In progress, Issued, Superseded, Void, Cancelled.'),
    'requested_at',      jsonb_build_object('label','Requested','def','When the inspection was requested (the seller sent the car, or added a scope).'),
    'issued_at',         jsonb_build_object('label','Issued','def','When the garage issued the report.'),
    'days_to_inspect',   jsonb_build_object('label','Days to inspect','def','Days from requested to issued.'),
    'waiting_days',      jsonb_build_object('label','Waiting','def','For open inspections: days since requested.'),
    'verdict',           jsonb_build_object('label','Result','def','Pass, Conditional or Fail on the issued report.'),
    'score',             jsonb_build_object('label','Score','def','The report''s score out of 100.'),
    'objected',          jsonb_build_object('label','Saaz objected','def','Saaz''s latest view of the report is an objection.'),
    'insp_requested',    jsonb_build_object('label','Requested','def','Inspections requested in the period.'),
    'insp_issued',       jsonb_build_object('label','Issued','def','Inspections issued in the period.'),
    'median_days_to_inspect', jsonb_build_object('label','Median days to inspect','def','Median of days from requested to issued, over inspections issued in the period.'),
    'insp_open',         jsonb_build_object('label','Open now','def','Inspections requested or in progress right now.'),
    'insp_waiting_7d',   jsonb_build_object('label','Waiting over 7 days','def','Open inspections requested more than 7 days ago.'),
    'line_offers',       jsonb_build_object('label','Offered to garages','def','Times a car was put in play with a garage on the garage line in the period.'),
    'timeouts',          jsonb_build_object('label','Time-outs','def','Garage line turns in the period that ended because the garage did not act before its deadline.'),
    'timeout_rate',      jsonb_build_object('label','Time-out rate','def','Time-outs as a percent of turns that ended in the period.'),
    'pass_rate',         jsonb_build_object('label','Pass rate','def','Issued reports in the period with a Pass, as a percent of issued reports.'),
    'pass',              jsonb_build_object('label','Pass','def','Issued reports with a Pass.'),
    'conditional',       jsonb_build_object('label','Conditional','def','Issued reports with a Conditional result.'),
    'fail',              jsonb_build_object('label','Fail','def','Issued reports with a Fail.'),
    'avg_score',         jsonb_build_object('label','Average score','def','Average score of reports issued in the period.'),
    'opened_at',         jsonb_build_object('label','Put in play','def','When the car was offered to this garage on the garage line.'),
    'line_status',       jsonb_build_object('label','Line status','def','In play, agreed (booked), passed, declined, timed out, released or closed.'),
    'hours_to_contact',  jsonb_build_object('label','Hours to first contact','def','Hours from the car being put in play to the garage''s first message to the seller.'),
    'round',             jsonb_build_object('label','Round','def','Which turn of the garage line this was for the car.')
  ) || jsonb_build_object(  -- two objects: a function call takes at most 100 arguments
    'offers',            jsonb_build_object('label','Offers','def','Offers made by buyers in the period (same as Enquiries).'),
    'agreed',            jsonb_build_object('label','Agreed','def','Deals that reached agreement in the period (date of agreement).'),
    'completed',         jsonb_build_object('label','Completed','def','Deals marked completed (handed over) in the period.'),
    'agree_rate',        jsonb_build_object('label','Offer to agreement','def','Of the offers made in the period, the percent that have reached agreement so far.'),
    'median_days_to_agree', jsonb_build_object('label','Median days to agree','def','Median of days from the offer to agreement, over deals agreed in the period.'),
    'median_gap',        jsonb_build_object('label','Median gap','def','Median of how far below the asking price deals agreed, over deals agreed in the period.'),
    'lost',              jsonb_build_object('label','Ended without a deal','def','Offers that ended in the period without agreement: rejected, auto-rejected, withdrawn, cancelled or closed.'),
    'buyer',             jsonb_build_object('label','Buyer','def','The buyer''s name.'),
    'offer_at',          jsonb_build_object('label','Offer made','def','When the buyer made the first offer.'),
    'first_offer',       jsonb_build_object('label','First offer','def','The buyer''s first offer.'),
    'asking',            jsonb_build_object('label','Asking at agreement','def','The car''s asking price at the moment of agreement (from the price history).'),
    'agreed_amount',     jsonb_build_object('label','Agreed price','def','The price both sides agreed.'),
    'gap_pct',           jsonb_build_object('label','Gap','def','How far below the asking price the deal agreed, in percent of the asking price. Negative means above asking.'),
    'days_to_agree',     jsonb_build_object('label','Days to agree','def','Days from the first offer to agreement.'),
    'deal_status',       jsonb_build_object('label','Deal status','def','Negotiating, agreed, on hold, completed, or how it ended.'),
    'typical_gap',       jsonb_build_object('label','Typical gap','def','What Saaz has learned: the median gap of agreed deals for the most specific group with at least 3 agreed deals (model, then make, then price band, then all cars).'),
    'gap_vs_typical',    jsonb_build_object('label','Gap vs typical','def','This deal''s gap minus the typical gap for its group, in percentage points. Positive means the buyer got more off than usual.'),
    'based_on',          jsonb_build_object('label','Learned from','def','The group the typical gap comes from, and how many agreed deals it is based on.'),
    'expected_price',    jsonb_build_object('label','Expected agreed price','def','The asking price less the typical gap for its group: what this car is likely to agree at.'),
    'group_n',           jsonb_build_object('label','Agreed deals','def','Agreed deals in this group so far (all time up to the end of the period).'),
    'gap_p25',           jsonb_build_object('label','Gap, low quarter','def','A quarter of deals in this group agreed with a gap below this.'),
    'gap_p75',           jsonb_build_object('label','Gap, high quarter','def','A quarter of deals in this group agreed with a gap above this.'),
    'learned',           jsonb_build_object('label','Used for pricing','def','Yes when the group has at least 3 agreed deals, so its gap is used for its cars. With fewer, its cars use the next wider group (make, then price band, then all cars).'),
    'model',             jsonb_build_object('label','Model','def','Make and model.')
  ) $$;

-- ---------- inspections: one row each ----------
do $t$ begin
  if not exists (select 1 from pg_type where typname = 'rpt_inspection' and typnamespace = 'public'::regnamespace) then
    create type public.rpt_inspection as (id uuid, doc_no text, listing_id uuid, ref text, car text, make text, price_band text, garage_id uuid, garage text,
      scope text, insp_status text, requested_at timestamptz, started_at timestamptz, issued_at timestamptz, cancelled_at timestamptz,
      verdict text, score int, objected boolean, days_to_inspect numeric, waiting_days numeric, open_now boolean,
      requested_in_period boolean, issued_in_period boolean, cancelled_in_period boolean);
  end if;
  if not exists (select 1 from pg_type where typname = 'rpt_line' and typnamespace = 'public'::regnamespace) then
    create type public.rpt_line as (id uuid, listing_id uuid, ref text, car text, make text, price_band text, garage_id uuid, garage text,
      line_status text, round int, opened_at timestamptz, closed_at timestamptz, hours_to_contact numeric,
      opened_in_period boolean, ended_in_period boolean, timed_out_in_period boolean);
  end if;
  if not exists (select 1 from pg_type where typname = 'rpt_deal' and typnamespace = 'public'::regnamespace) then
    create type public.rpt_deal as (id uuid, listing_id uuid, ref text, car text, make text, model text, price_band text, buyer text,
      deal_status text, offer_at timestamptz, first_offer bigint, agreed_at timestamptz, agreed_amount bigint, asking bigint, gap_pct numeric,
      days_to_agree numeric, completed_at timestamptz, ended_at timestamptz,
      offered_in_period boolean, agreed_in_period boolean, completed_in_period boolean, lost_in_period boolean,
      typical_gap numeric, gap_vs_typical numeric, based_on text);
  end if;
end $t$;

create or replace function public.rpt_inspection_facts(p_from date, p_to date) returns setof public.rpt_inspection
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  select r.id, r.doc_no, l.id, l.ref, l.year || ' ' || l.make || ' ' || l.model, l.make, public.rpt_price_band(l.price), r.garage_id, coalesce(g.name, r.garage_name),
    r.scope, r.status, coalesce(r.requested_at, r.created_at), r.started_at, r.issued_at, r.cancelled_at,
    case when r.status in ('issued','superseded') then r.verdict end, case when r.status in ('issued','superseded') then r.score end,
    coalesce(op.stance = 'object', false),
    case when r.issued_at is not null then round(extract(epoch from r.issued_at - coalesce(r.requested_at, r.created_at)) / 86400, 1) end,
    case when r.status in ('requested','draft') then round(extract(epoch from now() - coalesce(r.requested_at, r.created_at)) / 86400, 1) end,
    r.status in ('requested','draft'),
    coalesce(r.requested_at, r.created_at) >= p_from::timestamptz and coalesce(r.requested_at, r.created_at) < (p_to + 1)::timestamptz,
    r.issued_at >= p_from::timestamptz and r.issued_at < (p_to + 1)::timestamptz,
    r.status = 'cancelled' and r.cancelled_at >= p_from::timestamptz and r.cancelled_at < (p_to + 1)::timestamptz
  from public.reviews r join public.listings l on l.id = r.listing_id left join public.garages g on g.id = r.garage_id
  left join lateral (select o.stance from public.review_opinions o where o.review_id = r.id and o.stance in ('support','object') order by o.created_at desc limit 1) op on true
$$;
revoke execute on function public.rpt_inspection_facts(date, date) from public, anon, authenticated;

create or replace function public.rpt_line_facts(p_from date, p_to date) returns setof public.rpt_line
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  select c.id, l.id, l.ref, l.year || ' ' || l.make || ' ' || l.model, l.make, public.rpt_price_band(l.price), c.garage_id, g.name,
    c.status, c.round, c.opened_at, c.closed_at,
    case when c.garage_first_message_at is not null then round(extract(epoch from c.garage_first_message_at - c.opened_at) / 3600, 1) end,
    c.opened_at >= p_from::timestamptz and c.opened_at < (p_to + 1)::timestamptz,
    c.closed_at >= p_from::timestamptz and c.closed_at < (p_to + 1)::timestamptz and c.status <> 'in_play',
    c.status = 'timed_out' and c.closed_at >= p_from::timestamptz and c.closed_at < (p_to + 1)::timestamptz
  from public.conversations c join public.listings l on l.id = c.listing_id left join public.garages g on g.id = c.garage_id
$$;
revoke execute on function public.rpt_line_facts(date, date) from public, anon, authenticated;

-- ---------- what agreement usually looks like: the gap, by group, from every agreed deal up to p_to ----------
-- level: 1 model (make and model), 2 make, 3 price band, 4 all cars
create or replace function public.rpt_deal_base(p_to date)
returns table (id uuid, listing_id uuid, ref text, car text, make text, model text, price_band text, buyer text, deal_status text,
  offer_at timestamptz, first_offer bigint, agreed_at timestamptz, agreed_amount bigint, asking bigint, gap_pct numeric, days_to_agree numeric,
  completed_at timestamptz, ended_at timestamptz)
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  with ag as (select e.deal_id, min(e.created_at) at from public.deal_events e where e.kind = 'agreed' group by 1),
  agv as (select distinct on (e.deal_id) e.deal_id, e.amount from public.deal_events e where e.kind = 'agreed' order by e.deal_id, e.created_at),
  fo as (select distinct on (e.deal_id) e.deal_id, e.amount from public.deal_events e where e.kind = 'offer' order by e.deal_id, e.created_at),
  co as (select e.deal_id, min(e.created_at) at from public.deal_events e where e.kind = 'completed' group by 1),
  en as (select e.deal_id, max(e.created_at) at from public.deal_events e where e.kind in ('reject','auto_reject','withdraw','cancelled','closed') group by 1),
  d as (
    select d.*, l.ref, l.year || ' ' || l.make || ' ' || l.model car, l.make, l.model, l.price lprice, l.id lid, p.name buyer_name,
      ag.at agreed_at, coalesce(agv.amount, case when ag.at is not null then d.amount end) agreed_amount, fo.amount first_offer, co.at completed_at,
      case when d.status in ('rejected','auto_rejected','withdrawn','cancelled','closed') then coalesce(en.at, d.updated_at) end ended_at
    from public.deals d join public.listings l on l.id = d.listing_id left join public.profiles p on p.id = d.buyer_id
    left join ag on ag.deal_id = d.id left join agv on agv.deal_id = d.id left join fo on fo.deal_id = d.id
    left join co on co.deal_id = d.id left join en on en.deal_id = d.id
    where d.created_at < (p_to + 1)::timestamptz
  ), d2 as (
    select d.*,
      -- the asking price when they agreed: the last price change before agreement, else the price before the first change after it, else today's price
      coalesce((select (a.detail->>'after')::bigint from public.audit_log a where a.entity = 'listing' and a.action = 'price changed' and a.entity_id = d.lid::text
                  and a.at <= coalesce(d.agreed_at, now()) order by a.at desc limit 1),
               (select (a.detail->>'before')::bigint from public.audit_log a where a.entity = 'listing' and a.action = 'price changed' and a.entity_id = d.lid::text
                  and a.at > coalesce(d.agreed_at, now()) order by a.at asc limit 1),
               d.lprice) ask
    from d
  )
  select d2.id, d2.lid, d2.ref, d2.car, d2.make, d2.model, public.rpt_price_band(d2.ask), d2.buyer_name, d2.status,
    d2.created_at, coalesce(d2.first_offer, d2.amount), d2.agreed_at, d2.agreed_amount, d2.ask,
    case when d2.agreed_amount is not null and d2.ask > 0 then round((d2.ask - d2.agreed_amount) * 100.0 / d2.ask, 1) end,
    case when d2.agreed_at is not null then round(extract(epoch from d2.agreed_at - d2.created_at) / 86400, 1) end,
    d2.completed_at, d2.ended_at
  from d2
$$;
revoke execute on function public.rpt_deal_base(date) from public, anon, authenticated;

create or replace function public.rpt_gap_norms(p_to date)
returns table (level int, gkey text, label text, n int, median numeric, p25 numeric, p75 numeric)
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  with a as (select * from public.rpt_deal_base(p_to) b where b.gap_pct is not null and b.agreed_at < (p_to + 1)::timestamptz),
  g as (
    select 1 lv, make || '|' || model k, make || ' ' || model lab, gap_pct from a
    union all select 2, make, make, gap_pct from a
    union all select 3, price_band, price_band, gap_pct from a
    union all select 4, 'all', 'All cars', gap_pct from a)
  select lv, k, lab, count(*)::int, round((percentile_cont(0.5) within group (order by gap_pct))::numeric, 1),
    round((percentile_cont(0.25) within group (order by gap_pct))::numeric, 1), round((percentile_cont(0.75) within group (order by gap_pct))::numeric, 1)
  from g group by lv, k, lab
$$;
revoke execute on function public.rpt_gap_norms(date) from public, anon, authenticated;

-- One row per deal, with what Saaz has learned for its group: the most specific group with at least 3 agreed deals
-- (make and model, then make, then price band, then all cars), from every deal agreed up to the end of the period.
create or replace function public.rpt_deal_facts(p_from date, p_to date) returns setof public.rpt_deal
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  with b as (select * from public.rpt_deal_base(p_to)),
  a as (select * from b where b.gap_pct is not null and b.agreed_at < (p_to + 1)::timestamptz),
  n1 as (select make, model, count(*) n, round((percentile_cont(0.5) within group (order by gap_pct))::numeric, 1) med from a group by 1, 2),
  n2 as (select make, count(*) n, round((percentile_cont(0.5) within group (order by gap_pct))::numeric, 1) med from a group by 1),
  n3 as (select price_band, count(*) n, round((percentile_cont(0.5) within group (order by gap_pct))::numeric, 1) med from a group by 1),
  n4 as (select count(*) n, round((percentile_cont(0.5) within group (order by gap_pct))::numeric, 1) med from a),
  t as (
    select b.*, case when n1.n >= 3 then n1.med when n2.n >= 3 then n2.med when n3.n >= 3 then n3.med when n4.n >= 3 then n4.med end tg,
      case when n1.n >= 3 then b.make || ' ' || b.model || ', ' || n1.n when n2.n >= 3 then b.make || ', ' || n2.n
           when n3.n >= 3 then b.price_band || ', ' || n3.n when n4.n >= 3 then 'All cars, ' || n4.n end || ' deals' bo
    from b left join n1 on n1.make = b.make and n1.model = b.model left join n2 on n2.make = b.make
      left join n3 on n3.price_band = b.price_band cross join n4)
  select t.id, t.listing_id, t.ref, t.car, t.make, t.model, t.price_band, t.buyer, t.deal_status, t.offer_at, t.first_offer, t.agreed_at, t.agreed_amount, t.asking,
    t.gap_pct, t.days_to_agree, t.completed_at, t.ended_at,
    t.offer_at >= p_from::timestamptz and t.offer_at < (p_to + 1)::timestamptz,
    t.agreed_at >= p_from::timestamptz and t.agreed_at < (p_to + 1)::timestamptz,
    t.completed_at >= p_from::timestamptz and t.completed_at < (p_to + 1)::timestamptz,
    t.agreed_at is null and t.ended_at >= p_from::timestamptz and t.ended_at < (p_to + 1)::timestamptz,
    t.tg, case when t.gap_pct is not null and t.tg is not null then round(t.gap_pct - t.tg, 1) end, t.bo
  from t
$$;
revoke execute on function public.rpt_deal_facts(date, date) from public, anon, authenticated;

-- The same learning applied to cars on sale: what each live car is likely to agree at
create or replace function public.rpt_expected_prices(p_to date)
returns table (listing_id uuid, ref text, car text, make text, model text, price_band text, price bigint, currency text, typical_gap numeric, expected_price bigint, based_on text)
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
  with n as (select * from public.rpt_gap_norms(p_to) where n >= 3)
  select l.id, l.ref, l.year || ' ' || l.make || ' ' || l.model, l.make, l.model, public.rpt_price_band(l.price), l.price, l.currency,
    coalesce(n1.median, n2.median, n3.median, n4.median),
    (round(l.price * (1 - coalesce(n1.median, n2.median, n3.median, n4.median) / 100) / 100000) * 100000)::bigint,
    coalesce(n1.label || ', ' || n1.n, n2.label || ', ' || n2.n, n3.label || ', ' || n3.n, n4.label || ', ' || n4.n) || ' deals'
  from public.listings l
  left join n n1 on n1.level = 1 and n1.gkey = l.make || '|' || l.model left join n n2 on n2.level = 2 and n2.gkey = l.make
  left join n n3 on n3.level = 3 and n3.gkey = public.rpt_price_band(l.price) left join n n4 on n4.level = 4
  where l.status in ('live','reserved')
$$;
revoke execute on function public.rpt_expected_prices(date) from public, anon, authenticated;

-- ---------- the dispatcher: one admin_report for every report ----------
-- The part 16 function becomes the Inventory and Funnel engine; admin_report now routes by report.
do $r$ begin
  if not exists (select 1 from pg_proc where proname = 'rpt_listings_report' and pronamespace = 'public'::regnamespace) then
    alter function public.admin_report(text, date, date, boolean, jsonb, text, text, boolean, int, int, boolean) rename to rpt_listings_report;
  end if;
end $r$;
revoke execute on function public.rpt_listings_report(text, date, date, boolean, jsonb, text, text, boolean, int, int, boolean) from public, anon, authenticated;

create or replace function public.admin_report(p_report text, p_from date, p_to date, p_compare boolean default false,
  p_filters jsonb default '{}'::jsonb, p_group text default null, p_sort text default null, p_desc boolean default true,
  p_page int default 1, p_size int default 25, p_export boolean default false)
returns jsonb language plpgsql volatile security definer set search_path = public set "TimeZone" to 'Africa/Kampala' set jit = off as $$
declare
  me uuid := public.require_admin();
  f jsonb := coalesce(p_filters, '{}'::jsonb); flag text := coalesce(p_filters->>'flag', '');
  len int; pf date; pt date; lim int; off int; started timestamptz := clock_timestamp();
  ia public.rpt_inspection[]; la public.rpt_line[]; da public.rpt_deal[]; ipa public.rpt_inspection[]; lpa public.rpt_line[]; dpa public.rpt_deal[];
  kpis jsonb; trend jsonb; groups jsonb := null; gcols jsonb := null; rows jsonb; total int; cols text[]; sortcol text; kind text; dir text;
begin
  if p_report in ('inventory','funnel') then
    return public.rpt_listings_report(p_report, p_from, p_to, p_compare, p_filters, p_group, p_sort, p_desc, p_page, p_size, p_export);
  end if;
  if p_report not in ('inspections','deals') then raise exception 'Unknown report.'; end if;
  if p_from is null or p_to is null or p_to < p_from then raise exception 'Choose a date range.'; end if;
  if p_to - p_from > 731 then raise exception 'Choose a range of two years or less.'; end if;
  len := p_to - p_from + 1; pt := p_from - 1; pf := pt - len + 1;
  lim := case when p_export then 10000 else least(greatest(coalesce(p_size, 25), 1), 200) end;
  off := case when p_export then 0 else (greatest(coalesce(p_page, 1), 1) - 1) * lim end;
  dir := case when p_desc then 'desc' else 'asc' end;

  if p_report = 'inspections' then
    select coalesce(array_agg(x), '{}') into ia from public.rpt_inspection_facts(p_from, p_to) x
      where (f->>'make' is null or x.make = f->>'make') and (f->>'price_band' is null or x.price_band = f->>'price_band')
        and (f->>'garage' is null or x.garage_id::text = f->>'garage') and (f->>'scope' is null or x.scope = f->>'scope')
        and (f->>'q' is null or x.ref ilike '%' || (f->>'q') || '%' or x.car ilike '%' || (f->>'q') || '%' or coalesce(x.doc_no,'') ilike '%' || (f->>'q') || '%' or coalesce(x.garage,'') ilike '%' || (f->>'q') || '%');
    select coalesce(array_agg(x), '{}') into la from public.rpt_line_facts(p_from, p_to) x
      where (f->>'make' is null or x.make = f->>'make') and (f->>'price_band' is null or x.price_band = f->>'price_band')
        and (f->>'garage' is null or x.garage_id::text = f->>'garage')
        and (f->>'q' is null or x.ref ilike '%' || (f->>'q') || '%' or x.car ilike '%' || (f->>'q') || '%' or coalesce(x.garage,'') ilike '%' || (f->>'q') || '%');
    kpis := jsonb_build_array(
      jsonb_build_object('key','insp_requested','value',(select count(*) from unnest(ia) i where requested_in_period),'flag','requested'),
      jsonb_build_object('key','insp_issued','value',(select count(*) from unnest(ia) i where issued_in_period),'flag','issued'),
      jsonb_build_object('key','median_days_to_inspect','value',(select round((percentile_cont(0.5) within group (order by days_to_inspect))::numeric, 1) from unnest(ia) i where issued_in_period),'flag','issued'),
      jsonb_build_object('key','insp_open','value',(select count(*) from unnest(ia) i where open_now),'flag','open_now'),
      jsonb_build_object('key','insp_waiting_7d','value',(select count(*) from unnest(ia) i where open_now and waiting_days > 7),'flag','waiting_7d'),
      jsonb_build_object('key','line_offers','value',(select count(*) from unnest(la) c where opened_in_period),'flag','line_offers'),
      jsonb_build_object('key','timeouts','value',(select count(*) from unnest(la) c where timed_out_in_period),'flag','timeouts'),
      jsonb_build_object('key','timeout_rate','value',(select case when count(*) filter (where ended_in_period) > 0 then round(count(*) filter (where timed_out_in_period) * 100.0 / count(*) filter (where ended_in_period), 1) end from unnest(la) c),'flag','line_ended'),
      jsonb_build_object('key','pass_rate','value',(select case when count(*) > 0 then round(count(*) filter (where verdict = 'pass') * 100.0 / count(*), 1) end from unnest(ia) i where issued_in_period),'flag','issued'));
    if p_compare then
      -- the previous period, worked out once with the same filters
      select coalesce(array_agg(x), '{}') into ipa from public.rpt_inspection_facts(pf, pt) x
        where (f->>'make' is null or x.make = f->>'make') and (f->>'price_band' is null or x.price_band = f->>'price_band')
          and (f->>'garage' is null or x.garage_id::text = f->>'garage') and (f->>'scope' is null or x.scope = f->>'scope');
      select coalesce(array_agg(x), '{}') into lpa from public.rpt_line_facts(pf, pt) x
        where (f->>'make' is null or x.make = f->>'make') and (f->>'price_band' is null or x.price_band = f->>'price_band') and (f->>'garage' is null or x.garage_id::text = f->>'garage');
      kpis := (select jsonb_agg(k || case when k->>'key' in ('insp_open','insp_waiting_7d') then '{}'::jsonb else jsonb_build_object('prev', case k->>'key'
            when 'insp_requested' then (select to_jsonb(count(*)) from unnest(ipa) i where i.requested_in_period)
            when 'insp_issued' then (select to_jsonb(count(*)) from unnest(ipa) i where i.issued_in_period)
            when 'median_days_to_inspect' then (select to_jsonb(round((percentile_cont(0.5) within group (order by i.days_to_inspect))::numeric, 1)) from unnest(ipa) i where i.issued_in_period)
            when 'pass_rate' then (select to_jsonb(case when count(*) > 0 then round(count(*) filter (where i.verdict = 'pass') * 100.0 / count(*), 1) end) from unnest(ipa) i where i.issued_in_period)
            when 'line_offers' then (select to_jsonb(count(*)) from unnest(lpa) c where c.opened_in_period)
            when 'timeouts' then (select to_jsonb(count(*)) from unnest(lpa) c where c.timed_out_in_period)
            else (select to_jsonb(case when count(*) filter (where c.ended_in_period) > 0 then round(count(*) filter (where c.timed_out_in_period) * 100.0 / count(*) filter (where c.ended_in_period), 1) end) from unnest(lpa) c) end) end)
        from jsonb_array_elements(kpis) k);
    end if;
    -- trend: requested and issued per day (counted once, then laid on the calendar)
    trend := (select jsonb_agg(jsonb_build_object('day', d::date, 'requested', coalesce(rq.n, 0), 'issued', coalesce(iss.n, 0))
        || case when p_compare then jsonb_build_object('prev_day', (d - make_interval(days => len))::date, 'prev_requested', coalesce(prq.n, 0), 'prev_issued', coalesce(piss.n, 0)) else '{}'::jsonb end order by d)
      from generate_series(p_from::timestamp, p_to::timestamp, interval '1 day') d
      left join (select i.requested_at::date dd, count(*) n from unnest(ia) i where i.requested_in_period group by 1) rq on rq.dd = d::date
      left join (select i.issued_at::date dd, count(*) n from unnest(ia) i where i.issued_in_period group by 1) iss on iss.dd = d::date
      left join (select i.requested_at::date dd, count(*) n from unnest(ipa) i where i.requested_in_period group by 1) prq on prq.dd = (d - make_interval(days => len))::date
      left join (select i.issued_at::date dd, count(*) n from unnest(ipa) i where i.issued_in_period group by 1) piss on piss.dd = (d - make_interval(days => len))::date);
    if p_group is not null then
      if p_group = 'garage' then
        gcols := '[{"key":"insp_requested","flag":"requested"},{"key":"insp_issued","flag":"issued"},{"key":"median_days_to_inspect","flag":"issued"},{"key":"insp_open","flag":"open_now"},
                   {"key":"line_offers","flag":"line_offers"},{"key":"timeouts","flag":"timeouts"},{"key":"timeout_rate","flag":"line_ended"},
                   {"key":"pass","flag":"pass"},{"key":"conditional","flag":"conditional"},{"key":"fail","flag":"fail"},{"key":"avg_score","flag":"issued"},{"key":"objected","flag":"objected"}]';
        groups := (select coalesce(jsonb_agg(jsonb_build_object('value', gg.garage_id::text, 'label', gg.garage,
            'insp_requested', coalesce(ii.requested, 0), 'insp_issued', coalesce(ii.issued, 0), 'median_days_to_inspect', ii.med, 'insp_open', coalesce(ii.open, 0),
            'line_offers', coalesce(cc.offers, 0), 'timeouts', coalesce(cc.timeouts, 0), 'timeout_rate', cc.rate,
            'pass', coalesce(ii.pass, 0), 'conditional', coalesce(ii.cond, 0), 'fail', coalesce(ii.fail, 0), 'avg_score', ii.avg, 'objected', coalesce(ii.obj, 0))
            order by coalesce(ii.issued, 0) desc, gg.garage), '[]')
          from (select distinct garage_id, garage from unnest(ia) where garage_id is not null union select distinct garage_id, garage from unnest(la) where garage_id is not null) gg
          left join (select i.garage_id, count(*) filter (where i.requested_in_period) requested, count(*) filter (where i.issued_in_period) issued,
              round((percentile_cont(0.5) within group (order by i.days_to_inspect) filter (where i.issued_in_period))::numeric, 1) med, count(*) filter (where i.open_now) open,
              count(*) filter (where i.issued_in_period and i.verdict = 'pass') pass, count(*) filter (where i.issued_in_period and i.verdict = 'conditional') cond,
              count(*) filter (where i.issued_in_period and i.verdict = 'fail') fail, round(avg(i.score) filter (where i.issued_in_period), 1) avg, count(*) filter (where i.objected) obj
            from unnest(ia) i group by 1) ii on ii.garage_id = gg.garage_id
          left join (select c.garage_id, count(*) filter (where c.opened_in_period) offers, count(*) filter (where c.timed_out_in_period) timeouts,
              case when count(*) filter (where c.ended_in_period) > 0 then round(count(*) filter (where c.timed_out_in_period) * 100.0 / count(*) filter (where c.ended_in_period), 1) end rate
            from unnest(la) c group by 1) cc on cc.garage_id = gg.garage_id);
      elsif p_group = 'scope' then
        gcols := '[{"key":"insp_requested","flag":"requested"},{"key":"insp_issued","flag":"issued"},{"key":"median_days_to_inspect","flag":"issued"},{"key":"insp_open","flag":"open_now"}]';
        groups := (select coalesce(jsonb_agg(row_to_json(g)::jsonb order by g.insp_requested desc), '[]') from (
          select i.scope value, initcap(i.scope) label, count(*) filter (where i.requested_in_period) insp_requested, count(*) filter (where i.issued_in_period) insp_issued,
            round((percentile_cont(0.5) within group (order by i.days_to_inspect) filter (where i.issued_in_period))::numeric, 1) median_days_to_inspect, count(*) filter (where i.open_now) insp_open
          from unnest(ia) i group by i.scope) g);
      else raise exception 'Unknown grouping.'; end if;
    end if;
    -- rows: inspections, or garage line turns for the line numbers
    if flag in ('line_offers','timeouts','line_ended') then
      kind := 'garage_line'; cols := array['ref','car','garage','line_status','round','opened_at','hours_to_contact'];
      sortcol := coalesce(nullif(p_sort, ''), 'opened_at');
      if not (sortcol = any(cols)) then raise exception 'Unknown sort column.'; end if;
      select count(*) into total from unnest(la) c where case flag when 'line_offers' then opened_in_period when 'timeouts' then timed_out_in_period else ended_in_period end;
      execute format('select coalesce(jsonb_agg(to_jsonb(r) - ''listing_id'' || jsonb_build_object(''listing_id'', r.listing_id) order by rn), ''[]'') from (select c.*, row_number() over (order by %I %s nulls last, ref) rn from unnest($1) c
        where case $2 when ''line_offers'' then opened_in_period when ''timeouts'' then timed_out_in_period else ended_in_period end order by %I %s nulls last, ref limit %s offset %s) r',
        sortcol, dir, sortcol, dir, lim, off) into rows using la, flag;
    else
      kind := 'inspections'; cols := array['doc_no','ref','car','garage','scope','insp_status','requested_at','issued_at','days_to_inspect','waiting_days','verdict','score','objected'];
      sortcol := coalesce(nullif(p_sort, ''), 'requested_at');
      if not (sortcol = any(cols)) then raise exception 'Unknown sort column.'; end if;
      select count(*) into total from unnest(ia) i where case flag when '' then true when 'requested' then requested_in_period when 'issued' then issued_in_period
        when 'open_now' then open_now when 'waiting_7d' then open_now and waiting_days > 7 when 'objected' then objected
        when 'pass' then issued_in_period and verdict = 'pass' when 'conditional' then issued_in_period and verdict = 'conditional' when 'fail' then issued_in_period and verdict = 'fail' else false end;
      execute format('select coalesce(jsonb_agg(to_jsonb(r) order by rn), ''[]'') from (select i.*, row_number() over (order by %I %s nulls last, doc_no) rn from unnest($1) i
        where case $2 when '''' then true when ''requested'' then requested_in_period when ''issued'' then issued_in_period
        when ''open_now'' then open_now when ''waiting_7d'' then open_now and waiting_days > 7 when ''objected'' then objected
        when ''pass'' then issued_in_period and verdict = ''pass'' when ''conditional'' then issued_in_period and verdict = ''conditional'' when ''fail'' then issued_in_period and verdict = ''fail'' else false end
        order by %I %s nulls last, doc_no limit %s offset %s) r', sortcol, dir, sortcol, dir, lim, off) into rows using ia, flag;
    end if;

  else  -- deals
    select coalesce(array_agg(x), '{}') into da from public.rpt_deal_facts(p_from, p_to) x
      where (f->>'make' is null or x.make = f->>'make') and (f->>'price_band' is null or x.price_band = f->>'price_band')
        and (f->>'model' is null or x.make || '|' || x.model = f->>'model')
        and (f->>'q' is null or x.ref ilike '%' || (f->>'q') || '%' or x.car ilike '%' || (f->>'q') || '%' or coalesce(x.buyer,'') ilike '%' || (f->>'q') || '%');
    kpis := jsonb_build_array(
      jsonb_build_object('key','offers','value',(select count(*) from unnest(da) d where offered_in_period),'flag','offered'),
      jsonb_build_object('key','agreed','value',(select count(*) from unnest(da) d where agreed_in_period),'flag','agreed'),
      jsonb_build_object('key','completed','value',(select count(*) from unnest(da) d where completed_in_period),'flag','completed'),
      jsonb_build_object('key','agree_rate','value',(select case when count(*) > 0 then round(count(*) filter (where agreed_at is not null) * 100.0 / count(*), 1) end from unnest(da) d where offered_in_period),'flag','offered'),
      jsonb_build_object('key','median_days_to_agree','value',(select round((percentile_cont(0.5) within group (order by days_to_agree))::numeric, 1) from unnest(da) d where agreed_in_period),'flag','agreed'),
      jsonb_build_object('key','median_gap','value',(select round((percentile_cont(0.5) within group (order by gap_pct))::numeric, 1) from unnest(da) d where agreed_in_period),'flag','agreed'),
      jsonb_build_object('key','lost','value',(select count(*) from unnest(da) d where lost_in_period),'flag','lost'));
    if p_compare then
      select coalesce(array_agg(x), '{}') into dpa from public.rpt_deal_facts(pf, pt) x
        where (f->>'make' is null or x.make = f->>'make') and (f->>'price_band' is null or x.price_band = f->>'price_band') and (f->>'model' is null or x.make || '|' || x.model = f->>'model');
      kpis := (select jsonb_agg(k || jsonb_build_object('prev', (
          select case k->>'key' when 'offers' then to_jsonb(count(*) filter (where d.offered_in_period)) when 'agreed' then to_jsonb(count(*) filter (where d.agreed_in_period))
            when 'completed' then to_jsonb(count(*) filter (where d.completed_in_period)) when 'lost' then to_jsonb(count(*) filter (where d.lost_in_period))
            when 'agree_rate' then to_jsonb(case when count(*) filter (where d.offered_in_period) > 0 then round(count(*) filter (where d.offered_in_period and d.agreed_at is not null) * 100.0 / count(*) filter (where d.offered_in_period), 1) end)
            when 'median_days_to_agree' then to_jsonb(round((percentile_cont(0.5) within group (order by d.days_to_agree) filter (where d.agreed_in_period))::numeric, 1))
            else to_jsonb(round((percentile_cont(0.5) within group (order by d.gap_pct) filter (where d.agreed_in_period))::numeric, 1)) end
          from unnest(dpa) d)))
        from jsonb_array_elements(kpis) k);
    end if;
    trend := (select jsonb_agg(jsonb_build_object('day', d::date, 'offers', coalesce(o.n, 0), 'agreed', coalesce(g.n, 0))
        || case when p_compare then jsonb_build_object('prev_day', (d - make_interval(days => len))::date, 'prev_offers', coalesce(po.n, 0), 'prev_agreed', coalesce(pg.n, 0)) else '{}'::jsonb end order by d)
      from generate_series(p_from::timestamp, p_to::timestamp, interval '1 day') d
      left join (select x.offer_at::date dd, count(*) n from unnest(da) x where x.offered_in_period group by 1) o on o.dd = d::date
      left join (select x.agreed_at::date dd, count(*) n from unnest(da) x where x.agreed_in_period group by 1) g on g.dd = d::date
      left join (select x.offer_at::date dd, count(*) n from unnest(dpa) x where x.offered_in_period group by 1) po on po.dd = (d - make_interval(days => len))::date
      left join (select x.agreed_at::date dd, count(*) n from unnest(dpa) x where x.agreed_in_period group by 1) pg on pg.dd = (d - make_interval(days => len))::date);
    if p_group is not null then
      if p_group not in ('model','make','price_band') then raise exception 'Unknown grouping.'; end if;
      -- what Saaz has learned for each group, from all agreed deals up to the end of the period (filters for make and band applied)
      gcols := '[{"key":"group_n","flag":"agreed_ever"},{"key":"median_gap"},{"key":"gap_p25"},{"key":"gap_p75"},{"key":"learned"},{"key":"agreed","flag":"agreed"},{"key":"offers","flag":"offered"}]';
      groups := (select coalesce(jsonb_agg(jsonb_build_object('value', n.gkey, 'label', n.label, 'group_n', n.n, 'median_gap', n.median, 'gap_p25', n.p25, 'gap_p75', n.p75, 'learned', n.n >= 3,
          'agreed', coalesce(c.agreed, 0), 'offers', coalesce(c.offers, 0)) order by n.n desc, n.label), '[]')
        from public.rpt_gap_norms(p_to) n
        join (select case p_group when 'model' then d.make || '|' || d.model when 'make' then d.make else d.price_band end k,
                count(*) filter (where d.agreed_in_period) agreed, count(*) filter (where d.offered_in_period) offers
              from unnest(da) d group by 1) c on c.k = n.gkey
        where n.level = case p_group when 'model' then 1 when 'make' then 2 else 3 end);
    end if;
    if flag = 'expected' then
      -- live cars: what they are likely to agree at, from the typical gap of their group
      kind := 'expected'; cols := array['ref','car','price','typical_gap','expected_price','based_on'];
      sortcol := coalesce(nullif(p_sort, ''), 'price');
      if not (sortcol = any(cols)) then raise exception 'Unknown sort column.'; end if;
      -- one pass: the rows of this page and the total
      execute format('select coalesce(jsonb_agg(to_jsonb(r) - ''n_all'' order by rn) filter (where rn > %s and rn <= %s), ''[]''), coalesce(max(n_all), 0) from (
          select x.*, coalesce(x.based_on, ''Fewer than 3 agreed deals yet'') based_on, row_number() over (order by %I %s nulls last, ref) rn, count(*) over () n_all
          from public.rpt_expected_prices($1) x
          where ($2->>''make'' is null or x.make = $2->>''make'') and ($2->>''price_band'' is null or x.price_band = $2->>''price_band'') and ($2->>''model'' is null or x.make || ''|'' || x.model = $2->>''model'')) r',
        off, off + lim, sortcol, dir) into rows, total using p_to, f;
    else
      kind := 'deals'; cols := array['ref','car','buyer','deal_status','offer_at','first_offer','asking','agreed_amount','gap_pct','typical_gap','gap_vs_typical','days_to_agree','based_on'];
      sortcol := coalesce(nullif(p_sort, ''), 'offer_at');
      if not (sortcol = any(cols)) then raise exception 'Unknown sort column.'; end if;
      select count(*) into total from unnest(da) d where case flag when '' then offered_in_period or agreed_in_period or completed_in_period or lost_in_period
        when 'offered' then offered_in_period when 'agreed' then agreed_in_period when 'completed' then completed_in_period when 'lost' then lost_in_period
        when 'agreed_ever' then gap_pct is not null else false end;
      execute format('select coalesce(jsonb_agg(to_jsonb(r) order by rn), ''[]'') from (select d.*, row_number() over (order by %I %s nulls last, ref) rn from unnest($1) d
        where case $2 when '''' then offered_in_period or agreed_in_period or completed_in_period or lost_in_period
        when ''offered'' then offered_in_period when ''agreed'' then agreed_in_period when ''completed'' then completed_in_period when ''lost'' then lost_in_period
        when ''agreed_ever'' then gap_pct is not null else false end
        order by %I %s nulls last, ref limit %s offset %s) r', sortcol, dir, sortcol, dir, lim, off) into rows using da, flag;
    end if;
  end if;

  if p_export then
    perform public.audit('admin', 'report', p_report, 'report exported', jsonb_build_object('from', p_from, 'to', p_to, 'filters', f, 'group', p_group,
      'rows', case when groups is not null then jsonb_array_length(groups) else jsonb_array_length(rows) end));
  end if;
  return jsonb_build_object('report', p_report, 'from', p_from, 'to', p_to, 'prev_from', pf, 'prev_to', pt, 'compare', p_compare,
    'timezone', 'East Africa Time (UTC+3)', 'generated_at', now(), 'ms', round(extract(epoch from clock_timestamp() - started) * 1000),
    'filters', f, 'kpis', kpis, 'trend', trend, 'groups', groups, 'group_columns', gcols, 'rows_kind', kind, 'columns', to_jsonb(cols), 'sort', sortcol, 'desc', p_desc,
    'total', total, 'page', case when p_export then 1 else greatest(coalesce(p_page, 1), 1) end, 'size', lim, 'rows', rows);
end $$;
revoke execute on function public.admin_report(text, date, date, boolean, jsonb, text, text, boolean, int, int, boolean) from public, anon;
grant execute on function public.admin_report(text, date, date, boolean, jsonb, text, text, boolean, int, int, boolean) to authenticated;

-- Options: add garages, scopes and models, and the new definitions
create or replace function public.admin_report_options() returns jsonb language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_admin();
  return jsonb_build_object('makes', (select coalesce(jsonb_agg(distinct make order by make), '[]'::jsonb) from public.listings),
    'models', (select coalesce(jsonb_agg(jsonb_build_object('value', m.make || '|' || m.model, 'label', m.make || ' ' || m.model) order by m.make, m.model), '[]'::jsonb) from (select distinct make, model from public.listings) m),
    'garages', (select coalesce(jsonb_agg(jsonb_build_object('value', g.id, 'label', g.name) order by g.name), '[]'::jsonb) from public.garages g where g.status in ('certified','suspended')),
    'scopes', '["general","engine","body","electrics","brakes"]'::jsonb,
    'price_bands', '["Under 20m","20m to 40m","40m to 70m","70m to 100m","Over 100m"]'::jsonb,
    'status_groups', '["draft","pending","live","sold","expired","removed"]'::jsonb,
    'age_bands', '["0 to 7 days","8 to 30 days","31 to 60 days","61 to 90 days","Over 90 days"]'::jsonb,
    'glossary', public.report_glossary() || public.report_glossary_2(), 'today', (now() at time zone 'Africa/Kampala')::date);
end $$;
revoke execute on function public.admin_report_options() from public, anon;
grant execute on function public.admin_report_options() to authenticated;
