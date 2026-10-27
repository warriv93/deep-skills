# Phase R, 0 & 0.5 — Recon, Grill, UI Mock

## Phase R — Recon

The repo answers first; the user answers only what the repo cannot.

1. **Read the ground:** `.deep-plan/project.md` (present when `/deep-app-plan` handed this milestone over — its Platform and contract blocks are settled), `CLAUDE.md`, README, `CONTEXT.md`, ADRs, package manifests, layout, test setup. Fan the search out to a cheap `Explore` subagent and take back conclusions.
2. **Write `.deep-plan/recon-note.md`** (≤1 page): stack and versions, module map, **reuse list** (existing utilities and services the feature must build on), conventions, danger zones. Greenfield → one line: "greenfield — no prior art".
3. **Size the work.** Too big for one session → run `/wayfinder` to chart it into tickets and stop there; under `/orchestrate-deep-plans` (`.deep-plan/podium/podium.json` exists), stop and report `TOO BIG <milestone>: <why>` in one line instead, for the orchestrator to re-cut. One buildable chunk → continue.
4. Checkpoint.

## Phase 0 — Grill until the spec is unambiguous

1. Restate the request and the objective as you understand it.
2. **Confirm the platform in one line** — repo host, hosting target, DB, auth — for a yes/no.
3. **Grill in proportion to scope** through `AskUserQuestion`, skipping everything the recon note already answers:
   - **Small (1–3 files):** 1–2 targeted questions, or proposed defaults to confirm.
   - **Medium (3–10 files):** 3–5 questions covering the main flow and edge cases.
   - **Large / cross-cutting:** full `/grill-with-docs` (`/grilling` + `/domain-modeling`).

   **Cross-milestone questions**, under `/orchestrate-deep-plans`: a question whose answer shapes other milestones of the epic is the orchestrator's, not this grill's → report `OPEN DECISION <question>: affects <milestones>` in one line and stop until it returns the outcome.

   **UI questions** (layout, placement, hierarchy, visual treatment) wait for the mock: list them under "Open UI questions" in the Spec Brief, and Phase 0.5 answers them there.

   While the user answers a round, run a background subagent on the work off the critical path: deepen `recon-note.md` where the questions touch it, and draft `.deep-plan/architecture.draft.md` for the modules the settled answers already fix, listing each assumption.
4. Resolve factual unknowns with `/research` on primary sources.
5. **Write `.deep-plan/spec-brief.md`:** objectives, features, constraints, non-goals, resolved decisions, open UI questions, success criteria. End it with an "Assumptions" section: a numbered list of what the brief assumes that the user never said.
6. **Gate:** put the Assumptions list to the user first, each to confirm or correct; then the user explicitly signs off the Spec Brief. Then checkpoint.

## Phase 0.5 — Mock the UI (frontend work only)

No UI surface → one line, "no UI surface — skipping mock", and go to Phase 1.

1. **Build a throwaway mock** of the P1 flows with `/prototype` + `frontend-design` (+ `dataviz` for charts), Apple-style: fake data; P1 screens plus empty, loading, error and mobile states. Write it to `.deep-plan/mock/index.html` and iterate with targeted edits.
2. **Build the open UI questions in as live alternatives:** every open UI question in the Spec Brief, and every UI choice that comes up while mocking, gets a control in a floating Alternatives panel (segmented control, slider or toggle, recommended choice marked) that switches the mock between variants in place, plus a Copy choices button.
3. **Serve it:** `python3 -m http.server 8766 --bind 127.0.0.1 -d .deep-plan` in the background (an orchestrated run's Podium server already serves `.deep-plan/`), then post `<url>/mock/` in your reply with a sentence on what it shows: the clickable mock, and the Alternatives panel that switches each open UI question between its variants.
4. **Walk it screen by screen** with the user: hierarchy, flow, naming, each alternative; cut non-goals. Iterate on the same file until the user signs off.
5. **Fold the outcome back:** each alternative's chosen variant becomes a decision in `spec-brief.md`; amend `CONTEXT.md` and ADRs; record `.deep-plan/mock/` in `spec-brief.md` as the visual reference.
6. **Gate:** the user signs off the mock. Then checkpoint.

Grill and mock context is disposable. After the last sign-off of this file, ask the user to run `/clear` and re-invoke `/deep-plan`; Phase 1 starts from the ledger, `recon-note.md` and `spec-brief.md`.
