-- Saaz marketplace, part 5: hardening after Supabase's security check (17 Oct 2026).
-- 1. Fixed search path on the small helper functions.
alter function public.check_plate(text, text) set search_path = public;
alter function public.check_vin(text) set search_path = public;
alter function public.mask_contacts(text) set search_path = public;
alter function public.panel_keys() set search_path = public;
alter function public.review_keys() set search_path = public;
alter function public.rule_broken(public.listings, bigint, boolean) set search_path = public;
-- 2. Actions that need a signed-in account can't be called by visitors at all (they already refuse; this closes the door earlier).
revoke execute on function public.update_profile(text,text,text), public.garage_sign_in(), public.apply_garage(jsonb), public.resubmit_garage(uuid,jsonb),
  public.admin_decide_garage(uuid,text,text), public.admin_add_garage(jsonb,text,text,text,text), public.add_garage_member(text,text,text,text),
  public.remove_garage_member(uuid), public.vin_lookup(text), public.save_listing(jsonb), public.submit_listing(uuid), public.change_price(uuid,bigint),
  public.reopen_for_changes(uuid), public.withdraw_listing(uuid), public.set_offer_rules(uuid,jsonb), public.send_message(uuid,text),
  public.seller_respond(uuid,boolean,text), public.garage_respond(uuid,text,date), public.admin_assign_garage(uuid,uuid), public.admin_restart_line(uuid),
  public.start_review(uuid), public.save_review(uuid,jsonb), public.discard_review(uuid), public.issue_review(uuid),
  public.admin_decide_listing(uuid,text,text,boolean), public.admin_void_review(uuid,text), public.make_offer(uuid,bigint,boolean,text),
  public.deal_action(uuid,text,bigint,text,boolean), public.deal_contacts(uuid), public.toggle_save(uuid), public.admin_set_user(uuid,text,boolean,text),
  public.admin_set_setting(text,jsonb), public.admin_add_import(jsonb), public.listing_history(uuid), public.admin_conversation_counts(),
  public.my_listings(boolean), public.garage_jobs(), public.garage_team(uuid), public.deal_view(uuid), public.my_deals(), public.mark_read(uuid[]),
  public.require_user(), public.require_admin()
  from public, anon;
grant execute on function public.update_profile(text,text,text), public.garage_sign_in(), public.apply_garage(jsonb), public.resubmit_garage(uuid,jsonb),
  public.admin_decide_garage(uuid,text,text), public.admin_add_garage(jsonb,text,text,text,text), public.add_garage_member(text,text,text,text),
  public.remove_garage_member(uuid), public.vin_lookup(text), public.save_listing(jsonb), public.submit_listing(uuid), public.change_price(uuid,bigint),
  public.reopen_for_changes(uuid), public.withdraw_listing(uuid), public.set_offer_rules(uuid,jsonb), public.send_message(uuid,text),
  public.seller_respond(uuid,boolean,text), public.garage_respond(uuid,text,date), public.admin_assign_garage(uuid,uuid), public.admin_restart_line(uuid),
  public.start_review(uuid), public.save_review(uuid,jsonb), public.discard_review(uuid), public.issue_review(uuid),
  public.admin_decide_listing(uuid,text,text,boolean), public.admin_void_review(uuid,text), public.make_offer(uuid,bigint,boolean,text),
  public.deal_action(uuid,text,bigint,text,boolean), public.deal_contacts(uuid), public.toggle_save(uuid), public.admin_set_user(uuid,text,boolean,text),
  public.admin_set_setting(text,jsonb), public.admin_add_import(jsonb), public.listing_history(uuid), public.admin_conversation_counts(),
  public.my_listings(boolean), public.garage_jobs(), public.garage_team(uuid), public.deal_view(uuid), public.my_deals(), public.mark_read(uuid[]),
  public.require_user(), public.require_admin()
  to authenticated;
