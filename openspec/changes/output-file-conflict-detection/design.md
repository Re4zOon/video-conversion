## Context

The CLI currently begins conversion immediately and overwrites any existing output path.
We need a pre-conversion check in the CLI flow to prevent data loss by prompting users when conflicts exist.

## Goals / Non-Goals

**Goals:**
- Detect existing output files before conversion starts.
- Prompt users with overwrite, rename, or cancel options.
- Update help/usage documentation to describe the behavior.

**Non-Goals:**
- Changing conversion logic beyond preflight checks.
- Adding new CLI flags or configuration formats beyond the existing prompt flow.

## Decisions

- Add a preflight check in the CLI conversion command that uses `Path.exists()` on the resolved output path before invoking ffmpeg.
  - **Alternative:** Rely on ffmpeg overwrite flags. Rejected because it does not provide rename/cancel choices.
- Reuse existing prompt/input utilities (if present) to ask for overwrite, rename, or cancel, keeping the prompt synchronous.
  - **Alternative:** Introduce a new dependency for richer prompts. Rejected to keep changes minimal.
- When rename is selected, request a new filename and re-run the conflict check loop until a non-existing path is provided or the user cancels.

## Risks / Trade-offs

- [Risk] Users could enter a new filename that is still invalid or already exists. → Mitigation: revalidate and re-prompt.
- [Risk] Prompt flow could be bypassed in non-interactive contexts. → Mitigation: document expected behavior; keep default cancel on EOF if needed.
