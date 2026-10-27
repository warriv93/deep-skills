# Asana

An Asana **project** maps to the Podium project, its top-level **tasks** to epics, and each task's **subtasks** to that epic's milestones. A single linked task is an epic. Stories stay local: sub-subtasks are not read and nothing below a milestone goes to Asana. Talk to Asana through the `mcp__asana__*` tools; the Podium shows only what you record.

## Fields

`asana` on `project` (a linked project), on an epic (its task) and on a milestone (its subtask): `{gid, url, assignee, fields, completed}`. `url` is the `permalink_url`, `assignee` the assignee's name, `fields` the custom fields that have a value as `[{name, value}]` (`display_value`), `completed` Asana's completion, `keep` true once the user chose to keep building a milestone done in Asana. Write them with `podium set <target> asana=@<file>`.

## Link

On an Asana link in the arguments (`/orchestrate-deep-plans <link>`) or `REQUEST asana [<epic>] note=<link>`.

1. **The gid:** drop the query string; the gid is the segment after `task/` or `project/` (`https://app.asana.com/1/<ws>/project/<p>/task/<t>`). The old form `https://app.asana.com/0/<p>/<t>` → the last number; `/0/<p>/list` is a project.
2. **A project:** `get_project`, then `get_tasks(project=…)` for its open top-level tasks. Ask the user which of them are epics (`AskUserQuestion`, multiSelect; more than four → list them numbered in text and ask). Record the project's `asana` on `project`.
3. **Each epic task** (the chosen tasks, the linked task, or the task for `<epic>`): `get_task` with `opt_fields=name,notes,completed,assignee.name,permalink_url,num_subtasks,custom_fields.name,custom_fields.display_value`. It links to an existing epic already holding its gid, or the `<epic>` of the request, or one whose title is the same ignoring case and punctuation; otherwise it becomes a new epic (`id` a slug, `title` the task name, `summary` the first paragraph of its notes).
4. **Its subtasks:** `get_task` lists only their names, so call `get_task` on each for the fields above. Match each to the epic's milestones:
   - **Obvious:** the same title ignoring case and punctuation, or the subtask names the milestone's id (`M2`, `Milestone 2`) → link it without asking.
   - **Anything else:** ask the user which milestone it is, the likely ones as options plus "a new draft milestone".
   - **No milestone:** a new milestone, `status: "draft"`, `summary` from its notes. A completed subtask becomes a `done` milestone with no branch or PR, as history.
5. Append an `asana` event naming what linked, and tell the user in one line.

Matching questions go to the user, never to an assumption: while unavailable, link the obvious ones, set `needsYou` for the rest and finish on `HUMAN available`.

## Refresh

At every sync, and whenever a linked milestone's `phase` changes, re-read the linked tasks and subtasks and update each `asana`. `podium asana refresh` does all of it over Asana's REST API, and `podium turn` runs it: a line and an `asana` event per change, and `ASK <subtask gid> "<name>" → <candidates>` for a subtask to put to the user as Link step 4 says. It prints `NO_TOKEN` and exits 3 without a personal access token: refresh through the MCP tools as below, and offer the user to store one in the keychain with `security add-generic-password -s podium-asana -a "$USER" -w` (it prompts for the token; `ASANA_TOKEN` overrides it). A milestone's title stays the run's when the subtask is renamed. A new subtask is matched as in Link step 4. A subtask completed while its milestone hasn't landed → record `completed: true` and change nothing else. The Podium asks the user "Done in Asana?" on the milestone, with **Skip it** and **Keep building**, answered as `REQUEST asana-done <milestone> note=<drop|keep>`:

- **drop:** stop the milestone's running stories, set it `dropped` with a note that it was done in Asana, `active: null` if it was active, and append an `asana` event.
- **keep:** set `asana.keep=true`; the question goes away and the subtask stays completed in Asana.

## Write back

One write, made on its own (the user's standing approval for these runs): when a milestone lands (`podium turn` prints `ACT asana-complete <milestone> <gid>`), complete its subtask (`update_tasks` with `{task: <gid>, completed: true}`) and record `asana.completed=true`. Asana stays otherwise untouched: the epic's own task stays open, and the run leaves comments, new tasks and fields to the user.

## Planning

A milestone with `asana` starts its `/deep-plan` grill from its subtask's notes, quoted as the user's input, not as decisions.
