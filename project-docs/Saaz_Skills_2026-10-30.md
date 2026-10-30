# Saaz build skills (30 Oct 2026)

Which skills every Saaz build session uses, and when. A skill only loads in a session if it is saved to James's account (the .skill files were delivered on 30 Oct 2026); this file is the plan either way.

## In use

| Skill | Source | Use it when | Saaz build step |
|---|---|---|---|
| james-working-style | James | Every reply, file and plan | Always |
| karpathy-guidelines | multica-ai/andrej-karpathy-skills (MIT) | Any code change: say assumptions, smallest change, touch only what the request needs, set a check and loop until it passes | Before and during every task |
| systematic-debugging | obra/superpowers (MIT) | Any failing test, bug report or Build Assistant task that says something is broken. Root cause first, one fix at a time, stop after 3 failed fixes and question the design | When a check fails or a bug is reported |
| verification-before-completion | obra/superpowers (MIT) | Before saying verified, done, fixed or passing; before `build_agent_update(... 'verified' ...)`; before telling James a zip is ready | Last step of every task |
| blast-radius | ahmedbenaw/pstack (MIT) | Before handing James a zip: what the change could break beyond the diff (global CSS, shared card, database functions), with the one safety fact proven by running code | Before every zip |
| security-audit | cloudflare/security-audit-skill (MIT) | Guidance mode: any change to sign-in, admin access (authenticator), row rules, database functions, storage, edge functions, or who can use the Build Assistant (BA-0007). Full audit mode only when James asks, and once before Saaz starts trading | Before any supabase/*.sql part is written for approval; full audit before launch |
| audit-suite (a11y, UX, design, frontend, performance, production readiness, repo maintainer) | already installed | UI and interaction changes | With every UI change |
| skill-creator | already installed | Making or changing skills | When asked |

Rules that still win over any skill: never push or deploy, no production database change without James's approval in a live chat, no secrets, nothing about Lemax–Saaz in public. Where a skill says commit, open a PR or create branches, Saaz instead hands James a zip.

## Dropped, and why

| Skill(s) | Why not |
|---|---|
| ponytail (all 6) | Smallest-change and short-reply rules duplicate karpathy-guidelines and james-working-style; its review and audit duplicate audit-suite and security-audit; gain and help are about the tool itself |
| pstack principles (22) | Covered by karpathy-guidelines, systematic-debugging and verification-before-completion (prove-it-works, fix-root-causes, laziness, subtract-before-add) |
| pstack arena, swarm, interrogate, setup-pstack | Need several model families configured and cost many agent runs; design exploration already uses the rendered 100-version matrix James asked for |
| pstack Benny automations, recall, reflect, automate-me, poteto-mode, bro, teach, how, why, no-comments, make-bot-ui | Slack and tracker bots, personal modes, or not relevant to a static site with Supabase |
| pstack tdd, typescript-best-practices | Saaz tests are browser and database checks, and Saaz has no TypeScript |
| pstack technical-writing, unslop | james-working-style already sets the writing rules |
| pstack create/maintain-verification-skill | Saaz already has its test suites and tests/README.md |
| superpowers using-superpowers, brainstorming | Force a skill check or a design dialogue before every reply; Saaz already works sample-first with James's approval |
| superpowers writing-plans, executing-plans, subagent-driven-development, using-git-worktrees, finishing-a-development-branch | Built around commits, branches and PRs; Saaz ships by zip and ship.sh |
| superpowers test-driven-development, requesting/receiving-code-review, dispatching-parallel-agents, writing-skills, diagnosing-superpowers | Covered by karpathy-guidelines, audit-suite, skill-creator, or built-in tools |
| ui-ux-pro-max (all 7) | Logo, banner and brand generation call paid image services; ui-styling is shadcn and Tailwind (Saaz is plain CSS with tokens); design-system duplicates tokens.css and the layout system; its style catalogue pushes trend looks, against the approved art direction (project-docs/Saaz_ArtDirection_2026-10-29.md); its checks are covered by audit-suite |
