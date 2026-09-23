# Voice-agent template evals (promptfoo)

Pre-publish QA for the voice-agent templates. 9 scripted probes (3 per
template) hit the chat endpoint and assert the reply behaves like the
template should. **All 9 must pass before a template version is published.**

## What is here

| File | Purpose |
|---|---|
| `promptfoo.yaml` | Eval config: single `http` provider (`POST /api/agents/chat`), `{{template_id}}` + `{{prompt}}` vars per test, `transformResponse: json.reply` so assertions run on the reply text, loads the 3 test files via `file://` |
| `tests-plumbing.yaml` | `voice-plumbing-uk`: burst-pipe emergency + lead capture, boiler-service price (£), out-of-area London caller |
| `tests-hvac.yaml` | `voice-hvac-uk`: annual-service booking + lead capture, warranty question, F-Gas/certificate question |
| `tests-electrician.yaml` | `voice-electrician-uk`: EICR landlord booking + lead capture, consumer-unit price (£), sparking-socket emergency |
| `README.md` | This file |

Each test's `description` holds the full 2–3 turn conversation script
(demo_script style). The `prompt` var is the decisive caller turn: contact
details are compressed into a single message because the endpoint is
stateless per request (see "Multi-turn" below).

## Install

Pick one (Node available in this repo):

```powershell
npm i -g promptfoo        # global install, then `promptfoo ...` directly
# OR zero-install per run (downloads on first use):
npx --yes promptfoo@latest --version
```

## Run

1. Start the backend and seed the three templates
   (`voice-plumbing-uk`, `voice-hvac-uk`, `voice-electrician-uk`).
2. From this directory:

```powershell
Set-Location D:\Voice\evals
promptfoo validate -c promptfoo.yaml   # schema check, no backend needed
promptfoo eval -c promptfoo.yaml       # full eval, needs backend + seeds
```

`npx` variant (no global install): prefix both commands with
`npx --yes promptfoo@latest`, e.g.
`npx --yes promptfoo@latest eval -c promptfoo.yaml`.

## Publish gate rule

- **All 9 tests pass → template version may be published.**
- Any failure blocks publish. Fix the template (or the test, if the test
  is wrong), re-run the full eval, then publish.
- Keep this pack in sync with template behaviour: if a template's pricing,
  coverage area, or booking flow changes, update the affected test first.

## Assertion design notes

- Primary assertions are `contains` / `icontains` on the reply text —
  robust against rewording (e.g. `certificat` matches both "certificate"
  and "certification"; `safe` matches "safe"/"safety").
- Exactly **one `javascript` assertion per template** (the `-a` lead-capture
  tests). Because `transformResponse: json.reply` exposes only the reply
  string, lead capture is asserted as "booking reference quoted in reply"
  (`reference`, `bk-…`, or `booked`). If you ever need the raw field
  (`output.lead_reference != null`), drop `transformResponse` and use
  per-assertion `transform: output.reply` instead.
- `threshold: 0.5` on a test means OR-semantics: at least half the
  assertions must pass (1 of 2, or 2 of 3). Used where the spec allows
  alternatives (e.g. "asks postcode OR returns reference").
- If the endpoint is down or a template id is unseeded, requests error and
  the affected tests fail — that is intentional (fail closed).

## Multi-turn (future)

True session-chained turns need `session_id` carried across requests.
promptfoo supports this via a `sessionParser` + `{{sessionId}}` template
once the backend's session behaviour is confirmed. Until then, each
conversation is probed as a single decisive turn with the full script in
`description`. If the passthrough prompt (`prompts: ["{{prompt}}"]`) ever
mis-renders, rename the var to `message` in the test files and use
`prompts: ["{{message}}"]` (provider body stays `{{prompt}}` = rendered
prompt).

## CI note

Not wired yet. Later: add a GitHub Actions job that starts the backend
(or hits a preview URL), seeds templates, installs promptfoo
(`npm i -g promptfoo` or `npx`), runs `promptfoo eval -c promptfoo.yaml`
from `D:\Voice\evals`, and fails the workflow on any test failure so a
template version cannot publish red.

## Status at authoring time (2026-09-23)

- `GET /api/health` → ok; `POST /api/agents/chat` → **404** (parallel
  backend build had not landed). So: config `validate`d, live eval
  **not run** — re-run `promptfoo eval` once the endpoint exists.
