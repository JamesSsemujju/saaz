-- Part 18: Build Assistant. A private development-feedback system inside the Saaz app.
-- Element comments (with many tagged elements), general chat, a durable task queue for the coding agent, honest statuses,
-- and full history. Everything lives in its own schema, `build`, which the website's API does not expose and which the
-- website's roles cannot read. The browser reaches it only through the build_* functions below, each of which checks:
--   1. the caller is in an admin session (password + pinned authenticator: is_admin, part 10/12),
--   2. the caller is a full admin or a listed Build Assistant developer,
--   3. the assistant is switched on (except reading history and the admin switch itself).
-- The coding agent uses the build_agent_* functions. They are not callable by any website role at all
-- (only by the database owner the agent connects as).

create schema if not exists build;
revoke all on schema build from public, anon, authenticated;

-- ---------- tables ----------
create table if not exists build.settings (
  id int primary key default 1 check (id = 1),
  enabled boolean not null default false,
  project text not null default 'saaz',
  environment text not null default 'production',  -- the only Supabase project Saaz has (see project-docs)
  updated_at timestamptz not null default now(),
  updated_by uuid
);
insert into build.settings (id) values (1) on conflict (id) do nothing;

create table if not exists build.toggles (          -- every switch on or off, by whom, and what was open at that moment
  id bigserial primary key, at timestamptz not null default now(), actor uuid not null, enabled boolean not null,
  reason text, open_tasks jsonb not null default '[]');

create table if not exists build.members (          -- developers allowed besides full admins (they must still pass the admin sign-in)
  user_id uuid primary key, role text not null default 'developer' check (role in ('developer')),
  added_by uuid not null, added_at timestamptz not null default now(), removed_by uuid, removed_at timestamptz);

create table if not exists build.elements (         -- one row per element or component that has been referenced
  id uuid primary key default gen_random_uuid(),
  ref_name text not null unique check (ref_name ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and length(ref_name) <= 48),
  anchor_path text not null,                         -- the chain of data-ref names from the page down to this element
  descriptor jsonb not null default '{}',            -- tag, role, visible label (no user data beyond what the page shows)
  stability text not null check (stability in ('stable','anchored','unstable')),
  routes text[] not null default '{}',               -- route patterns where it was seen
  first_seen_at timestamptz not null default now(), last_seen_at timestamptz not null default now(), created_by uuid not null,
  unique (anchor_path, descriptor));

create table if not exists build.threads (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('annotation','chat')),
  scope text not null check (scope in ('project','page','element','task')),
  route text, created_by uuid not null, created_at timestamptz not null default now());

create table if not exists build.messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references build.threads(id),
  task_id uuid,                                      -- a message inside a task's conversation (question, answer, report)
  author_kind text not null check (author_kind in ('user','agent','system')),
  author_id text not null,                           -- user id, or the agent's name
  kind text not null check (kind in ('instruction','note','question','answer','report')),
  body text not null check (length(body) between 1 and 8000),
  route text, environment text not null, build_version text,
  client_key text unique,                            -- the browser's id for this submission: sending twice saves once
  created_at timestamptz not null default now(), edited_at timestamptz);

create table if not exists build.message_versions ( -- the text before every edit
  id bigserial primary key, message_id uuid not null references build.messages(id), version int not null,
  body text not null, refs jsonb not null, replaced_at timestamptz not null default now(), replaced_by uuid not null,
  unique (message_id, version));

create table if not exists build.message_refs (     -- a comment can tag many elements; an element can be in many comments
  message_id uuid not null references build.messages(id), element_id uuid not null references build.elements(id),
  ref_name text not null, ordinal int not null, item_key text, active boolean not null default true, primary key (message_id, element_id));

create sequence if not exists build.task_no;
create table if not exists build.tasks (
  id uuid primary key default gen_random_uuid(),
  ref text not null unique default ('BA-' || lpad(nextval('build.task_no')::text, 4, '0')),
  thread_id uuid not null references build.threads(id), source_message_id uuid not null unique references build.messages(id),
  scope text not null check (scope in ('project','page','element','task')), route text, summary text not null,
  status text not null check (status in ('queued','acknowledged','in_progress','needs_clarification','blocked','implemented',
                                         'verifying','verified','failed','cancelled')),
  depends_on uuid[] not null default '{}',
  lease_owner text, lease_until timestamptz, attempts int not null default 0,
  created_by uuid not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());

create table if not exists build.task_events (      -- append only: every status change, note, file, commit and check
  id bigserial primary key, task_id uuid not null references build.tasks(id), at timestamptz not null default now(),
  actor_kind text not null check (actor_kind in ('user','agent','system')), actor_id text not null,
  from_status text, to_status text, note text, detail jsonb not null default '{}');

create table if not exists build.agent_runs (       -- when an agent session checked in, so the page can say whether one is around
  id bigserial primary key, agent text not null, started_at timestamptz not null default now(), last_seen_at timestamptz not null default now(), note text);

create index if not exists build_messages_thread on build.messages (thread_id, created_at);
create index if not exists build_tasks_status on build.tasks (status, created_at);
create index if not exists build_events_task on build.task_events (task_id, id);
create index if not exists build_refs_element on build.message_refs (element_id);

revoke all on all tables in schema build from public, anon, authenticated;
revoke all on all sequences in schema build from public, anon, authenticated;

-- History can't be rewritten: events, versions and toggles accept new rows only
create or replace function build.append_only() returns trigger language plpgsql as $$
begin raise exception 'Build Assistant history is append-only.'; end $$;
do $t$ begin
  if not exists (select 1 from pg_trigger where tgname = 'build_events_append_only') then
    create trigger build_events_append_only before update or delete on build.task_events for each row execute function build.append_only();
    create trigger build_versions_append_only before update or delete on build.message_versions for each row execute function build.append_only();
    create trigger build_toggles_append_only before update or delete on build.toggles for each row execute function build.append_only();
  end if;
end $t$;

-- ---------- who may use it ----------
create or replace function build.member_ok(p uuid) returns boolean language sql stable security definer set search_path = public, build as $$
  select exists (select 1 from build.members m where m.user_id = p and m.removed_at is null) $$;

-- Raises unless the caller is allowed; p_need_on: the assistant must also be switched on
create or replace function build.require(p_need_on boolean default true) returns uuid language plpgsql stable security definer set search_path = public, build as $$
declare u uuid := auth.uid();
begin
  if u is null or not public.is_admin() or not (public.is_full_admin() or build.member_ok(u)) then
    raise exception 'Not found.' using errcode = '42501';   -- same answer as any missing page: no hint that it exists
  end if;
  if p_need_on and not (select enabled from build.settings where id = 1) then
    raise exception 'The Build Assistant is switched off.' using errcode = '42501';
  end if;
  return u;
end $$;

-- ---------- allowed status changes (one place) ----------
create or replace function build.can_move(p_from text, p_to text, p_actor text) returns boolean language sql immutable as $$
  select case
    when p_actor = 'user' then (p_to = 'cancelled' and p_from not in ('verified','cancelled'))
                             or (p_to = 'queued' and p_from in ('needs_clarification','blocked','failed'))   -- answered, unblocked or retried
    when p_actor = 'agent' then (p_from, p_to) in (
       ('queued','acknowledged'), ('acknowledged','in_progress'), ('acknowledged','needs_clarification'), ('acknowledged','blocked'),
       ('in_progress','needs_clarification'), ('in_progress','blocked'), ('in_progress','implemented'), ('in_progress','failed'),
       ('implemented','verifying'), ('verifying','verified'), ('verifying','failed'), ('verifying','in_progress'))
    when p_actor = 'system' then (p_from in ('acknowledged','in_progress','verifying') and p_to = 'queued')   -- an agent's lease ran out
    else false end $$;

create or replace function build.move(p_task uuid, p_to text, p_actor_kind text, p_actor text, p_note text, p_detail jsonb default '{}')
returns void language plpgsql security definer set search_path = public, build as $$
declare t build.tasks;
begin
  select * into t from build.tasks where id = p_task for update;
  if t.id is null then raise exception 'Not found.'; end if;
  if not build.can_move(t.status, p_to, p_actor_kind) then
    raise exception 'A task can''t go from % to %.', replace(t.status,'_',' '), replace(p_to,'_',' ');
  end if;
  update build.tasks set status = p_to, updated_at = now(),
    lease_owner = case when p_to in ('acknowledged','in_progress','verifying','implemented') then lease_owner end,
    lease_until = case when p_to in ('acknowledged','in_progress','verifying','implemented') then lease_until end
  where id = p_task;
  insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note, detail)
  values (p_task, p_actor_kind, p_actor, t.status, p_to, p_note, coalesce(p_detail, '{}'));
end $$;

-- ---------- status for the page: is the assistant available to this person? ----------
-- Anyone signed in may ask; everyone except allowed admins gets {"allowed": false} and nothing else.
create or replace function public.build_status() returns jsonb language plpgsql stable security definer set search_path = public, build as $$
declare u uuid := auth.uid(); s build.settings; ok boolean;
begin
  ok := u is not null and public.is_admin() and (public.is_full_admin() or build.member_ok(u));
  if not ok then return jsonb_build_object('allowed', false); end if;
  select * into s from build.settings where id = 1;
  return jsonb_build_object('allowed', true, 'enabled', s.enabled, 'can_switch', public.is_full_admin(),
    'project', s.project, 'environment', s.environment,
    'agent_last_seen', (select max(last_seen_at) from build.agent_runs),
    'open_tasks', (select count(*) from build.tasks where status not in ('verified','cancelled')));
end $$;

-- ---------- elements: find or register the record behind a reference ----------
-- p: {anchor_path, descriptor:{tag,role,label}, stability, route, base_name}
create or replace function public.build_element(p jsonb) returns jsonb language plpgsql security definer set search_path = public, build as $$
declare u uuid := build.require(); e build.elements; base text; nm text; i int := 1; d jsonb;
begin
  if coalesce(p->>'anchor_path','') = '' or p->>'stability' not in ('stable','anchored','unstable') then raise exception 'This element can''t be identified.'; end if;
  d := jsonb_build_object('tag', left(coalesce(p->'descriptor'->>'tag',''), 20), 'role', left(coalesce(p->'descriptor'->>'role',''), 40),
                          'label', left(coalesce(p->'descriptor'->>'label',''), 60));
  select * into e from build.elements where anchor_path = p->>'anchor_path' and descriptor = d;
  if e.id is null then
    base := left(trim(both '-' from regexp_replace(lower(coalesce(p->>'base_name','element')), '[^a-z0-9]+', '-', 'g')), 40);
    if base = '' then base := 'element'; end if;
    nm := base;
    while exists (select 1 from build.elements where ref_name = nm) loop i := i + 1; nm := base || '-' || i; end loop;
    insert into build.elements (ref_name, anchor_path, descriptor, stability, routes, created_by)
    values (nm, p->>'anchor_path', d, p->>'stability', array_remove(array[p->>'route'], null), u) returning * into e;
  else
    update build.elements set last_seen_at = now(),
      routes = case when p->>'route' is null or p->>'route' = any(routes) then routes else routes || (p->>'route') end
    where id = e.id returning * into e;
  end if;
  return jsonb_build_object('id', e.id, 'ref_name', e.ref_name, 'stability', e.stability, 'anchor_path', e.anchor_path);
end $$;

-- A reference typed by hand: resolve it, or say it is unknown. Never a guess.
create or replace function public.build_find_ref(p_name text) returns jsonb language plpgsql stable security definer set search_path = public, build as $$
declare u uuid := build.require(); e build.elements;
begin
  select * into e from build.elements where ref_name = lower(regexp_replace(coalesce(p_name,''), '^//', ''));
  if e.id is null then return jsonb_build_object('found', false); end if;
  return jsonb_build_object('found', true, 'id', e.id, 'ref_name', e.ref_name, 'stability', e.stability);
end $$;

-- ---------- references in a text: every //name written must be a tagged element, and every tagged element must be written ----------
-- A // after a letter, digit, slash or colon is ordinary text (a web address like https://saaz.ug), not a reference.
create or replace function build.check_refs(p_body text, p_refs jsonb) returns void language plpgsql stable security definer set search_path = public, build as $$
declare typed text[]; listed text[];
begin
  select coalesce(array_agg(distinct x[1]), '{}') into typed from regexp_matches(p_body, '(?:^|[^/\w:])//([a-z0-9]+(?:-[a-z0-9]+)*)', 'g') x;
  select coalesce(array_agg(distinct e.ref_name), '{}') into listed
    from jsonb_array_elements(coalesce(p_refs,'[]')) j join build.elements e on e.id = (j->>'element_id')::uuid and e.ref_name = j->>'ref_name';
  if jsonb_array_length(coalesce(p_refs,'[]')) <> cardinality(listed) then raise exception 'A tagged element is no longer known. Remove it and tag it again.'; end if;
  if not (typed <@ listed) then raise exception 'Unknown reference: //%. Tag the element instead of typing it.', (select x from unnest(typed) x where not x = any(listed) limit 1); end if;
  if not (listed <@ typed) then raise exception 'A tagged element is missing from the text.'; end if;
end $$;

-- ---------- submitting: a comment on elements, or a chat message ----------
-- p: {kind:'annotation'|'chat', message_kind:'instruction'|'note', scope, route, body, refs:[{element_id, ref_name, item_key}],
--     thread_id (to continue a chat thread), client_key, build_version}
-- The body keeps the //references as written; every one of them must match a ref in refs (checked here).
create or replace function public.build_submit(p jsonb) returns jsonb language plpgsql security definer set search_path = public, build as $$
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
            m.route, left(regexp_replace(v_body, '\s+', ' ', 'g'), 140), 'queued', u) returning * into t;
    insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note)
    values (t.id, 'user', u::text, null, 'queued', 'Saved and queued for the agent.');
  end if;
  return jsonb_build_object('message_id', m.id, 'thread_id', th, 'saved_at', m.created_at,
    'task', case when t.id is not null then jsonb_build_object('id', t.id, 'ref', t.ref, 'status', t.status) end);
end $$;

-- Edit a submitted message before work starts: the earlier text and its references are kept as a version; the task is told
create or replace function public.build_edit(p_message uuid, p jsonb) returns jsonb language plpgsql security definer set search_path = public, build as $$
declare u uuid := build.require(); m build.messages; v int; t build.tasks; v_body text := trim(coalesce(p->>'body',''));
begin
  select * into m from build.messages where id = p_message and author_kind = 'user' for update;
  if m.id is null or m.author_id <> u::text then raise exception 'Not found.'; end if;
  select * into t from build.tasks where source_message_id = m.id;
  if t.id is not null and t.status not in ('queued','needs_clarification','blocked') then raise exception 'Work on this has started. Add a note to the task instead.'; end if;
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
end $$;

-- A reply inside a task: answers a question (the task goes back to the queue) or adds a note
create or replace function public.build_reply(p_task uuid, p_body text, p_client_key text) returns jsonb language plpgsql security definer set search_path = public, build as $$
declare u uuid := build.require(); t build.tasks; m build.messages; s build.settings;
begin
  select * into m from build.messages where client_key = p_client_key;
  if m.id is not null then return jsonb_build_object('message_id', m.id, 'repeat', true); end if;
  select * into t from build.tasks where id = p_task;
  if t.id is null then raise exception 'Not found.'; end if;
  if trim(coalesce(p_body,'')) = '' then raise exception 'Write something first.'; end if;
  select * into s from build.settings where id = 1;
  insert into build.messages (thread_id, task_id, author_kind, author_id, kind, body, route, environment, client_key)
  values (t.thread_id, t.id, 'user', u::text, case when t.status = 'needs_clarification' then 'answer' else 'note' end, trim(p_body), t.route, s.environment, p_client_key) returning * into m;
  if t.status in ('needs_clarification','blocked') then
    perform build.move(t.id, 'queued', 'user', u::text, 'Answered; back in the queue.', jsonb_build_object('message_id', m.id));
  else
    insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note, detail)
    values (t.id, 'user', u::text, t.status, t.status, 'Note added.', jsonb_build_object('message_id', m.id));
  end if;
  return jsonb_build_object('message_id', m.id);
end $$;

-- Cancel or retry a task (the user's only status changes)
create or replace function public.build_task_action(p_task uuid, p_action text, p_reason text) returns void language plpgsql security definer set search_path = public, build as $$
declare u uuid := build.require();
begin
  if p_action = 'cancel' then perform build.move(p_task, 'cancelled', 'user', u::text, coalesce(nullif(trim(p_reason),''), 'Cancelled.'));
  elsif p_action = 'retry' then perform build.move(p_task, 'queued', 'user', u::text, coalesce(nullif(trim(p_reason),''), 'Retry requested.'));
  else raise exception 'Unknown action.'; end if;
end $$;

-- History: threads with their messages, references, tasks and events (newest first). Reading works when switched off too.
create or replace function public.build_history(p_limit int default 50, p_task uuid default null) returns jsonb language plpgsql stable security definer set search_path = public, build as $$
declare u uuid := build.require(false);
begin
  return (select coalesce(jsonb_agg(x order by x->>'last_at' desc), '[]') from (
    select jsonb_build_object('thread_id', th.id, 'kind', th.kind, 'scope', th.scope, 'route', th.route, 'created_at', th.created_at,
      'last_at', (select max(created_at) from build.messages where thread_id = th.id),
      'messages', (select jsonb_agg(jsonb_build_object('id', m.id, 'author_kind', m.author_kind, 'kind', m.kind, 'body', m.body, 'route', m.route,
          'created_at', m.created_at, 'edited_at', m.edited_at, 'task_id', m.task_id,
          'author', case when m.author_kind = 'user' then (select coalesce(name, email) from public.profiles where id::text = m.author_id) else m.author_id end,
          'refs', (select coalesce(jsonb_agg(jsonb_build_object('element_id', r.element_id, 'ref_name', r.ref_name, 'item_key', r.item_key, 'stability', e.stability) order by r.ordinal), '[]')
                   from build.message_refs r join build.elements e on e.id = r.element_id where r.message_id = m.id and r.active),
          'versions', (select count(*) from build.message_versions v where v.message_id = m.id)) order by m.created_at) from build.messages m where m.thread_id = th.id),
      'tasks', (select coalesce(jsonb_agg(jsonb_build_object('id', t.id, 'ref', t.ref, 'status', t.status, 'summary', t.summary, 'scope', t.scope,
          'source_message_id', t.source_message_id, 'attempts', t.attempts, 'created_at', t.created_at, 'updated_at', t.updated_at,
          'events', (select jsonb_agg(jsonb_build_object('at', ev.at, 'actor_kind', ev.actor_kind, 'from', ev.from_status, 'to', ev.to_status, 'note', ev.note, 'detail', ev.detail) order by ev.id)
                     from build.task_events ev where ev.task_id = t.id)) order by t.created_at), '[]') from build.tasks t where t.thread_id = th.id)
    ) x
    from build.threads th
    where p_task is null or th.id = (select thread_id from build.tasks where id = p_task)
    order by (select max(created_at) from build.messages where thread_id = th.id) desc nulls last
    limit least(greatest(coalesce(p_limit, 50), 1), 200)) s(x));
end $$;

-- ---------- the switch (full admins only) ----------
-- Switching off: no new submissions, the agent can't take new tasks, queued tasks stay queued (not completed, not removed),
-- a task already taken keeps its status and its agent can still record what happened to it. History stays.
create or replace function public.build_set_enabled(p_on boolean, p_reason text) returns jsonb language plpgsql security definer set search_path = public, build as $$
declare u uuid := auth.uid(); open jsonb;
begin
  if u is null or not public.is_admin() or not public.is_full_admin() then raise exception 'Not found.' using errcode = '42501'; end if;
  if (select enabled from build.settings where id = 1) = p_on then return jsonb_build_object('enabled', p_on, 'changed', false); end if;
  select coalesce(jsonb_agg(jsonb_build_object('ref', ref, 'status', status)), '[]') into open from build.tasks where status not in ('verified','cancelled');
  update build.settings set enabled = p_on, updated_at = now(), updated_by = u where id = 1;
  insert into build.toggles (actor, enabled, reason, open_tasks) values (u, p_on, nullif(trim(coalesce(p_reason,'')),''), open);
  perform public.audit('admin', 'build_assistant', 'settings', case when p_on then 'build assistant switched on' else 'build assistant switched off' end,
    jsonb_build_object('reason', p_reason, 'open_tasks', jsonb_array_length(open)));
  return jsonb_build_object('enabled', p_on, 'changed', true, 'open_tasks', open);
end $$;

-- Admin page: switch, history of the switch, developers
create or replace function public.build_admin() returns jsonb language plpgsql stable security definer set search_path = public, build as $$
declare u uuid := auth.uid();
begin
  if u is null or not public.is_admin() or not public.is_full_admin() then raise exception 'Not found.' using errcode = '42501'; end if;
  return jsonb_build_object('settings', (select to_jsonb(s) from build.settings s),
    'toggles', (select coalesce(jsonb_agg(jsonb_build_object('at', t.at, 'enabled', t.enabled, 'reason', t.reason, 'open_tasks', t.open_tasks,
        'by', (select coalesce(name, email) from public.profiles where id = t.actor)) order by t.id desc), '[]') from build.toggles t),
    'members', (select coalesce(jsonb_agg(jsonb_build_object('user_id', m.user_id, 'name', p.name, 'email', p.email, 'added_at', m.added_at) order by m.added_at), '[]')
        from build.members m join public.profiles p on p.id = m.user_id where m.removed_at is null),
    'counts', (select jsonb_object_agg(status, n) from (select status, count(*) n from build.tasks group by 1) c),
    'agent_last_seen', (select max(last_seen_at) from build.agent_runs));
end $$;

create or replace function public.build_member(p_email text, p_add boolean) returns void language plpgsql security definer set search_path = public, build as $$
declare u uuid := auth.uid(); target uuid;
begin
  if u is null or not public.is_admin() or not public.is_full_admin() then raise exception 'Not found.' using errcode = '42501'; end if;
  select a.user_id into target from public.admins a join public.profiles p on p.id = a.user_id where lower(p.email) = lower(trim(p_email));
  if target is null then raise exception 'Only people on the Saaz team (with an authenticator) can be Build Assistant developers.'; end if;
  if p_add then
    insert into build.members (user_id, added_by) values (target, u) on conflict (user_id) do update set removed_at = null, removed_by = null, added_by = u, added_at = now();
  else
    update build.members set removed_at = now(), removed_by = u where user_id = target and removed_at is null;
  end if;
  perform public.audit('admin', 'build_assistant', target::text, case when p_add then 'build assistant developer added' else 'build assistant developer removed' end);
end $$;

-- ---------- the coding agent ----------
-- Not callable from the website: execute is revoked from every website role below.
-- The agent connects as the database owner (the Supabase connection Claude uses) and calls these.

create or replace function public.build_agent_checkin(p_agent text, p_note text default null) returns bigint language plpgsql security definer set search_path = public, build as $$
declare id bigint;
begin
  insert into build.agent_runs (agent, note) values (left(p_agent, 60), p_note) returning agent_runs.id into id;
  return id;
end $$;

-- Take the next task: oldest queued task whose dependencies are verified, or a task whose agent's lease ran out.
-- One task, one agent at a time (row lock + lease). Returns null when switched off or nothing is ready.
create or replace function public.build_agent_claim(p_agent text, p_lease_minutes int default 60) returns jsonb language plpgsql security definer set search_path = public, build as $$
declare t build.tasks;
begin
  update build.agent_runs set last_seen_at = now() where id = (select max(id) from build.agent_runs where agent = p_agent);
  if not (select enabled from build.settings where id = 1) then return null; end if;
  -- leases that ran out go back to the queue first, with the reason recorded
  for t in select * from build.tasks where status in ('acknowledged','in_progress','verifying') and lease_until < now() for update skip locked loop
    perform build.move(t.id, 'queued', 'system', 'lease', 'The agent''s lease ran out (' || coalesce(t.lease_owner,'?') || '); back in the queue for a retry.');
  end loop;
  select * into t from build.tasks x
  where x.status = 'queued' and not exists (select 1 from unnest(x.depends_on) dep join build.tasks d on d.id = dep where d.status <> 'verified')
  order by x.created_at for update skip locked limit 1;
  if t.id is null then return null; end if;
  update build.tasks set lease_owner = p_agent, lease_until = now() + make_interval(mins => greatest(p_lease_minutes, 5)), attempts = attempts + 1 where id = t.id;
  insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note, detail)
  values (t.id, 'agent', p_agent, 'queued', 'queued', 'Delivered to the agent (attempt ' || (t.attempts + 1) || '). Not yet acknowledged.', jsonb_build_object('lease_minutes', greatest(p_lease_minutes, 5)));
  return public.build_agent_context(t.id);
end $$;

-- Everything the agent needs to understand a task: the instruction, its elements, the conversation, related open work
create or replace function public.build_agent_context(p_task uuid) returns jsonb language sql stable security definer set search_path = public, build as $$
  select jsonb_build_object('task', to_jsonb(t) - 'lease_owner', 'instruction', to_jsonb(m),
    'elements', (select coalesce(jsonb_agg(jsonb_build_object('ref_name', r.ref_name, 'item_key', r.item_key, 'anchor_path', e.anchor_path, 'descriptor', e.descriptor,
        'stability', e.stability, 'routes', e.routes, 'last_seen_at', e.last_seen_at) order by r.ordinal), '[]')
        from build.message_refs r join build.elements e on e.id = r.element_id where r.message_id = m.id and r.active),
    'versions', (select coalesce(jsonb_agg(to_jsonb(v) order by v.version), '[]') from build.message_versions v where v.message_id = m.id),
    'thread', (select coalesce(jsonb_agg(jsonb_build_object('author_kind', x.author_kind, 'kind', x.kind, 'body', x.body, 'at', x.created_at) order by x.created_at), '[]')
        from build.messages x where x.thread_id = t.thread_id),
    'events', (select coalesce(jsonb_agg(to_jsonb(ev) order by ev.id), '[]') from build.task_events ev where ev.task_id = t.id),
    -- other open tasks on the same elements, and standing project-wide instructions: read before acting, flag conflicts
    'related_open', (select coalesce(jsonb_agg(distinct jsonb_build_object('ref', o.ref, 'status', o.status, 'summary', o.summary, 'scope', o.scope)), '[]')
        from build.tasks o where o.id <> t.id and o.status not in ('verified','cancelled','failed')
          and (o.scope = 'project' or exists (select 1 from build.message_refs a join build.message_refs b on a.element_id = b.element_id
                 where a.message_id = o.source_message_id and b.message_id = t.source_message_id and a.active and b.active))))
  from build.tasks t join build.messages m on m.id = t.source_message_id where t.id = p_task $$;

-- Every other step: acknowledge (with what it understood), start, ask, block, implemented, verifying, verified, failed.
-- p_detail: {files:[], commits:[], checks:[{name, result}], build_version, understanding, question}
create or replace function public.build_agent_update(p_agent text, p_task uuid, p_to text, p_note text, p_detail jsonb default '{}') returns jsonb language plpgsql security definer set search_path = public, build as $$
declare t build.tasks; s build.settings;
begin
  select * into t from build.tasks where id = p_task for update;
  if t.id is null then raise exception 'Not found.'; end if;
  if t.lease_owner is distinct from p_agent and p_to <> 'acknowledged' then raise exception 'This task is held by another agent (%).', coalesce(t.lease_owner, 'none'); end if;
  if t.status = 'queued' and (t.lease_owner is distinct from p_agent or t.lease_until < now()) then raise exception 'Claim the task before acknowledging it.'; end if;
  if coalesce(trim(p_note),'') = '' then raise exception 'Say what happened.'; end if;
  if p_to = 'verified' and jsonb_array_length(coalesce(p_detail->'checks','[]')) = 0 then raise exception 'Verified needs the checks that passed.'; end if;
  if p_to = 'verified' and exists (select 1 from jsonb_array_elements(p_detail->'checks') c where c->>'result' <> 'pass') then raise exception 'A check did not pass: not verified.'; end if;
  if p_to = 'implemented' and jsonb_array_length(coalesce(p_detail->'files','[]')) = 0 then raise exception 'Implemented needs the files that changed.'; end if;
  if p_to = 'acknowledged' and coalesce(trim(p_detail->>'understanding'),'') = '' then raise exception 'Acknowledge with what you understood.'; end if;
  perform build.move(p_task, p_to, 'agent', p_agent, p_note, p_detail);
  if p_to in ('needs_clarification','blocked') and coalesce(trim(p_detail->>'question'),'') <> '' then
    select * into s from build.settings where id = 1;
    insert into build.messages (thread_id, task_id, author_kind, author_id, kind, body, route, environment)
    values (t.thread_id, t.id, 'agent', p_agent, 'question', trim(p_detail->>'question'), t.route, s.environment);
  end if;
  if p_to in ('acknowledged','implemented','verified','failed') and coalesce(trim(p_detail->>'report'),'') <> '' then
    select * into s from build.settings where id = 1;
    insert into build.messages (thread_id, task_id, author_kind, author_id, kind, body, route, environment)
    values (t.thread_id, t.id, 'agent', p_agent, 'report', trim(p_detail->>'report'), t.route, s.environment);
  end if;
  update build.tasks set lease_until = case when p_to in ('acknowledged','in_progress','implemented','verifying') then greatest(lease_until, now() + interval '30 minutes') end,
    lease_owner = case when p_to in ('acknowledged','in_progress','implemented','verifying') then p_agent end where id = p_task;
  return jsonb_build_object('task', p_task, 'status', p_to);
end $$;

do $g$ declare f text; begin
  foreach f in array array['build_agent_checkin(text,text)','build_agent_claim(text,integer)','build_agent_context(uuid)','build_agent_update(text,uuid,text,text,jsonb)'] loop
    execute 'revoke execute on function public.' || f || ' from public, anon, authenticated';
  end loop;
  foreach f in array array['build_status()','build_element(jsonb)','build_find_ref(text)','build_submit(jsonb)','build_edit(uuid,jsonb)','build_reply(uuid,text,text)',
                           'build_task_action(uuid,text,text)','build_history(integer,uuid)','build_set_enabled(boolean,text)','build_admin()','build_member(text,boolean)'] loop
    execute 'revoke execute on function public.' || f || ' from public, anon';
    execute 'grant execute on function public.' || f || ' to authenticated';
  end loop;
end $g$;
revoke execute on all functions in schema build from public, anon, authenticated;
