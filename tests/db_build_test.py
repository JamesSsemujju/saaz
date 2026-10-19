"""Tests for part 18: the Build Assistant. Fresh database.
Who can reach it, the switch, element references, comments with many tags, chat, the agent's queue (delivery, acknowledgement,
leases, retries, two agents at once, dependencies), honest status rules, edits kept as versions, and privacy."""
import json, threading, psycopg2, admin_session
DSN = dict(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb", options="-c TimeZone=UTC")
conn = psycopg2.connect(**DSN); conn.autocommit = True; cur = conn.cursor()
ok = bad = 0
def su(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def as_(uid, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, uid) if uid else "",)); cur.execute("set role " + ("authenticated" if uid else "anon"))
    try: cur.execute(q, a or None); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def err(uid, q, a=()):
    try: as_(uid, q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def suerr(q, a=()):
    try: su(q, a); return None
    except psycopg2.Error as e: return e.diag.message_primary or "error"
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
def user(e, n): return su("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("admin@saaz.test", "Ann Admin"); su("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
ST = user("staff@saaz.test", "Stan Staff"); su("insert into admins (user_id, name, role) values (%s,'Stan Staff','staff')", (ST,))
DEV = user("dev@saaz.test", "Dee Dev"); su("insert into admins (user_id, name, role) values (%s,'Dee Dev','staff')", (DEV,))
S = user("seller@x.test", "Sam Seller")
J = lambda x: json.dumps(x)
def submit(uid, p): return as_(uid, "select build_submit(%s::jsonb)", (J(p),))[0][0]
def el(uid, path, label, stab="stable", base=None, route="/browse"):
    return as_(uid, "select build_element(%s::jsonb)", (J({"anchor_path": path, "descriptor": {"tag": "div", "role": "", "label": label}, "stability": stab, "route": route, "base_name": base or path.split(">")[-1]}),))[0][0]
def agent(q, a=()): return su(q, a)[0][0]

# ---------- who can reach it ----------
check("visitors can't even ask whether it exists", err(None, "select build_status()") is not None)
check("a seller is told nothing", as_(S, "select build_status()")[0][0] == {"allowed": False})
check("staff who aren't developers are told nothing", as_(ST, "select build_status()")[0][0] == {"allowed": False})
st = as_(A, "select build_status()")[0][0]
check("a full admin sees it, switched off by default", st["allowed"] and st["enabled"] is False and st["can_switch"] is True, st)
check("switched off: nothing can be submitted", "switched off" in (err(A, "select build_submit('{}'::jsonb)") or ""))
check("staff can't switch it on", err(ST, "select build_set_enabled(true, 'go')") is not None)
check("a seller can't switch it on", err(S, "select build_set_enabled(true, 'go')") is not None)
r = as_(A, "select build_set_enabled(true, 'Start building')")[0][0]
check("a full admin switches it on, and it is recorded with who and why", r["changed"] and su("select count(*) from build.toggles where enabled and actor=%s and reason='Start building'", (A,))[0][0] == 1
      and su("select count(*) from audit_log where action='build assistant switched on'")[0][0] == 1)
check("staff can't add developers", err(ST, "select build_member('dev@saaz.test', true)") is not None)
check("only Saaz team members can be developers", "Saaz team" in (err(A, "select build_member('seller@x.test', true)") or ""))
as_(A, "select build_member('dev@saaz.test', true)")
check("a developer on the team sees it", as_(DEV, "select build_status()")[0][0]["allowed"] is True)
check("a developer can't switch it", err(DEV, "select build_set_enabled(false, 'x')") is not None)

# ---------- privacy ----------
check("website roles can't read the build schema at all", all(err(u, "select count(*) from build.messages") is not None for u in (None, S, A)))
check("a seller can't call any Build Assistant function", all(err(S, q) is not None for q in ["select build_history(10, null)", "select build_submit('{\"kind\":\"chat\",\"body\":\"x\",\"client_key\":\"k\"}'::jsonb)", "select build_find_ref('header')"]))
check("nobody on the website can call the agent's functions (not even an admin)", all(err(u, q) is not None for u in (None, S, A) for q in
      ["select build_agent_claim('x', 60)", "select build_agent_checkin('x', null)", "select build_agent_context(gen_random_uuid())", "select build_agent_update('x', gen_random_uuid(), 'verified', 'x', '{}')"]))

# ---------- element references ----------
h = el(A, "header", "Saaz header"); h2 = el(A, "header", "Saaz header")
check("the same element gets the same reference", h["id"] == h2["id"] and h["ref_name"] == "header")
card = el(A, "results>vehicle-card", "Vehicle card", base="vehicle-card")
other_card = el(A, "home-latest>vehicle-card", "Vehicle card", base="vehicle-card")
check("two different elements with the same name are told apart (vehicle-card, vehicle-card-2)", (card["ref_name"], other_card["ref_name"]) == ("vehicle-card", "vehicle-card-2"))
fp = el(A, "results>filter-panel", "Filters", base="filter-panel")
check("bad names are cleaned to short lowercase words", el(A, "x>y", "Weird", base="Show Cars!!", stab="anchored")["ref_name"] == "show-cars")
check("a typed reference resolves when known", as_(A, "select build_find_ref('//filter-panel')")[0][0]["ref_name"] == "filter-panel")
check("an unknown typed reference is reported, not guessed", as_(A, "select build_find_ref('//filter-pannel')")[0][0] == {"found": False})

# ---------- one comment, many elements ----------
body = "The spacing here is inconsistent with //header and should align with the navigation. Also compare it with //filter-panel because both components should follow the same spacing system."
refs = [{"element_id": card["id"], "ref_name": "vehicle-card", "item_key": "SZ-00004"}, {"element_id": h["id"], "ref_name": "header"}, {"element_id": fp["id"], "ref_name": "filter-panel"}]
bad_body = "Fix //header and //vehicle-card"
check("every tagged element must appear in the text", "missing from the text" in (err(A, "select build_submit(%s::jsonb)", (J({"kind": "annotation", "body": bad_body, "refs": refs, "client_key": "c0", "route": "/browse"}),)) or ""))
check("a typed reference that isn't tagged is refused", "Unknown reference: //footer" in (err(A, "select build_submit(%s::jsonb)", (J({"kind": "annotation", "body": "See //vehicle-card and //footer", "refs": refs[:1], "client_key": "c0b", "route": "/browse"}),)) or ""))
check("a comment needs at least one element", "at least one element" in (err(A, "select build_submit(%s::jsonb)", (J({"kind": "annotation", "body": "Hi", "refs": [], "client_key": "c0c"}),)) or ""))
# the first element is the one double-clicked; it appears in the text as written by the editor
full = "//vehicle-card " + body
s1 = submit(A, {"kind": "annotation", "body": full, "refs": refs, "client_key": "c1", "route": "/browse", "build_version": "2026-10-19"})
check("one comment saved with a queued task", s1["task"]["status"] == "queued" and s1["task"]["ref"].startswith("BA-"), s1)
check("the comment keeps all three elements, in order, with the car it was on", su("select array_agg(ref_name order by ordinal), max(item_key) from build.message_refs where message_id=%s", (s1["message_id"],))[0] == (["vehicle-card", "header", "filter-panel"], "SZ-00004"))
check("the text is kept exactly as written", su("select body from build.messages where id=%s", (s1["message_id"],))[0][0] == full)
again = submit(A, {"kind": "annotation", "body": full, "refs": refs, "client_key": "c1", "route": "/browse"})
check("sending the same comment twice saves it once", again.get("repeat") and su("select count(*) from build.tasks")[0][0] == 1)
check("saved is not received: the task is queued, not acknowledged", su("select status from build.tasks")[0][0] == "queued" and
      su("select to_status from build.task_events where task_id=%s order by id", (s1["task"]["id"],)) == [("queued",)])
c1 = submit(A, {"kind": "chat", "message_kind": "note", "scope": "project", "body": "Just a note: the launch is next month.", "client_key": "c2"})
check("a chat note is saved without making a task", c1["task"] is None)
c2 = submit(DEV, {"kind": "chat", "message_kind": "instruction", "scope": "project", "body": "Do not publish these changes until I approve them.", "client_key": "c3"})
check("a chat instruction makes a project-wide task", su("select scope, route from build.tasks where id=%s", (c2["task"]["id"],))[0] == ("project", None))
c3 = submit(A, {"kind": "chat", "message_kind": "instruction", "scope": "page", "route": "/sell/new", "body": "Review the seller form on this page.", "client_key": "c4"})
check("a page instruction keeps its page", su("select scope, route from build.tasks where id=%s", (c3["task"]["id"],))[0] == ("page", "/sell/new"))
hist = as_(A, "select build_history(50, null)")[0][0]
check("history returns threads with messages, references and tasks", len(hist) == 4 and any(t["kind"] == "annotation" and t["messages"][0]["refs"][1]["ref_name"] == "header" for t in hist))

# ---------- editing before work starts keeps the old version ----------
new_body = "//vehicle-card spacing should match //header."
as_(A, "select build_edit(%s, %s::jsonb)", (s1["message_id"], J({"body": new_body, "refs": refs[:2]})))
check("an edit keeps the earlier text and references as version 1", su("select version, body, jsonb_array_length(refs) from build.message_versions where message_id=%s", (s1["message_id"],))[0] == (1, full, 3))
check("the removed tag no longer counts, the others stay", su("select array_agg(ref_name order by ordinal) from build.message_refs where message_id=%s and active", (s1["message_id"],))[0][0] == ["vehicle-card", "header"])
check("the task records the edit", "version 1 kept" in su("select note from build.task_events where task_id=%s order by id desc limit 1", (s1["task"]["id"],))[0][0])
check("someone else can't edit your comment", err(DEV, "select build_edit(%s, %s::jsonb)", (s1["message_id"], J({"body": new_body, "refs": refs[:2]}))) is not None)

# ---------- the agent ----------
agent("select build_agent_checkin('claude-test', 'test run')")
check("the page can see when an agent last checked in", as_(A, "select build_status()")[0][0]["agent_last_seen"] is not None)
ctx = agent("select build_agent_claim('claude-test', 60)")
t1 = ctx["task"]["id"]
check("the agent gets the oldest task with its full context", ctx["task"]["ref"] == s1["task"]["ref"] and [e["ref_name"] for e in ctx["elements"]] == ["vehicle-card", "header"] and ctx["instruction"]["body"] == new_body)
check("the context carries the earlier version and the project-wide instruction to respect", len(ctx["versions"]) == 1 and any(o["summary"].startswith("Do not publish") for o in ctx["related_open"]))
check("delivered is recorded, but it is still not acknowledged", su("select status, attempts, lease_owner from build.tasks where id=%s", (t1,))[0] == ("queued", 1, "claude-test"))
check("acknowledging needs what the agent understood", "understood" in (suerr("select build_agent_update('claude-test', %s, 'acknowledged', 'Got it', '{}')", (t1,)) or ""))
agent("select build_agent_update('claude-test', %s, 'acknowledged', 'Received', %s::jsonb)", (t1, J({"understanding": "Align the card spacing with the header's spacing tokens.", "report": "I understood: align the card spacing with the header."})))
check("acknowledged, with the agent's own words shown in the thread", su("select status from build.tasks where id=%s", (t1,))[0][0] == "acknowledged" and
      su("select count(*) from build.messages where task_id=%s and author_kind='agent' and kind='report'", (t1,))[0][0] == 1)
check("another agent can't act on a task it doesn't hold", "held by another agent" in (suerr("select build_agent_update('other', %s, 'in_progress', 'x', '{}')", (t1,)) or ""))
check("no skipping: acknowledged can't jump to verified", "can't go from acknowledged to verified" in (suerr("select build_agent_update('claude-test', %s, 'verified', 'x', %s::jsonb)", (t1, J({"checks": [{"name": "a", "result": "pass"}]}))) or ""))
agent("select build_agent_update('claude-test', %s, 'in_progress', 'Started', '{}')", (t1,))
check("editing after work started is refused", "started" in (err(A, "select build_edit(%s, %s::jsonb)", (s1["message_id"], J({"body": new_body, "refs": refs[:2]}))) or ""))
check("implemented needs the files that changed", "files" in (suerr("select build_agent_update('claude-test', %s, 'implemented', 'Done', '{}')", (t1,)) or ""))
agent("select build_agent_update('claude-test', %s, 'implemented', 'Card spacing uses --sp-4', %s::jsonb)", (t1, J({"files": ["src/styles/cars.css"], "build_version": "2026-10-19b"})))
agent("select build_agent_update('claude-test', %s, 'verifying', 'Running checks', '{}')", (t1,))
check("verified is refused if a check failed", "did not pass" in (suerr("select build_agent_update('claude-test', %s, 'verified', 'ok', %s::jsonb)", (t1, J({"checks": [{"name": "layout", "result": "pass"}, {"name": "flow", "result": "fail"}]}))) or ""))
check("verified is refused without checks", "checks" in (suerr("select build_agent_update('claude-test', %s, 'verified', 'ok', '{}')", (t1,)) or ""))
agent("select build_agent_update('claude-test', %s, 'verified', 'All checks passed', %s::jsonb)", (t1, J({"checks": [{"name": "layout_audit", "result": "pass"}, {"name": "browser_flow", "result": "pass"}], "report": "Done and checked. Not shipped: ship when you approve."})))
check("the full history: queued, delivered, acknowledged, in progress, implemented, verifying, verified", [x[0] for x in su("select to_status from build.task_events where task_id=%s order by id", (t1,))]
      == ["queued", "queued", "queued", "acknowledged", "in_progress", "implemented", "verifying", "verified"])
check("history can't be rewritten", "append-only" in (suerr("update build.task_events set note='x' where task_id=%s", (t1,)) or ""))

# clarification, answer, back to the queue
ctx2 = agent("select build_agent_claim('claude-test', 60)"); t2 = ctx2["task"]["id"]
check("next task in order: the project-wide instruction", ctx2["task"]["scope"] == "project")
agent("select build_agent_update('claude-test', %s, 'acknowledged', 'Received', %s::jsonb)", (t2, J({"understanding": "Hold releases until approval."})))
agent("select build_agent_update('claude-test', %s, 'needs_clarification', 'Need to know which changes', %s::jsonb)", (t2, J({"question": "Does this cover the reports too, or only the marketplace?"})))
check("a question is shown in the task's conversation", su("select body from build.messages where task_id=%s and kind='question'", (t2,))[0][0].startswith("Does this cover"))
as_(A, "select build_reply(%s, 'Everything. Nothing ships without my yes.', 'r1')", (t2,))
check("answering sends it back to the queue", su("select status from build.tasks where id=%s", (t2,))[0][0] == "queued")
check("a repeated answer is saved once", as_(A, "select build_reply(%s, 'Everything. Nothing ships without my yes.', 'r1')", (t2,))[0][0].get("repeat") is True)

# two agents at once: each task to one agent only
res = []
def claim(name):
    c2 = psycopg2.connect(**DSN); c2.autocommit = True; k = c2.cursor(); k.execute("select build_agent_claim(%s, 60)", (name,)); res.append((name, k.fetchone()[0])); c2.close()
ths = [threading.Thread(target=claim, args=(f"agent-{i}",)) for i in range(4)]; [t.start() for t in ths]; [t.join() for t in ths]
got = [r[1]["task"]["id"] for r in res if r[1]]
check("four agents claiming at once: no task goes to two of them", len(got) == len(set(got)) and len(got) == 2, res)
late = agent("select build_agent_claim('agent-late', 60)")
check("an agent claiming afterwards doesn't get a task another agent already holds (found live: BA-0001 went out 5 times)", late is None or late["task"]["id"] not in got, late and late["task"]["ref"])

# a lease that runs out: back to the queue with the reason, delivered again as attempt 2
held = su("select id, lease_owner from build.tasks where status='queued' and lease_owner is not null order by created_at limit 1")[0]
agent("select build_agent_update(%s, %s, 'acknowledged', 'Received', %s::jsonb)", (held[1], held[0], J({"understanding": "x"})))
su("update build.tasks set lease_until = now() - interval '1 minute' where id=%s", (held[0],))
su("update build.tasks set lease_owner = null, lease_until = null where status='queued'")  # the other claimed task is released for the test
again = agent("select build_agent_claim('claude-test', 60)")
ev = su("select actor_kind, from_status, to_status, note from build.task_events where task_id=%s and actor_kind='system'", (held[0],))
check("a lapsed lease goes back to the queue with the reason recorded", len(ev) == 1 and ev[0][:3] == ("system", "acknowledged", "queued") and "lease ran out" in ev[0][3], ev)
check("and is delivered again as attempt 2", again["task"]["id"] == str(held[0]) or su("select attempts from build.tasks where id=%s", (held[0],))[0][0] >= 2)

# failed, retried, cancelled
tid = again["task"]["id"]
agent("select build_agent_update('claude-test', %s, 'acknowledged', 'Received', %s::jsonb)", (tid, J({"understanding": "x"})))
agent("select build_agent_update('claude-test', %s, 'in_progress', 'Started', '{}')", (tid,))
agent("select build_agent_update('claude-test', %s, 'failed', 'The build stopped: a value not from tokens', %s::jsonb)", (tid, J({"error": "check_layout: 1 value"})))
check("a failure is kept with its cause", su("select status from build.tasks where id=%s", (tid,))[0][0] == "failed" and "check_layout" in json.dumps(su("select detail from build.task_events where task_id=%s and to_status='failed'", (tid,))[0][0]))
as_(A, "select build_task_action(%s, 'retry', 'Try again with the tokens')", (tid,))
check("you can retry a failed task: back to the queue, the failure stays in its history", su("select status from build.tasks where id=%s", (tid,))[0][0] == "queued" and su("select count(*) from build.task_events where task_id=%s and to_status='failed'", (tid,))[0][0] == 1)
as_(A, "select build_task_action(%s, 'cancel', 'Not needed')", (tid,))
check("cancelled is final", "can't go from cancelled" in (err(A, "select build_task_action(%s, 'retry', 'x')", (tid,)) or ""))

# dependencies: a task waits for the one it depends on to be verified
dep = submit(A, {"kind": "chat", "message_kind": "instruction", "scope": "project", "body": "Second step.", "client_key": "c9"})
first_open = su("select id from build.tasks where status='queued' and id<>%s order by created_at limit 1", (dep["task"]["id"],))
blocker = submit(A, {"kind": "chat", "message_kind": "instruction", "scope": "project", "body": "First step.", "client_key": "c10"})
su("update build.tasks set depends_on = array[%s::uuid] where id=%s", (blocker["task"]["id"], dep["task"]["id"]))
su("update build.tasks set status='cancelled' where status='queued' and id not in (%s, %s)", (dep["task"]["id"], blocker["task"]["id"]))
nxt = agent("select build_agent_claim('claude-test', 60)")
check("a task waiting on another is not handed out first", nxt["task"]["id"] == blocker["task"]["id"])

# conflicts: two open comments on the same element are shown to the agent side by side, and unrelated ones are not
x1 = submit(A, {"kind": "annotation", "body": "//header Make this taller.", "refs": [{"element_id": h["id"], "ref_name": "header"}], "client_key": "cx1", "route": "/browse"})
x2 = submit(A, {"kind": "annotation", "body": "//header Make this shorter.", "refs": [{"element_id": h["id"], "ref_name": "header"}], "client_key": "cx2", "route": "/browse"})
x3 = submit(A, {"kind": "annotation", "body": "//filter-panel Tidy the labels.", "refs": [{"element_id": fp["id"], "ref_name": "filter-panel"}], "client_key": "cx3", "route": "/browse"})
rel = [o["ref"] for o in agent("select build_agent_context(%s)", (x2["task"]["id"],))["related_open"]]
check("a second comment on the same element shows the agent the first one, so a conflict can be flagged", x1["task"]["ref"] in rel and x3["task"]["ref"] not in rel, rel)
su("update build.tasks set status='cancelled' where id in (%s, %s, %s)", (x1["task"]["id"], x2["task"]["id"], x3["task"]["id"]))

# ---------- switched off ----------
open_before = su("select count(*) from build.tasks where status not in ('verified','cancelled')")[0][0]
r = as_(A, "select build_set_enabled(false, 'Shipping')")[0][0]
check("switching off records every open task at that moment", r["changed"] and len(r["open_tasks"]) == open_before)
check("switched off: no new comments or messages", "switched off" in (err(A, "select build_submit(%s::jsonb)", (J({"kind": "chat", "body": "x", "client_key": "z1"}),)) or ""))
check("switched off: the agent gets no new tasks", agent("select build_agent_claim('claude-test', 60)") is None)
check("switched off: queued work stays queued (not completed, not removed)", su("select status from build.tasks where id=%s", (dep["task"]["id"],))[0][0] == "queued")
check("switched off: the agent can still record what happened to the task it holds", agent("select build_agent_update('claude-test', %s, 'acknowledged', 'Received before the switch', %s::jsonb)", (blocker["task"]["id"], J({"understanding": "x"})))["status"] == "acknowledged")
check("switched off: history can still be read by admins", len(as_(A, "select build_history(50, null)")[0][0]) >= 4)
check("switched off: the marketplace still works", as_(None, "select count(*) from browse_listings('UG')")[0][0] >= 0)
check("both switches are in the history", su("select count(*) from build.toggles")[0][0] == 2)
print(f"\n{ok} passed, {bad} failed")
