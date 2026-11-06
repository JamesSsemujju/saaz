-- Saaz marketplace part 27: Build Assistant for the whole Saaz team (6 Nov 2026). Run after part 26.
-- James: staff use the Build Assistant too, and what they ask for waits for an admin's approval before the agent sees it.
--   - Everyone on the Saaz team (Admin or Staff, signed in with their authenticator) can open the Build Assistant.
--     Developers added by an admin still can too.
--   - An admin's request is queued for the agent at once, as before. A staff request waits as "Waiting for admin approval";
--     an admin approves it (it joins the queue) or declines it with a reason. Every step is in the task's history.
--   - Only admins switch the assistant on or off, and only admins approve (unchanged: build_set_enabled is admin only).
-- Changes no existing row. Safe to run twice.

alter table build.tasks drop constraint if exists tasks_status_check;
alter table build.tasks add constraint tasks_status_check check (status in ('awaiting_approval','queued','acknowledged','in_progress',
  'needs_clarification','blocked','implemented','verifying','verified','failed','cancelled'));
alter table build.task_events drop constraint if exists task_events_actor_kind_check;
alter table build.task_events add constraint task_events_actor_kind_check check (actor_kind in ('user','agent','system','admin'));

create or replace function build.require(p_need_on boolean DEFAULT true)
 RETURNS uuid
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'build'
AS $function$
declare u uuid := auth.uid();
begin
  if u is null or not public.is_admin() then   -- part 27: the whole Saaz team (admins, staff, developers added as members are admins too)
    raise exception 'Not found.' using errcode = '42501';   -- same answer as any missing page: no hint that it exists
  end if;
  if p_need_on and not (select enabled from build.settings where id = 1) then
    raise exception 'The Build Assistant is switched off.' using errcode = '42501';
  end if;
  return u;
end $function$;

create or replace function public.build_status()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'build'
AS $function$
declare u uuid := auth.uid(); s build.settings; ok boolean;
begin
  ok := u is not null and public.is_admin();
  if not ok then return jsonb_build_object('allowed', false); end if;
  select * into s from build.settings where id = 1;
  return jsonb_build_object('allowed', true, 'enabled', s.enabled, 'can_switch', public.is_full_admin(), 'can_approve', public.is_full_admin(),
    'awaiting_approval', (select count(*) from build.tasks where status = 'awaiting_approval'),
    'project', s.project, 'environment', s.environment,
    'agent_last_seen', (select max(last_seen_at) from build.agent_runs),
    'open_tasks', (select count(*) from build.tasks where status not in ('verified','cancelled')));
end $function$;

create or replace function build.can_move(p_from text, p_to text, p_actor text)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'public', 'pg_temp'
AS $function$
  select case
    when p_actor = 'user' then (p_to = 'cancelled' and p_from not in ('verified','cancelled'))
                             or (p_to = 'queued' and p_from in ('needs_clarification','blocked','failed'))   -- answered, unblocked or retried
    when p_actor = 'admin' then p_from = 'awaiting_approval' and p_to in ('queued','cancelled')   -- part 27: an admin approves or declines
    when p_actor = 'agent' then (p_from, p_to) in (
       ('queued','acknowledged'), ('acknowledged','in_progress'), ('acknowledged','needs_clarification'), ('acknowledged','blocked'),
       ('in_progress','needs_clarification'), ('in_progress','blocked'), ('in_progress','implemented'), ('in_progress','failed'),
       ('implemented','verifying'), ('verifying','verified'), ('verifying','failed'), ('verifying','in_progress'))
    when p_actor = 'system' then (p_from in ('acknowledged','in_progress','verifying') and p_to = 'queued')   -- an agent's lease ran out
    else false end $function$;

create or replace function public.build_submit(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'build'
AS $function$
declare u uuid := build.require(); s build.settings; th uuid; m build.messages; t build.tasks; r jsonb; n int := 0;
  v_body text := trim(coalesce(p->>'body','')); mk text := coalesce(p->>'message_kind','instruction');
begin
  select * into m from build.messages where client_key = p->>'client_key';
  if m.id is not null then   -- the same submission again (double tap, retry after a dropped connection): return what was saved
    select * into t from build.tasks where source_message_id = m.id;
    return jsonb_build_object('message_id', m.id, 'task', case when t.id is not null then jsonb_build_object('id', t.id, 'ref', t.ref, 'status', t.status) end, 'repeat', true);
  end if;
  if coalesce(p->>'client_key','') = '' then raise exception 'Missing submission key.'; end if;
  if v_body = '' then raise exception 'Write something first.'; end if;
  if p->>'kind' not in ('annotation','chat') or mk not in ('instruction','note') then raise exception 'Unknown kind.'; end if;
  if p->>'kind' = 'annotation' and jsonb_array_length(coalesce(p->'refs','[]')) = 0 then raise exception 'A comment needs at least one element.'; end if;
  perform build.check_refs(v_body, p->'refs');
  select * into s from build.settings where id = 1;
  th := nullif(p->>'thread_id','')::uuid;
  if th is not null and not exists (select 1 from build.threads where id = th and kind = p->>'kind') then raise exception 'Not found.'; end if;
  if th is null then
    insert into build.threads (kind, scope, route, created_by)
    values (p->>'kind', case when p->>'kind' = 'annotation' then 'element' else coalesce(nullif(p->>'scope',''), 'project') end,
            case when coalesce(p->>'scope','') = 'project' and p->>'kind' = 'chat' then null else left(p->>'route', 200) end, u) returning id into th;
  end if;
  insert into build.messages (thread_id, author_kind, author_id, kind, body, route, environment, build_version, client_key)
  values (th, 'user', u::text, mk, v_body, left(p->>'route', 200), s.environment, left(p->>'build_version', 40), p->>'client_key') returning * into m;
  for r in select * from jsonb_array_elements(coalesce(p->'refs','[]')) loop
    n := n + 1;
    insert into build.message_refs (message_id, element_id, ref_name, ordinal, item_key)
    values (m.id, (r->>'element_id')::uuid, r->>'ref_name', n, left(r->>'item_key', 40)) on conflict do nothing;
  end loop;
  if mk = 'instruction' then
    insert into build.tasks (thread_id, source_message_id, scope, route, summary, status, created_by)
    values (th, m.id, case when p->>'kind' = 'annotation' then 'element' else (select scope from build.threads where id = th) end,
            m.route, left(regexp_replace(v_body, '\s+', ' ', 'g'), 140), case when public.is_full_admin() then 'queued' else 'awaiting_approval' end, u) returning * into t;
    insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note)
    values (t.id, 'user', u::text, null, t.status, case when t.status = 'queued' then 'Saved and queued for the agent.' else 'Saved. Waiting for an admin to approve it.' end);
    if t.status = 'awaiting_approval' then
      perform public.notify(a.user_id, 'build_approval', t.ref || ' from ' || coalesce((select name from public.profiles where id = u), 'Saaz staff') || ' is waiting for your approval in the Build Assistant: ' || left(t.summary, 80), '#/admin', '{app}')
        from public.admins a where a.role = 'admin';
    end if;
  end if;
  return jsonb_build_object('message_id', m.id, 'thread_id', th, 'saved_at', m.created_at,
    'task', case when t.id is not null then jsonb_build_object('id', t.id, 'ref', t.ref, 'status', t.status) end);
end $function$;

create or replace function public.build_edit(p_message uuid, p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'build'
AS $function$
declare u uuid := build.require(); m build.messages; v int; t build.tasks; v_body text := trim(coalesce(p->>'body',''));
begin
  select * into m from build.messages where id = p_message and author_kind = 'user' for update;
  if m.id is null or m.author_id <> u::text then raise exception 'Not found.'; end if;
  select * into t from build.tasks where source_message_id = m.id;
  if t.id is not null and t.status not in ('awaiting_approval','queued','needs_clarification','blocked') then raise exception 'Work on this has started. Add a note to the task instead.'; end if;
  if v_body = '' then raise exception 'Write something first.'; end if;
  perform build.check_refs(v_body, p->'refs');
  if (select kind from build.threads where id = m.thread_id) = 'annotation' and jsonb_array_length(coalesce(p->'refs','[]')) = 0 then raise exception 'A comment needs at least one element.'; end if;
  select coalesce(max(version), 0) + 1 into v from build.message_versions where message_id = m.id;
  insert into build.message_versions (message_id, version, body, refs, replaced_by)
  values (m.id, v, m.body, (select coalesce(jsonb_agg(jsonb_build_object('element_id', x.element_id, 'ref_name', x.ref_name, 'item_key', x.item_key) order by x.ordinal), '[]')
                            from build.message_refs x where x.message_id = m.id and x.active), u);
  update build.messages set body = v_body, edited_at = now() where id = m.id;
  update build.message_refs set active = false where message_id = m.id;
  insert into build.message_refs (message_id, element_id, ref_name, ordinal, item_key, active)
  select m.id, (j->>'element_id')::uuid, j->>'ref_name', (row_number() over ())::int, left(j->>'item_key', 40), true from jsonb_array_elements(coalesce(p->'refs','[]')) j
  on conflict (message_id, element_id) do update set ordinal = excluded.ordinal, ref_name = excluded.ref_name, item_key = excluded.item_key, active = true;
  if t.id is not null then
    update build.tasks set summary = left(regexp_replace(trim(p->>'body'), '\s+', ' ', 'g'), 140), updated_at = now() where id = t.id;
    insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note, detail)
    values (t.id, 'user', u::text, t.status, t.status, 'Instruction edited; version ' || v || ' kept.', jsonb_build_object('version', v));
  end if;
  return jsonb_build_object('message_id', m.id, 'version_kept', v);
end $function$;

create or replace function public.build_task_action(p_task uuid, p_action text, p_reason text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'build'
AS $function$
declare u uuid := build.require();
begin
  if p_action = 'cancel' then perform build.move(p_task, 'cancelled', 'user', u::text, coalesce(nullif(trim(p_reason),''), 'Cancelled.'));
  elsif p_action = 'retry' then perform build.move(p_task, 'queued', 'user', u::text, coalesce(nullif(trim(p_reason),''), 'Retry requested.'));
  elsif p_action in ('approve','decline') then   -- part 27: only an admin, only a task waiting for approval
    if not public.is_full_admin() then raise exception 'Only an admin approves Build Assistant requests.'; end if;
    if p_action = 'decline' and coalesce(trim(p_reason),'') = '' then raise exception 'Say why, so the person who asked knows.'; end if;
    perform build.move(p_task, case when p_action = 'approve' then 'queued' else 'cancelled' end, 'admin', u::text,
      case when p_action = 'approve' then coalesce('Approved: ' || nullif(trim(p_reason),''), 'Approved; queued for the agent.') else 'Declined: ' || trim(p_reason) end);
    perform public.notify(t.created_by::uuid, 'build_' || p_action || 'd', t.ref || case when p_action = 'approve' then ' was approved and is queued for the agent.' else ' was declined: ' || trim(p_reason) end, '#/admin', '{app}')
      from build.tasks t where t.id = p_task;
  else raise exception 'Unknown action.'; end if;
end $function$;

-- Tell the API about the changed functions now (Supabase usually does this by itself)
notify pgrst, 'reload schema';
