-- Part 11: an admin can do what a seller or buyer can do, for them, with a reason, and it is all in the history.
-- Like an event platform's staff managing an event for the organiser: the change is made, and the trail shows who, when and why.
--
-- How it works: admin_act() checks the admin (pinned authenticator, part 10), needs a reason, then runs the SAME function the
-- seller or buyer would run, so every business rule still applies (minimum price, 4 photos, offer rules, and so on).
-- While it runs, a transaction-only setting says which person and which car or deal the admin is acting for.
--   * is_listing_seller / is_seller_of / deal_side accept the admin only for that one car or deal, only inside admin_act.
--   * audit() stamps every row written during the action: actor = the admin, role = admin, plus for_user, for_side and reason.
--   * deal_events rows get admin_id and admin_reason, so the deal page shows "Saaz team, for the seller: <reason>".
--   * The person acted for gets a notice with the reason.
-- Guard: an admin can't accept a figure that an admin entered for the other side. One real person has to be in every agreement
-- (or use "Mark agreed" with a note of how both sides confirmed, which already exists).

-- What the admin is doing right now, if anything. Empty outside admin_act, and for anyone who is not a signed-in admin.
create or replace function public.acting() returns jsonb
language sql stable security definer set search_path = public as $$
  select case when coalesce(current_setting('saaz.acting', true), '') <> '' and public.is_admin()
              then current_setting('saaz.acting', true)::jsonb end
$$;
revoke execute on function public.acting() from public, anon, authenticated;

create or replace function public.is_listing_seller(l public.listings) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(l.seller_id = auth.uid(), false) or (l.saaz_owned and public.is_admin())
    or coalesce(public.acting()->>'side' = 'seller' and public.acting()->>'listing' = l.id::text, false)
$$;

create or replace function public.is_seller_of(p_listing uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.listings l where l.id = p_listing and public.is_listing_seller(l))
$$;

create or replace function public.deal_side(d public.deals) returns text
language sql stable security definer set search_path = public as $$
  select case
    when public.acting()->>'side' = 'buyer' and public.acting()->>'deal' = d.id::text then 'buyer'
    when public.acting()->>'side' = 'seller' and public.acting()->>'listing' = d.listing_id::text then 'seller'
    when public.acting() is not null then null
    when d.buyer_id = auth.uid() then 'buyer'
    when exists (select 1 from public.listings l where l.id = d.listing_id and public.is_listing_seller(l)) then 'seller'
    when public.is_admin() then 'admin' end
$$;

-- Every audit row written while acting says so
create or replace function public.audit(p_role text, p_entity text, p_id text, p_action text, p_detail jsonb default '{}'::jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare a jsonb := public.acting();
begin
  insert into public.audit_log (actor_id, actor_role, entity, entity_id, action, detail)
  values (auth.uid(), case when a is null then p_role else 'admin' end, p_entity, p_id, p_action,
          coalesce(p_detail, '{}'::jsonb) || case when a is null then '{}'::jsonb
            else jsonb_build_object('for_user', a->'for', 'for_side', a->'side', 'reason', a->'reason') end);
end $$;
revoke execute on function public.audit(text,text,text,text,jsonb) from public, anon, authenticated;

-- Deal events record the admin and the reason
alter table public.deal_events add column if not exists admin_id uuid references auth.users(id);
alter table public.deal_events add column if not exists admin_reason text;
create or replace function public.stamp_deal_event() returns trigger
language plpgsql security definer set search_path = public as $$
declare a jsonb := public.acting();
begin
  if a is not null then new.admin_id := auth.uid(); new.admin_reason := a->>'reason'; end if;
  return new;
end $$;
drop trigger if exists deal_events_stamp on public.deal_events;
create trigger deal_events_stamp before insert on public.deal_events for each row execute function public.stamp_deal_event();

-- Submitting for a seller checks the SELLER's phone and listing limit, not the admin's
create or replace function public.submit_listing(p_listing uuid) returns void
language plpgsql security definer set search_path = public as $$
declare u uuid := public.require_user(); l public.listings; pr public.profiles; n int; minp bigint;
begin
  select * into l from public.listings where id = p_listing;
  if l is null or not public.is_listing_seller(l) then raise exception 'Not your listing.'; end if;
  if l.status not in ('draft','changes_requested','re_review_due') then raise exception 'This listing is already submitted.'; end if;
  if not l.saaz_owned then u := l.seller_id; end if;
  select * into pr from public.profiles where id = u;
  if not l.saaz_owned then
    if (public.setting('require_phone_verified'))::text::boolean and not pr.phone_verified then
      raise exception 'Verify your phone number before selling.'; end if;
    if not pr.trusted then
      select count(*) into n from public.listings where seller_id = u and id <> l.id
        and status not in ('draft','sold','rejected','withdrawn');
      if n >= (public.setting('listing_limit'))::text::int then
        raise exception 'You can have % active listings. Withdraw one first.', (public.setting('listing_limit')); end if;
    end if;
    if not l.logbook_name_matches and not l.owner_authorised then
      raise exception 'Confirm the logbook is in your name, or that the owner authorised the sale.'; end if;
  end if;
  if array_length(l.photos,1) is null or array_length(l.photos,1) < 4 then raise exception 'Add at least 4 photos.'; end if;
  if array_length(l.photos,1) > 12 then raise exception 'Use at most 12 photos.'; end if;
  if length(l.description) < 30 then raise exception 'Write at least 30 characters of description.'; end if;
  minp := case when l.currency = 'KES' then (public.setting('min_price_kes'))::text::bigint else (public.setting('min_price_ugx'))::text::bigint end;
  if l.price < minp then raise exception 'The lowest asking price is % %.', l.currency, minp; end if;
  update public.listings set status = 'awaiting_review', submitted_at = now(), admin_note = null, updated_at = now() where id = l.id;
  perform public.audit(case when l.saaz_owned then 'admin' else 'seller' end,'listing',l.id::text,'submitted');
  perform public.put_next_in_play(l.id);
end $$;

-- The one door: admin acts for a seller or buyer
create or replace function public.admin_act(p_kind text, p_target uuid, p_reason text, p jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path = public as $$
declare me uuid := public.require_admin(); why text := trim(coalesce(p_reason, ''));
  l public.listings; d public.deals; c public.conversations; side text; who uuid; label text; link text; res jsonb := '{}'::jsonb;
  last_fig public.deal_events; ent text; ent_id text;
begin
  if length(why) < 10 then raise exception 'Write the reason (10 characters or more). The seller or buyer sees it.'; end if;
  if p_kind in ('deal_seller', 'deal_buyer') then
    select * into d from public.deals where id = p_target;
    if d is null then raise exception 'Deal not found.'; end if;
    select * into l from public.listings where id = d.listing_id;
    side := case p_kind when 'deal_seller' then 'seller' else 'buyer' end;
    ent := 'deal'; ent_id := d.id::text;
  elsif p_kind in ('garage_agree', 'garage_pass') then
    select * into c from public.conversations where id = p_target;
    if c is null then raise exception 'Garage conversation not found.'; end if;
    select * into l from public.listings where id = c.listing_id; side := 'seller';
    ent := 'conversation'; ent_id := c.id::text;
  else
    select * into l from public.listings where id = p_target;
    if l is null then raise exception 'Car not found.'; end if;
    side := 'seller'; ent := 'listing'; ent_id := l.id::text;
  end if;
  if l.saaz_owned and side = 'seller' then raise exception 'This is a Saaz car: use its own page, you are already the seller.'; end if;
  who := case side when 'seller' then l.seller_id else d.buyer_id end;
  if who = me then raise exception 'This is your own car or offer. Use the normal page.'; end if;

  if p_kind in ('deal_seller', 'deal_buyer') then
    if coalesce(p->>'action', '') not in ('counter', 'accept', case side when 'seller' then 'reject' else 'withdraw' end) then
      raise exception 'The % can counter, accept or %.', side, case side when 'seller' then 'reject' else 'withdraw' end; end if;
    if p->>'action' = 'accept' then
      select * into last_fig from public.deal_events where deal_id = d.id and kind in ('offer','counter','propose') order by created_at desc limit 1;
      if last_fig.admin_id is not null or last_fig.by_side = 'admin' then
        raise exception 'An admin entered the figure on the table. The other side must confirm it themselves, or use Mark agreed with a note of how both sides confirmed.'; end if;
    end if;
  end if;

  perform set_config('saaz.acting', jsonb_build_object('listing', l.id, 'deal', d.id, 'side', side, 'for', who, 'reason', why)::text, true);
  case p_kind
    when 'price' then perform public.change_price(l.id, (p->>'price')::bigint); label := 'changed the asking price to ' || l.currency || ' ' || to_char((p->>'price')::bigint, 'FM999,999,999,999');
    when 'offer_rules' then perform public.set_offer_rules(l.id, p->'rules'); label := 'changed the offer rules';
    when 'edit_draft' then perform public.save_listing((p->'listing') || jsonb_build_object('id', l.id)); label := 'edited the draft';
    when 'submit' then perform public.submit_listing(l.id); label := 'sent the car for a Saaz inspection';
    when 'reopen' then perform public.reopen_for_changes(l.id); label := 'took the car off sale to edit it';
    when 'withdraw' then perform public.withdraw_listing(l.id); label := 'withdrew the car';
    when 'garage_agree' then perform public.seller_respond(c.id, true, null); label := 'agreed to the garage for the inspection';
    when 'garage_pass' then perform public.seller_respond(c.id, false, why); label := 'passed on the garage';
    when 'deal_seller', 'deal_buyer' then
      res := public.deal_action(d.id, p->>'action', nullif(p->>'amount', '')::bigint, nullif(p->>'message', ''), nullif(p->>'trade_in', '')::boolean);
      label := case p->>'action' when 'counter' then 'countered with ' || l.currency || ' ' || to_char((p->>'amount')::bigint, 'FM999,999,999,999')
                 when 'accept' then 'accepted the figure' when 'reject' then 'declined the offer' else 'withdrew the offer' end;
    else raise exception 'Unknown action.';
  end case;
  perform public.audit('admin', ent, ent_id, 'Saaz team acted for the ' || side || ': ' || label, jsonb_build_object('input', p));
  perform set_config('saaz.acting', '', true);

  link := case side when 'buyer' then '#/deals/' || d.id when 'seller' then case when d.id is not null then '#/deals/' || d.id else '#/my/cars/' || l.id end end;
  perform public.notify(who, 'admin_acted', 'Saaz team ' || label || ' on ' || l.ref || ' for you. Reason: ' || why, link, '{app,email}');
  return res || jsonb_build_object('done', label);
end $$;
revoke execute on function public.admin_act(text, uuid, text, jsonb) from public, anon;
grant execute on function public.admin_act(text, uuid, text, jsonb) to authenticated;

-- The car's history (seller and admin see it) now includes its deals, and shows the reason when the Saaz team acted
create or replace function public.listing_history(p_listing uuid)
returns table(at timestamptz, who text, action text) language sql stable security definer set search_path = public as $$
  select a.at,
    case when a.actor_role = 'admin' then 'Our team' when a.actor_role = 'system' then 'Saaz'
      else coalesce((select name from public.profiles where id = a.actor_id), a.actor_role) end,
    a.action || case when a.detail ? 'reason' then ' (reason: ' || (a.detail->>'reason') || ')' else '' end
  from public.audit_log a, public.listings l
  where l.id = p_listing and (public.is_listing_seller(l) or public.is_admin())
    and ((a.entity = 'listing' and a.entity_id = l.id::text)
      or (a.entity = 'conversation' and a.entity_id in (select id::text from public.conversations where listing_id = l.id))
      or (a.entity = 'review' and a.entity_id in (select id::text from public.reviews where listing_id = l.id))
      or (a.entity = 'deal' and a.entity_id in (select id::text from public.deals where listing_id = l.id)))
  order by a.at
$$;
