-- Saaz marketplace, part 8: report privacy (finding F-25, 17 Oct 2026). Run in the Supabase SQL Editor.
-- Before: anyone could list every issued, superseded or void inspection through the API.
-- After: the public sees only the current inspection of a car that is public (live, reserved, sold).
-- The seller, the garage, and admins see their own as before. Report links (#/report/<code>) and Verify still work: they use review_document() and verify_review().

create or replace function public.is_public_review(p_id uuid) returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.listings l where l.current_review_id = p_id and l.status in ('live','reserved','sold'))
$$;
revoke execute on function public.is_public_review(uuid) from public;
grant execute on function public.is_public_review(uuid) to anon, authenticated;

drop policy if exists "issued reviews public, drafts to the garage, admin" on public.reviews;
create policy "current inspection of a public car, own garage, seller, admin" on public.reviews for select using (
  (status = 'issued' and public.is_public_review(id)) or public.is_admin() or garage_id = public.my_garage_id() or public.is_seller_of(listing_id));
