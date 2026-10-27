# Lenses

Each lens: what it looks for, when it runs, how, and its done-when. "Changed" means in the diff against the base.

## Review lenses (static)

### Defects
- **Runs:** always.
- **How:** a strong subagent runs the Standards axis of the dual-axis `code-review` skill (`~/.claude/skills/code-review/SKILL.md`) with the review pack, plus a hunt for bugs: trace each changed branch, boundary and error path to a concrete failing input. Add `architecture.md`'s seams to its prompt, so a producer–consumer mismatch is a row. A bug fix: its test goes red with the fix reverted in a scratch worktree and green with it back; no test → `Should fix`.
- **Done when:** every changed file has been read and its rows are pooled.

### Spec
- **Runs:** a spec or acceptance criteria exist.
- **How:** a strong subagent runs the Spec axis of `code-review` with the spec, the seams and the review pack: spec items missing, and scope creep beyond them.
- **Done when:** every acceptance criterion is marked met, missing or partly met, with file:line.

### Design
The strategic-programming lens: does the change leave the code simpler to change next time, or did it buy speed now with complexity later?
- **Runs:** the diff adds a module, a public interface, an event or an endpoint, or touches more than a handful of files.
- **How:** a strong subagent reads `~/.claude/skills/codebase-design/SKILL.md` and the changed files, and looks for complexity the change adds: shallow modules whose interface is as wide as their body, information leaking across a seam (two modules knowing one format or rule), pass-through layers, special cases bolted on where a general one fits, a change that needed edits in many places to do one thing, and names that hide what a thing is.
- **Bar:** `Should fix` at most, each row naming the deeper shape it should take. A design problem that breaks a seam in `architecture.md` is a Defects row.
- **Done when:** every new or widened interface in the diff has been judged deep enough or has a row.

### Security
- **Runs:** always.
- **How:** `/security-review` as a cheap subagent over the review pack.
- **Bar:** Critical → `Blocker`; High → `Should fix`.
- **Done when:** every changed endpoint, query and input path has been checked or has a row.

## Verify lenses (running)

### Contract
- **Runs:** always.
- **How:** with `.deep-plan/contract.cmds`, one `gates.sh` call (deep-plan's SKILL.md, Contract runs), with its `coverage` and e2e gates when it has them. Without one, the checks the repo's CI runs, read from its workflow files.
- **Bar:** a red gate the change causes → `Blocker`, its log tail as the failure.
- **Done when:** the contract is green, or red with its failing gate named.

### Journeys
- **Runs:** P1 journeys exist, or the diff changes UI or an endpoint.
- **How:** run the app (`/run`) and drive every P1 journey with headless Playwright, logging in as the repo's docs or seed data say. UI work: screenshot the built screens and have a cheap subagent compare them with the mock.
- **Bar:** a P1 journey that fails → `Blocker`; a screen off the mock → `Should fix`.
- **Done when:** every P1 journey is passed or failed at a named step.

### Accessibility
- **Runs:** the diff changes web UI (templates, components, styles).
- **How:**
  1. **Automated:** `node ~/.claude/skills/deep-qa/scripts/a11y.mjs [--storage <state>] <url>...` on every screen the change touches (WCAG 2.1 A/AA through axe-core; the header documents its lines). Behind a login, save Playwright's storage state after logging in and pass it. Run the same URLs on the base too when the screen exists there, so only violations the change adds count.
  2. **Keyboard:** drive each changed journey by keyboard alone: every control reachable by Tab in reading order, focus visible on each, Enter and Space act, Escape closes dialogs, no focus trap.
  3. **Reflow:** each changed screen at 320 px wide and at 200 % zoom loses no content or function.
- **Bar:** a new `critical` or `serious` violation, or a control unreachable by keyboard → `Blocker`; `moderate` → `Should fix`; `minor` → `Nit`. Violations also on the base go under Pre-existing.
- **Native apps:** run the repo's own accessibility checks when it has them (Android Lint's accessibility category, an iOS `performAccessibilityAudit` UI test); else `not run: no accessibility check in this repo`.
- **Done when:** every changed screen has an `A11Y` line, a keyboard pass and a reflow pass.

### Performance
- **Runs:** the diff adds or changes a database query, a migration on a large table, a loop over remote calls, or a web page's bundle.
- **How:** queries: a subagent checks each against the schema for a usable index and for N+1 access, reading the migrations for the indexes. Migrations: does it lock a large table without an online strategy. Web pages: `/web-perf` on each changed page, base vs head.
- **Bar:** an unindexed query on a large table, N+1 over a request's main list, or a blocking migration on a hot table → `Blocker`; a Lighthouse performance score down more than 10 → `Should fix`.
- **Done when:** every added query, migration and changed page has been judged or has a row.
