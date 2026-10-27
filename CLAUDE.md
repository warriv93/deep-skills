# deep-skills

## Writing or editing a skill

Every change to a file under `skills/` — a new skill, a phase file, a description — follows **writing-for-agents**. Load it before the first edit:

- installed → invoke the `writing-for-agents` skill;
- otherwise → read it from GitHub: `SKILL.md` and `SKILL-MECHANICS.md` under `skills/productivity/writing-for-agents` in `mattpocock/skills` (`gh api repos/mattpocock/skills/contents/<path> --jq .content | base64 -d`).

Done when every changed line has passed its pruning checks (single source of truth, relevance, no-ops) and every step ends on a checkable completion criterion.

## Repo conventions

- A skill is a folder: `skills/<name>/SKILL.md` (frontmatter with `name`, `description`, `argument-hint`) plus sibling `phase-*.md` files reached through relative links. `install.sh` symlinks each folder into `~/.claude/skills/`.
- A skill's name carries `deep` (`deep-plan`, `deep-app-plan`, `orchestrate-deep-plans`, `create-deep-pr`), so it never shares a name with the author's team skills in `~/gitrepos/ai-tools/simon`; `discuss` is the one exception: an identical copy lives in `~/gitrepos/ai-tools/simon/discuss`, so change both together.
- `SKILL.md` holds what every run needs; material only one phase needs goes in that phase's file.
- Shared rules live once in `SKILL.md` under a leading word (_ledger_, _checkpoint_, _contract_, _subagent protocol_); phase files use the word and leave the definition where it is.
- `/deep-plan`, `/deep-app-plan` and `/orchestrate-deep-plans` share `.deep-plan/`: `project.md` belongs to `/deep-app-plan`; `podium/` and `domain-stories/` to `/orchestrate-deep-plans`; every other file to `/deep-plan`.
- The agent can't run slash commands like `/clear` or `/compact`; a context reset is a request to the user.
- Skills also run in Antigravity. Keep writing them in Claude Code terms; when a skill starts using a new tool, model or command, add its row to `gemini/claude-tool-map/SKILL.md`, the one place the translation lives.
- After a skill change, update the skill table and Dependencies section in `README.md`.
