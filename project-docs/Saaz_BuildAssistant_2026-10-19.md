# Saaz Build Assistant (19 Oct 2026)

A private tool inside the Saaz site for building Saaz. You comment on elements of the real page, chat about the project, and a coding agent works the comments as a queue. It is not part of the marketplace. Visitors, buyers, sellers, garages and ordinary staff never see it or its records.

Status: **live since 19 Oct 2026.** Part 18 (`supabase/marketplace_18_build_assistant.sql`) was applied in Supabase as build_18a to build_18e, after the same five pieces passed the full database test locally. The switch starts **off**, so nobody sees the Build button until a full admin turns it on in Admin, System, Build Assistant (after you ship this code).

Checked live after applying (read-only): 11 tables, 15 functions, 3 history-lock triggers, switch off, 0 tasks. A visitor is refused `build_status`; a signed-in non-admin gets `{"allowed": false}`; signed-in users are refused the agent functions and the `build` tables.

## Who can use it

All three must be true, checked by the database on every call (`build.require`):
1. An admin session: password plus the pinned authenticator (`is_admin`).
2. A full admin (`admins.role = 'admin'`), or a Saaz team member a full admin added as a developer (Admin, System, Build Assistant, Developers).
3. The switch is on.

Anyone else asking gets `{"allowed": false}` and nothing more. The page only loads `build-assistant.js` after the database says yes, so the code isn't even downloaded for customers.

## Commenting on elements

1. Click **Build** (bottom left), tick **Select elements on the page**.
2. Move the mouse: the element under it is outlined. Double-click to start a comment about it. On a phone or tablet: tap to select, then press **Comment** in the panel.
3. While the comment is open, click (or tap) any other element. Its tag, like `//header`, goes in where your cursor is, and the cursor goes back to the comment.
4. Clicking empty page space does nothing. While selecting, the page doesn't react: links don't open, buttons don't press, forms don't submit. Untick the box to use the site normally; the draft stays.
5. **Save comment** saves and queues it. **Cancel** asks before throwing away written text.

Rules the tests prove:
- A tag already in the comment isn't added twice. You're told, with **Insert it again** if you mean it.
- Each tag has a ×. Removing it leaves the words around it as they were.
- The draft survives moving to another page and reloading. It's kept in this browser only and cleared at sign-out.
- You can tag elements from several pages in one comment.
- You can type a tag yourself (`//price-panel`). Save checks it: an unknown name is refused ("Unknown reference: //nosuch"), never guessed. `http://` and `a//b` are not tags.
- Escape stops selecting.

## How elements get their names

Each important component has a `data-ref` name in the code (26 names, list them with `python3 tools/build_refs.py`): `header`, `logo`, `main-nav`, `sell-btn`, `account-menu`, `area-bar`, `footer`, `home-hero`, `home-search`, `latest-cars`, `trust-section`, `filter-panel`, `results-grid`, `vehicle-card`, `pager`, `car-gallery`, `price-panel`, `inspection-card`, `car-details`, `offer-form`, `admin-menu`, and report parts.

| Stability | Meaning | Example |
|---|---|---|
| Stable | The component has a `data-ref` | `//filter-panel` |
| Anchored | Inside a named component, named by the component and its label | `//header-sell-a-car` |
| Unstable | No named component around it; named by its label or tag, saved with its path and text, flagged to the agent | `//button` |

Repeated components get numbers in the order they're tagged (`//vehicle-card`, `//vehicle-card-2`), with the car's reference stored as the key, so `//vehicle-card-2` always means the same car. Every tag is stored as a row (`build.message_refs`) linking the comment to the element record, with its position in the text. The text and the stored links must match exactly or the save is refused.

## Chat and history

- **Chat**: messages about the project, this page, or a task. An instruction becomes a task, like a comment.
- **Tasks**: every task with its status, its full timeline, the agent's questions and reports. Reply to a question and the task goes back in the queue. **Retry** a failed or blocked task, **Cancel** any open one.
- Editing a comment is allowed only before work starts. Every edit keeps the earlier version (`build.message_versions`).
- Events are append-only: a database trigger refuses updates and deletes.

## Statuses (honest, enforced by the database)

| Status | Set by | Means |
|---|---|---|
| saved | you | The comment is stored. Notes and questions stay here. |
| queued | you / system | An instruction waiting for the agent (set in the same step as saving). |
| acknowledged | agent | The agent read it and wrote what it understood. Required text. |
| in_progress | agent | Working on it. |
| needs_clarification | agent | Asked you a question (shown in Tasks). Your answer re-queues it. |
| blocked | agent | Can't proceed (a missing decision, a conflict). |
| implemented | agent | Changes made locally. Must list the files. |
| verifying | agent | Running the checks. |
| verified | agent | Every check passed. Must list the checks; one failure refuses it. |
| failed | agent | Didn't work; says why. You can Retry. |
| cancelled | you | Stopped. History kept. |

Only these moves are allowed; anything else is refused (`build.can_move`). "Delivered" is recorded as an event ("Delivered to the agent (attempt 1). Not yet acknowledged."), so the page never shows acknowledged until the agent actually acknowledges.

Verified means checked locally. **Nothing is deployed.** Shipping is still you running `ship.sh` and pressing y.

## Agent delivery

The agent is a Claude session with the Supabase connector. It calls these as `postgres`; the website roles can't call them at all.

| Function | Does |
|---|---|
| `build_agent_checkin(agent, note)` | Records that the agent looked (shown as "Agent last checked in"). |
| `build_agent_claim(agent, lease_minutes)` | Puts expired leases back in the queue (with a recorded reason), then takes the oldest queued task whose dependencies are verified. One task, one agent (row lock with SKIP LOCKED plus a lease). Counts attempts. Returns null when switched off or nothing is ready. |
| `build_agent_context(task)` | The instruction, every tagged element (path, label, stability, routes), versions, the thread, events, and other open tasks touching the same elements (for conflicts). |
| `build_agent_update(agent, task, to, note, detail)` | Moves the status, with the rules above. `detail.question` becomes a message to you; `detail.report` becomes a report message. |

Idempotency: each save carries a client key, so a double press or a retry after a dropped connection saves once.

Runbook for a session:
1. `select build_agent_checkin('claude-session', 'starting');`
2. `select build_agent_claim('claude-session', 60);` Null means nothing to do.
3. `select build_agent_context('<task id>');` Run `python3 tools/build_refs.py <each name>`. A missing name means the component was renamed or removed: move to needs_clarification and ask. Never apply it to a different element.
4. If `related_open` shows another open task on the same element that pulls the other way, move to blocked and say which tasks conflict.
5. Acknowledge with an understanding, work, mark implemented with the files, run the test suites, mark verified with the checks (or failed with why).
6. Hand the change to James for screenshots and approval. He ships.

## The switch (Admin, System, Build Assistant)

Full admins only. Switching off needs a reason, kept in the history.

When off:
- The Build button disappears for everyone, and the script isn't loaded.
- The database refuses every new comment, chat message, edit, reply, retry and claim ("The Build Assistant is switched off").
- Queued tasks wait. Nothing is marked done or deleted.
- A task an agent already holds keeps its status, and its agent can still record what happened, so the history stays true.
- All history stays. Turning it back on resumes where it stopped.
- The marketplace is not affected.

Every switch is recorded (`build.toggles`) and written to All activity, with how many tasks were open.

## Privacy

- Everything lives in the `build` schema, which PostgREST doesn't expose and the website roles can't read. Tested: a signed-in seller calling `build_history` or reading `build.messages` through the API gets an error.
- No marketplace table is changed. The tool only reads who you are (`admins`, `is_admin`).
- Viewing pages while using the tool doesn't count as a car view (admins never record views).
- Comments can quote what's on screen. Don't paste passwords or keys into them.

## Honest limits

1. **No separate development environment.** Saaz has one Supabase project, so the tool runs in production, gated by the checks above. A Supabase branch would cost money and isn't set up.
2. **The agent only works when a Claude session runs.** Nothing processes the queue in between. "Agent last checked in" shows when it last looked. A scheduled run could check it daily; that's your decision.
3. Element names come from the code. A component without a `data-ref` gets an anchored or unstable name, and the agent is told how stable it is.
4. Drafts are per browser. A draft started on a laptop isn't on your phone.
5. Hover isn't available on touch, so phones use tap then Comment. Tested at 390 px with real touch events.

## Tests (19 Oct 2026)

| Suite | Result |
|---|---|
| `db_build_test.py` (access, switch, refs, idempotency, statuses, leases, retries, two agents at once, dependencies, conflicts shown to the agent, versions, append-only, privacy) | 70 passed |
| `browser_build_test.py` at 1280 | 47 passed |
| `browser_build_test.py` at 390 (includes touch) | 51 passed |
| Every other suite, re-run after the change | All pass (see tests/README.md) |

## Claim fix, Part 19 (applied live 19 Oct 2026, after James's approval)
Found while working the first real tasks: a task handed to an agent stays "queued" (with a lease) until the agent acknowledges it, and `build_agent_claim` didn't check that lease, so a second claim handed out the same task again. BA-0001 was delivered 5 times in one go; no other harm, and the history keeps that record. `supabase/marketplace_19_build_claim_fix.sql` hands out a queued task only when it has no lease or its lease ran out. `db_build_test.py` now fails without it and passes with it (71 passed). Checked live after applying: BA-0006 was handed out once, and a second claim straight after got nothing.

## Tasks worked on 19 Oct 2026
| Task | Asked | Done |
|---|---|---|
| BA-0001 | Cars react on hover | Option A: photo lifts and zooms slightly on hover or keyboard focus; text unchanged; still on phones and with reduced motion |
| BA-0002 | Check that comments arrive | Answered; cancelled by James |
| BA-0003, BA-0005 | See every car when viewing the marketplace as admin | Uses admin_listings: every stage, buyer card, stage on the photo, admin line, cards open the admin page, no "Saved only", nothing published |
| BA-0006 | Video behind the hero and latest cars | James's road video turned -90 degrees (portrait on phones), silent, looping, about 0.5 MB per visitor (WebM, MP4 fallback); no section borders; white text over a dark tint; a still frame when motion is off or data saver is on. Files in src/assets/video/ |
| BA-0004 | Saaz-owned car without a logbook | Already allowed via Admin, Saaz cars; pointer added on the sell form for admins |

