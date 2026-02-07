## Why

The repository has no linting, formatting, or static analysis tooling configured. Without these guardrails, code quality depends entirely on manual review, making it easy for style inconsistencies, common bugs, and security anti-patterns to slip through. Adding standard Python best-practice tooling will catch issues early and establish a consistent, maintainable codebase.

## What Changes

- Add a Python linter and formatter configuration (Ruff) to enforce code style and catch common errors.
- Add a `pyproject.toml` to centralize project metadata, tool configuration, and dependency management.
- Add a GitHub Actions CI workflow to run linting and tests on every push and pull request.
- Add a pre-commit configuration to catch issues before code reaches the repository.

## Capabilities

### New Capabilities
- `linting`: Ruff-based linting and formatting configuration for consistent Python code style and error detection.
- `ci-pipeline`: GitHub Actions workflow that runs linting, type checking, and tests automatically.
- `project-config`: Centralized project configuration via `pyproject.toml` for metadata, dependencies, and tool settings.

### Modified Capabilities
<!-- No existing specs to modify — the specs directory is empty. -->

## Impact

- New files: `pyproject.toml`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.ruff.toml` (or config inside `pyproject.toml`)
- Development dependencies: `ruff`, `pre-commit`, `pytest` added to dev dependencies
- Existing code: `video.py` may need minor adjustments to satisfy linter rules (unused imports, naming conventions, etc.)
- CI: New GitHub Actions workflow will gate merges on passing lint and test checks
