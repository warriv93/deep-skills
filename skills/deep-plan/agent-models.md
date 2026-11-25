<!-- shared:start — this block is identical in ai-tools simon/subagent-protocol/agent-models.md and deep-skills skills/deep-plan/agent-models.md; diff the two before changing either -->
# Agent models

Every spawn takes its model and effort from its job's row below: pass Model as the Agent tool's `model` and Effort as its `effort`; Paseo launches take the model only. `podium` reads the Model column of the `story`, `story-critical`, `plan`, `gate` and `retro` rows for its stories and hand-offs, so those keys stay. To tune routing, edit a row here and nowhere else.

## Routing

| Key | Job | Model | Effort | Escalate | Why |
| --- | --- | --- | --- | --- | --- |
| `recon` | recon search, inventory, finding where code lives | `haiku` | low | `sonnet` when the answer needs a judgement (which design, why it breaks) | Reading and listing; Haiku 5.5 costs 1/40 of Opus 5.5, and the caller checks every lead it acts on |
| `mechanical` | mechanical edits and checks: a decided rename, formatting, applying a given diff, counts, link checks | `haiku` | low | `sonnet` when the edit needs reasoning about behaviour, or its check fails once | The decision is made; the agent only carries it out |
| `screenshot` | screenshot checks: does each PNG show what its brief says, or match its mock | `haiku` | low | `sonnet` when a line comes back unsure, or a verdict looks wrong on a retake | One verdict per file against a stated expectation |
| `draft` | background drafts, report drafting, domain stories | `sonnet` | medium | `opus` when the draft must take positions the caller would rewrite | The caller edits every draft before it counts |
| `coverage` | coverage check: map each decision and criterion to the task that implements it | `sonnet` | medium | `opus` when a gap's verdict is disputed | Whether a task covers a criterion takes more than matching words |
| `research` | research against primary sources: docs, API facts, prior art | `sonnet` | high | `opus` when sources conflict; `fable` when they still can't be reconciled | Wide reading with citations; the caller judges the conclusion |
| `security` | security pass (`/security-review`) | `sonnet` | high | `opus` when the diff touches auth, personal data or how money moves | A missed hole costs more than the pass, so it gets a model that follows attack paths |
| `story` | story building, routine | `sonnet` | high | same model after an environment failure; `opus` when an attempt fails on its own code | 1 retry in 206 Sonnet stories (Baseline) |
| `story-critical` | story building, correctness-critical: money, dates and time zones, concurrency, auth, migrations, core algorithms | `opus` | high | `fable` after two attempts fail on their own code | Errors here pass tests and reach users |
| `plan` | grill, spec and architecture: the planning hand-off and planning ahead | `opus` | high | `fable` when requirements conflict or the spec has many interdependent parts | Every story inherits its decisions |
| `review` | review and QA lenses, code-review gates, the pre-PR reviewer | `opus` | high | `fable` for a Blocker still disputed after one fix round | Fresh-context judgement over a whole diff |
| `gate` | quality-gate hand-off: gate, verify, fix and land | `opus` | high | `fable` when the same fix fails twice | Runs the review lenses and fixes what they find |
| `diagnose` | `/diagnosing-bugs` | `opus` | high | `fable` when the same bug survives two fix attempts | Hard bugs need hypotheses tested, not patterns matched |
| `retro` | retro: friction in a landed milestone's events becomes skill findings | `opus` | medium | `high` effort when the friction spans several milestones | Findings change skills; the input is a short event list |

## Terms

- *cheap subagent*: the `recon` row, `haiku` at low effort. Ask it for a direct answer: a bulk read can spend more on thinking than on its reply.
- *strong subagent*: the `review` row, `opus` at high effort.

## Escalate

- **Environment first:** a failure the environment caused (a full disk, a formatter, a flaky dependency, a false premise in the plan) retries on the same model.
- **One step up:** an attempt that fails on its own reasoning, or a reply that misses what its brief asked, moves one step up `haiku` → `sonnet` → `opus` → `fable`. For a story, `podium set <milestone>/<id> model=<model>` before `podium launch … --retry`.
- **Fable by escalation only:** no row starts on `fable`. Claude Fable 5.2 costs twice Opus 5.5 and runs longer turns, and no failure in the Baseline was the model's. Reach it from a row's Escalate column or a sign in CLAUDE.md's Model escalation. Paseo launches `fable` as the newest Fable it lists, which can trail the newest release.

## Baseline

Prices per million input/output tokens (`claude-api`, 2026-11): Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20, Fable 5.2 $8/$40. Opus 5.5 defaults to `medium` effort and Sonnet 5.5 to `high`; `high` is the floor for intelligence-sensitive work, and `low` suits simple subagents.

Podium runs to 2026-11 (in-app-message-experience, stagehand, three smaller): 5 of 379 stories took a second attempt, 4 of 173 on Opus and 1 of 206 on Sonnet. Each logged cause was outside the model: a false premise in the plan, checks that ran on an uncommitted tree, a full Docker disk, a story that needed a later story's code. Every quality gate passed, with 2–51 findings each. Before moving a row, re-measure: each story's `model` and `attempts` in `podium.json`, and the `retry` events' reasons in `events.jsonl`.
<!-- shared:end -->
