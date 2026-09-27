# AGENT BUS

This directory is the handoff point for any coding agent that continues development on Living VN.

Read these files in order:

1. `STATE.json`
2. `QUEUE.jsonl`
3. root `DESIGN_NOTES.md`
4. root `README.md`

## Rules for the continuing agent

- Do not wait for user confirmation when the queue already defines the next safe task.
- Preserve Ren'Py 8.3.7 compatibility unless the queue explicitly changes the platform baseline.
- Prefer standard-library or already-available Ren'Py APIs over new dependencies.
- Keep the LLM optional. The game must still boot and play a deterministic fallback scene when the AI endpoint fails.
- Never give the LLM unrestricted filesystem or process execution.
- Keep tool commands schema-validated and allowlisted.
- Update `STATE.json` after each completed task.
- Add new tasks to `QUEUE.jsonl` instead of deleting unfinished work.
- Run `tools/validate_project.py` after code changes.
- Never silently replace user assets.

## Agent completion contract

At the end of a development pass, write:

- what changed
- what was tested
- what still fails
- the next 3 concrete tasks

into `STATE.json`.
