-- Saaz marketplace, part 6: fixes from the system audit (17 Oct 2026). See docs/system-audit.md, findings F-03 to F-07.
-- Only adds or replaces functions and settings. Deletes and drops nothing.

-- F-03 Uganda only: new listings, garages and profiles must be in Uganda. (Kenya rows in `regions` stay, unused, for later expansion.)
create or replace function public.require_uganda(p_country text) returns void language plpgsql immutable set search_path = public as $$
begin
  if coalesce(p_country, 'UG') <> 'UG' then raise exception 'Saaz operates in Uganda only.'; end if;
end $$;

create or replace function public.guard_uganda() returns trigger language plpgsql set search_path = public as $$
begin
  perform public.require_uganda(new.country);
  return new;
end $$;
create trigger listings_uganda_only before insert or update of country on public.listings for each row execute function public.guard_uganda();
create trigger garages_uganda_only before insert or update of country on public.garages for each row execute function public.guard_uganda();
create trigger profiles_uganda_only before insert or update of country on public.profiles for each row execute function public.guard_uganda();
revoke execute on function public.guard_uganda() from public, anon, authenticated;

-- F-04 A garage is only put in play if someone on its team can act (an Active member).
create or replace function public.next_garage(l public.listings) returns uuid language sql stable security definer set search_path = public as $$
  select g.id from public.garages g
  join public.regions gr on gr.name = g.region
  join public.regions lr on lr.name = l.region
  where g.status = 'certified' and g.country = l.country
    and exists (select 1 from public.garage_members a where a.garage_id = g.id and a.status = 'active')
    and not exists (select 1 from public.garage_members m where m.garage_id = g.id and m.status <> 'removed' and m.user_id = l.seller_id)
    and not exists (select 1 from public.conversations c where c.listing_id = l.id and c.garage_id = g.id and c.round = l.line_round)
  order by sqrt(power(gr.lat - lr.lat, 2) + power((gr.lng - lr.lng) * cos(radians(lr.lat)), 2)),
    (select count(*) from public.conversations c2 where c2.garage_id = g.id and c2.status in ('in_play','agreed')),
    g.certified_at
  limit 1
$$;
revoke execute on function public.next_garage(public.listings) from public, anon, authenticated;

-- F-05 One notice per admin when the line is empty on a Saaz-owned car (admins were told twice).
create or replace function public.put_next_in_play(p_listing uuid) returns uuid language plpgsql security definer set search_path = public as $$
declare l public.listings; gid uuid; cid uuid; gname text;
begin
  select * into l from public.listings where id = p_listing;
  if l.status <> 'awaiting_review' then return null; end if;
  gid := public.next_garage(l);
  if gid is null then
    update public.listings set line_empty = true where id = p_listing;
    perform public.notify_admins('line_empty','No garage left in line for ' || l.ref || '. Assign one or restart the line.','#/admin/car/' || l.id);
    if not l.saaz_owned then
      perform public.notify(l.seller_id, 'line_empty', 'Saaz will find a garage for ' || l.ref || ' and let you know.', '#/my/cars/' || l.id);
    end if;
    perform public.audit('system','listing',l.id::text,'garage line empty');
    return null;
  end if;
  insert into public.conversations (listing_id, garage_id, round, deadline)
  values (p_listing, gid, l.line_round, now() + make_interval(hours => (public.setting('garage_contact_hours'))::text::int))
  returning id into cid;
  update public.listings set line_empty = false where id = p_listing;
  select name into gname from public.garages where id = gid;
  perform public.notify_garage(gid,'garage_in_play','A ' || l.year || ' ' || l.make || ' ' || l.model || ' in ' || l.region ||
    ' is yours to contact. Message the seller within ' || (public.setting('garage_contact_hours')) || ' hours.','#/garage/job/' || cid);
  perform public.notify(u, 'garage_in_play', gname || ' will contact you about ' || l.ref || ' inside Saaz.', '#/my/cars/' || l.id)
    from public.seller_side_users(l) u;
  perform public.audit('system','conversation',cid::text,'garage put in play', jsonb_build_object('listing',l.ref,'garage',gname));
  return cid;
end $$;
revoke execute on function public.put_next_in_play(uuid) from public, anon, authenticated;

-- F-06 Cars stuck with an empty line get a garage as soon as one can act (garage certified, or its first member signs in).
create or replace function public.requeue_empty_lines() returns int language plpgsql security definer set search_path = public as $$
declare r record; n int := 0;
begin
  for r in select id from public.listings where status = 'awaiting_review' and line_empty order by submitted_at loop
    if public.put_next_in_play(r.id) is not null then n := n + 1; end if;
  end loop;
  return n;
end $$;
revoke execute on function public.requeue_empty_lines() from public, anon, authenticated;

create or replace function public.after_garage_ready() returns trigger language plpgsql security definer set search_path = public as $$
begin
  perform public.requeue_empty_lines();
  return null;
end $$;
create trigger garage_members_ready after insert or update of status on public.garage_members
  for each row when (new.status = 'active') execute function public.after_garage_ready();
create trigger garages_ready after update of status on public.garages
  for each row when (new.status = 'certified') execute function public.after_garage_ready();
revoke execute on function public.after_garage_ready() from public, anon, authenticated;

-- F-07 Dates follow East Africa Time (the database clock is UTC; a review issued at 01:00 EAT was dated the day before).
alter function public.record_view(uuid, text) set timezone = 'Africa/Kampala';
alter function public.tick() set timezone = 'Africa/Kampala';
alter function public.issue_review(uuid) set timezone = 'Africa/Kampala';
alter function public.verify_review(text) set timezone = 'Africa/Kampala';
alter function public.review_document(text) set timezone = 'Africa/Kampala';
alter function public.listing_stats(uuid) set timezone = 'Africa/Kampala';
alter function public.browse_listings(text) set timezone = 'Africa/Kampala';
alter function public.my_listings(boolean) set timezone = 'Africa/Kampala';
alter function public.garage_respond(uuid, text, date) set timezone = 'Africa/Kampala';

-- F-16 Car photos: images only, 2 MB at most (the app shrinks photos to about 40 KB before upload).
update storage.buckets set file_size_limit = 2097152, allowed_mime_types = array['image/webp','image/jpeg','image/png'] where id = 'car-photos';
