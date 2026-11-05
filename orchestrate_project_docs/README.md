# Ghost Data Still Exists — Project Documentation Pack

This pack provides a starting documentation baseline for the HackerRank Orchestrate October 2026 challenge.

## Layout

- `docs/API.md` — runtime and output contract
- `docs/ARCHITECTURE.md` — proposed processing pipeline
- `docs/DATA_MODEL.md` — normalized internal representations
- `docs/DECISIONS.md` — key engineering decisions
- `docs/PRD.md` — product requirements and acceptance criteria
- `AGENTS.md.addendum` — project-specific coding-agent rules to merge into the repository's existing `AGENTS.md`
- `project-notes/PROJECT_STATE.md` — current known state and blockers
- `project-notes/TASKS.md` — implementation/evaluation checklist
- `project-notes/WORKLOG.md` — append-only work history

## Important

This is a documentation baseline, not a completed agent implementation. The only local dataset file inspected when preparing it was `deletion_requests.csv`; the complete evidence corpus and local starter code still need inspection. Do not treat planned components as implemented or test results as passed.

**Do not replace the repository's existing `AGENTS.md` with the addendum.** Merge the addendum into the existing file while preserving the official transcript and submission instructions.

Project notes do not update themselves just because they exist. The coding agent must follow the addendum and edit the state, task list and worklog after meaningful prompts, code changes and tests. This is an agent workflow convention, not a background file watcher.
