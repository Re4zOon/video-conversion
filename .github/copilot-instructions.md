# Copilot Instructions

## OpenSpec Workflow

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for specification-driven development. The OpenSpec skills are installed in `.github/skills/` and provide a structured workflow for all changes.

**Before implementing any feature, fix, or modification**, you MUST follow the OpenSpec workflow:

1. **Start a change** — Invoke the `openspec-new-change` skill (or `/opsx:new` in IDE) to create a new change under `openspec/changes/`.
2. **Create planning artifacts** — Invoke the `openspec-ff-change` skill (or `/opsx:ff` in IDE) to generate all planning artifacts (proposal, specs, design, tasks).
3. **Implement** — Invoke the `openspec-apply-change` skill (or `/opsx:apply` in IDE) to implement the tasks.
4. **Archive** — Invoke the `openspec-archive-change` skill (or `/opsx:archive` in IDE) to archive the completed change and merge specs.

Always check `openspec/changes/` for any active changes before starting new work. If an existing change is in progress, use the `openspec-continue-change` skill instead of creating a new one.

Always check `openspec/specs/` for existing specifications that may be affected by the change.
