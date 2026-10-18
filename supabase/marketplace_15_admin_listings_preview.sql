-- Part 15: the admin Cars page shows the same cards as the marketplace, for every status, without making anything public.
-- One source for the card's data: listing_card(). The marketplace (browse_listings) and the admin page (admin_listings) both use it.
-- browse_listings keeps its rule: only live and reserved cars. admin_listings needs is_admin() and returns every status.

create or replace function public.listing_card(l public.listings) returns jsonb
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
  select to_jsonb(l) - 'logbook_name_matches' - 'owner_authorised' - 'rule_min_pct' - 'rule_min_amount' - 'admin_note' - 'seller_id'
    || jsonb_build_object(
      'views_7d', (select count(*) from public.listing_views v where v.listing_id = l.id and v.day > current_date - 7),
      'saves', (select count(*) from public.saves s where s.listing_id = l.id),
      'offers', (select count(*) from public.deals d where d.listing_id = l.id),
      'review', (select jsonb_build_object('verdict',r.verdict,'score',r.score,'verify_code',r.verify_code,'valid_until',r.valid_until,'garage',r.garage_name)
                 from public.reviews r where r.id = l.current_review_id),
      'saved', exists (select 1 from public.saves s where s.listing_id = l.id and s.user_id = auth.uid()))
$$;
revoke execute on function public.listing_card(public.listings) from public, anon, authenticated;

create or replace function public.browse_listings(p_country text default null) returns setof jsonb
language sql stable security definer set search_path = public set "TimeZone" to 'Africa/Kampala' as $$
  select public.listing_card(l)
  from public.listings l
  where l.status in ('live','reserved') and (p_country is null or l.country = p_country)
  order by l.live_at desc
$$;

-- Every car, any status, for Saaz staff: the same card, plus whether buyers can see it
create or replace function public.admin_listings(p_status text default null) returns setof jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_admin();
  return query
  select public.listing_card(l) || jsonb_build_object('public', l.status in ('live','reserved','sold'))
  from public.listings l
  where p_status is null or p_status = '' or l.status = p_status
     or (p_status = 'not_public' and l.status not in ('live','reserved','sold'))
  order by l.updated_at desc
  limit 500;
end $$;
revoke execute on function public.admin_listings(text) from public, anon;
grant execute on function public.admin_listings(text) to authenticated;
