# Copilot Instructions

## OpenSpec Workflow

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for specification-driven development. The OpenSpec skills are installed in `.github/skills/` and provide a structured workflow for all changes.

**Before implementing any feature, fix, or modification**, you MUST follow the OpenSpec workflow:

You can follow one of two workflows:

**Option A — Step-by-step workflow**

1. **Start a change** — Invoke the `openspec-new-change` skill (or `/opsx:new` in IDE) to create a new change under `openspec/changes/`.
2. **Continue planning** — Invoke the `openspec-continue-change` skill (or `/opsx:continue` in IDE) to iteratively create and refine planning artifacts (proposal, specs, design, tasks) for that change.
3. **Implement** — Invoke the `openspec-apply-change` skill (or `/opsx:apply` in IDE) to implement the tasks.
4. **Archive** — Invoke the `openspec-archive-change` skill (or `/opsx:archive` in IDE) to archive the completed change and merge specs.

**Option B — Fast-forward workflow**

1. **Fast-forward a change** — Invoke the `openspec-ff-change` skill (or `/opsx:ff` in IDE) to create a new change and generate all planning artifacts (proposal, specs, design, tasks) in one step. Do **not** run `openspec-new-change` before this.
2. **Implement** — Invoke the `openspec-apply-change` skill (or `/opsx:apply` in IDE) to implement the tasks.
3. **Archive** — Invoke the `openspec-archive-change` skill (or `/opsx:archive` in IDE) to archive the completed change and merge specs.
Always check `openspec/changes/` for any active changes before starting new work. If an existing change is in progress, use the `openspec-continue-change` skill instead of creating a new one.

Always check `openspec/specs/` for existing specifications that may be affected by the change.
