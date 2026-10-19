-- Part 19: Build Assistant claim fix (19 Oct 2026).
-- Found live: a claimed task stays 'queued' (with a lease) until the agent acknowledges it, and build_agent_claim
-- didn't look at that lease, so the next claim handed out the same task again (BA-0001 was delivered 5 times).
-- Now a queued task is handed out only when it has no lease or its lease has run out. Nothing else changes.
-- The full function is repeated so this file can run on its own.

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
  where x.status = 'queued'
    and (x.lease_until is null or x.lease_until < now())   -- not a task already handed to an agent whose lease is still running
    and not exists (select 1 from unnest(x.depends_on) dep join build.tasks d on d.id = dep where d.status <> 'verified')
  order by x.created_at for update skip locked limit 1;
  if t.id is null then return null; end if;
  update build.tasks set lease_owner = p_agent, lease_until = now() + make_interval(mins => greatest(p_lease_minutes, 5)), attempts = attempts + 1 where id = t.id;
  insert into build.task_events (task_id, actor_kind, actor_id, from_status, to_status, note, detail)
  values (t.id, 'agent', p_agent, 'queued', 'queued', 'Delivered to the agent (attempt ' || (t.attempts + 1) || '). Not yet acknowledged.', jsonb_build_object('lease_minutes', greatest(p_lease_minutes, 5)));
  return public.build_agent_context(t.id);
end $$;
revoke execute on function public.build_agent_claim(text,integer) from public, anon, authenticated;
