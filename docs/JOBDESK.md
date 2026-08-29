# JOBDESK — Ownership and Boundaries

Three people, three layers, one repo. This document exists because two incidents
were caused by unclear boundaries: a cross-cutting route rename that broke the
frontend for a day, and a commit that touched files outside its brief.

## Roles

| Person | GitHub | Commit identity | Owns |
|---|---|---|---|
| **GreyArch** | `axzss` | `axzss <banksadits01122005@gmail.com>` | Frontend — `frontend/**` |
| **Zacky Muhammad Dinata** | `zmdinata` | `zmdiata <zmdinata@gmail.com>` | AI engineering + hedge-fund council — `agent/**`, `docs/**` |
| **Aji Nur Aji** | `AjiNurAji` | `AjiNurAji <ajinuraji090306@gmail.com>` | Backend — `backend/**`, `specials/**` |

Set your identity per-repo, not globally:

```bash
git config user.name  <name>
git config user.email <email>
```

## Scope boundaries

Each role has a directory it owns and directories it must not edit without
asking. This is enforced socially, not by hooks.

### Frontend (`axzss`)
**Owns:** `frontend/**` — `app/`, `lib/`, `next.config.js`, `tailwind.config.js`,
`package.json`.

**Must not edit:** `agent/**`, `backend/**`.

**Verify before pushing:**
```bash
cd frontend
npx tsc -p tsconfig.json --noEmit   # must be clean
npm run build                       # must compile all pages
```
Plus: load every page and confirm no console errors. `curl` returning 200 is
not sufficient — a page can return 200 while rendering an error boundary.

### AI engineering + council (`zmdiata`)
**Owns:** `agent/**` (strategies, decision engine, exit manager, portfolio
analyst, council, config), `docs/**`.

**Must not edit:** `frontend/**`, `backend/**`.

**Verify before pushing:**
```bash
pytest agent/tests backend/tests -q   # both suites, not just agent
```
Run the backend suite too: `agent/config.py` and the council modules are imported
by backend routes, so an agent-layer change can break backend tests.

**Extra rule:** if you modify an existing test — even a fixture — say so
explicitly in the commit message and in your report. A silently altered test
assertion is indistinguishable from weakening the suite.

### Backend (`AjiNurAji`)
**Owns:** `backend/**` — `app/`, routes, `alpaca_client.py`, `responses.py`,
`backend/tests/`, `specials/BACKEND_FRONTEND_API.md`.

**Must not edit:** `frontend/**`, `agent/**`.

**Verify before pushing:**
```bash
pytest backend/tests agent/tests -q
```

**Extra rule:** any change to a route path, response field name, or field type is
a **breaking change for the frontend**. Announce it and update
`specials/BACKEND_FRONTEND_API.md` in the same commit. The `/api` prefix
standardisation was correct but silently 404'd every frontend call for a day
because this rule did not exist yet.

## Shared files — coordinate first

| File | Why it is shared |
|---|---|
| `.gitignore` | Everyone adds entries |
| `docs/MEMORY.md` | The build log spans all layers |
| `docs/KNOWN-ISSUES.md` | Defects cross boundaries |
| `README.md` | Project-level |

For these, pull immediately before editing and push immediately after.

## Contract rules between layers

**Backend → Frontend.** The API contract is the *route source code*, not a
document. When writing a typed client, read `backend/app/routes/*.py` and
confirm field names and value ranges against a live response:

```bash
curl -s http://localhost:8000/api/council/assess | python3 -m json.tool | head -40
```

`specials/BACKEND_FRONTEND_API.md` is documentation and can drift — it currently
does, in three places (see `KNOWN-ISSUES.md`). Trust it only after verifying.

**Council → AI Engineer.** The council communicates policy through the HANDOFF
section of `docs/council_report.md`, parsed by `agent/council/handoff.py`. This
is markdown parsed with regex: **if you change the report format, the policy
silently degrades to defaults**. Run
`pytest agent/tests/test_council_handoff.py` after touching either side.

## Git rules

- Never push straight to `master` if the change is large or cross-cutting —
  open a PR (Aji has been doing this correctly: PRs #1–#5).
- Never force-push `master` without telling the other two. It has been done once,
  deliberately, to remove a reverted batch.
- Never commit `.env`, credentials, or API keys. `.gitignore` covers `.env`,
  `docs/.cache/`, and the copyrighted book files. Verify before pushing:
  ```bash
  grep -rInE "PK[A-Z0-9]{15,}" . --exclude-dir=.git --exclude-dir=node_modules
  ```
- **Read your own diff before committing.** `git diff --stat` then
  `git diff <file>` for anything you did not consciously edit. Every file in
  the diff must be one you meant to change.

## Delegation rules

When dispatching a subagent:

1. **Scope-lock the brief** — name the directories it may touch and the ones it
   must not.
2. **A subagent's report is a claim, not evidence.** Re-run the tests and the
   build yourself before committing its work.
3. **Read the full diff.** Subagents change files outside their brief. This has
   already caused one reverted commit.
4. **Report every changed file to the user**, including ones that look trivial.

## Current status by layer

| Layer | Status |
|---|---|
| Backend | Complete — 11 routes, zero TODOs, chaos coverage |
| AI engineering | Core complete; three robustness items pending (see `ROADMAP.md`) |
| Frontend | Endpoints wired; logo/identity and charts not started; mockup components still present |
