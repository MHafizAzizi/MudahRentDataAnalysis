# Claude Instructions — Mudah Rent Analysis

## Start of Every Session

Read `context.md` before doing anything else. It is the single source of truth for:
- What this project does
- What was decided and why
- What changed in the last session
- What tasks are still pending

Do not ask the user to re-explain the project. Do not rely on git log alone. Read `context.md` first.

## End of Every Session

Update `context.md` before closing:
1. Replace the **What Changed** section with a dated summary of this session.
2. Update **Pending Tasks** — mark completed items done, add newly discovered ones.
3. Leave everything else intact unless a decision was reversed.

Do not skip this step. The whole point of `context.md` is that the next session starts with full context.
