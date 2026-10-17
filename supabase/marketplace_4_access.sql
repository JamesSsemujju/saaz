-- Saaz marketplace, part 4 of 4: who can read what. Nobody writes tables directly; every change goes through a function.

-- Internal helpers must not be callable from the website.
revoke execute on function public.audit(text,text,text,text,jsonb) from public, anon, authenticated;
revoke execute on function public.notify(uuid,text,text,text,text[]) from public, anon, authenticated;
revoke execute on function public.notify_admins(text,text,text) from public, anon, authenticated;
revoke execute on function public.notify_garage(uuid,text,text,text) from public, anon, authenticated;
revoke execute on function public.put_next_in_play(uuid) from public, anon, authenticated;
revoke execute on function public.pass_on(uuid,text) from public, anon, authenticated;
revoke execute on function public.deal_agree(uuid,text) from public, anon, authenticated;
revoke execute on function public.handle_new_user() from public, anon, authenticated;
revoke execute on function public.seller_side_users(public.listings) from public, anon, authenticated;
revoke execute on function public.next_garage(public.listings) from public, anon, authenticated;
revoke execute on function public.review_canonical(public.reviews) from public, anon, authenticated;

-- Row-level security on every new table. No insert, update or delete policies: writes only through functions.
alter table public.settings enable row level security;
alter table public.regions enable row level security;
alter table public.profiles enable row level security;
alter table public.vehicles enable row level security;
alter table public.odometer_readings enable row level security;
alter table public.listings enable row level security;
alter table public.garages enable row level security;
alter table public.garage_members enable row level security;
alter table public.garage_invites enable row level security;
alter table public.conversations enable row level security;
alter table public.pass_reasons enable row level security;
alter table public.messages enable row level security;
alter table public.reviews enable row level security;
alter table public.deals enable row level security;
alter table public.deal_events enable row level security;
alter table public.listing_views enable row level security;
alter table public.saves enable row level security;
alter table public.notifications enable row level security;
alter table public.audit_log enable row level security;

create policy "anyone reads settings" on public.settings for select using (true);
create policy "anyone reads regions" on public.regions for select using (true);

create policy "own profile or admin" on public.profiles for select using (id = auth.uid() or public.is_admin());

create policy "signed-in read vehicles" on public.vehicles for select using (auth.uid() is not null);
create policy "anyone reads odometer history" on public.odometer_readings for select using (true);

create policy "public cars, own cars, garage jobs, admin" on public.listings for select using (
  status in ('live','reserved','sold') or seller_id = auth.uid() or public.is_admin() or public.garage_on_listing(id));

create policy "certified garages public, own garage, admin" on public.garages for select using (
  status = 'certified' or public.is_admin() or id = public.my_team_garage());

create policy "own team or admin" on public.garage_members for select using (
  public.is_admin() or user_id = auth.uid() or garage_id = public.my_team_garage());
create policy "garage owners and admin see invites" on public.garage_invites for select using (
  public.is_admin() or garage_id in (select garage_id from public.garage_members m where m.user_id = auth.uid() and m.role = 'owner' and m.status = 'active'));

create policy "seller, garage, admin" on public.conversations for select using (
  public.is_admin() or garage_id = public.my_garage_id() or public.is_seller_of(listing_id));
create policy "seller and admin read pass reasons" on public.pass_reasons for select using (
  public.is_admin() or exists (select 1 from public.conversations c where c.id = pass_reasons.conversation_id and public.is_seller_of(c.listing_id)));
-- Messages: only the two sides. Admin only for Saaz-owned cars, where admin is the seller.
create policy "only the two sides" on public.messages for select using (
  public.can_read_messages(conversation_id));

create policy "issued reviews public, drafts to the garage, admin" on public.reviews for select using (
  status in ('issued','superseded','void') or public.is_admin() or garage_id = public.my_garage_id() or public.is_seller_of(listing_id));

create policy "buyer, seller, admin" on public.deals for select using (
  buyer_id = auth.uid() or public.is_admin() or public.is_seller_of(listing_id));
create policy "buyer, seller, admin" on public.deal_events for select using (
  public.can_see_deal(deal_id));

create policy "own saves" on public.saves for select using (user_id = auth.uid());
create policy "own notifications" on public.notifications for select using (user_id = auth.uid());
create policy "admins read audit" on public.audit_log for select using (public.is_admin());
-- listing_views: no select policy. Counts come from listing_stats() and whats_selling().

-- Mark notifications read
create or replace function public.mark_read(p_ids uuid[]) returns void language sql security definer set search_path = public as
$$ update public.notifications set read = true where user_id = auth.uid() and id = any(p_ids) $$;

-- Admins see every notice the system sent (the Outbox)
create policy "admins read all notifications" on public.notifications for select using (public.is_admin());

-- Car photos: signed-in sellers upload into their own folder (<account id>/...). Reading stays public.
create policy "sellers upload own photos" on storage.objects for insert to authenticated
  with check (bucket_id = 'car-photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "sellers delete own photos" on storage.objects for delete to authenticated
  using (bucket_id = 'car-photos' and (storage.foldername(name))[1] = auth.uid()::text);
