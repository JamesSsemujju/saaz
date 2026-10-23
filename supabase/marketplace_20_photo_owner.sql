-- Part 20 (23 Oct 2026): a seller's listing can only use photos that seller uploaded.
-- Before: save_listing stored any photo path it was sent, so a seller could put another seller's (public) photos on their car.
-- Rule: on a private seller's car, every NEW photo path must sit in that seller's own folder in car-photos (<seller id>/...) and exist there.
-- Photos already on the car are left alone, so no existing listing breaks. Saaz-owned cars are not checked (Saaz staff upload those).
-- Admin acting for a seller can't add photos from the admin's own folder: the seller uploads their own (unchanged behaviour in the app).
-- NOT APPLIED to the live project. Run it in the SQL Editor after review.
create or replace function public.check_listing_photos() returns trigger
language plpgsql security definer set search_path = public as $$
declare ph text;
begin
  if new.saaz_owned or new.seller_id is null then return new; end if;
  foreach ph in array coalesce(new.photos, '{}') loop
    if tg_op = 'UPDATE' and ph = any(coalesce(old.photos, '{}')) then continue; end if;
    if split_part(ph, '/', 1) <> new.seller_id::text or ph like '%..%' then
      raise exception 'One of the photos was not uploaded from your account. Remove it and add it again.'; end if;
    if not exists (select 1 from storage.objects o where o.bucket_id = 'car-photos' and o.name = ph) then
      raise exception 'One of the photos did not finish uploading. Remove it and add it again.'; end if;
  end loop;
  return new;
end $$;
revoke execute on function public.check_listing_photos() from public, anon, authenticated;
drop trigger if exists listings_photo_owner on public.listings;
create trigger listings_photo_owner before insert or update of photos on public.listings
  for each row execute function public.check_listing_photos();
