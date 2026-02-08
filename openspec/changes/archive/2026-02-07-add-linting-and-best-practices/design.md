## Context

The `video-conversion` repository is a single-module Python CLI tool (`video.py`) with one test file (`test_video_errors.py`). It has `requirements.txt` and `requirements-dev.txt` but no `pyproject.toml`, no linter configuration, no CI pipeline, and no pre-commit hooks. All quality assurance is manual.

## Goals / Non-Goals

**Goals:**
- Establish automated linting and formatting via Ruff to enforce consistent code style.
- Add a `pyproject.toml` to centralize project metadata and tool configuration.
- Create a GitHub Actions CI workflow that runs linting and tests on push and pull requests.
- Add a `.pre-commit-config.yaml` so contributors can catch issues locally before pushing.

**Non-Goals:**
- Rewriting or refactoring `video.py` beyond what is needed to satisfy linter rules.
- Adding type annotations or mypy type checking (future work).
- Publishing the package to PyPI.
- Adding code coverage enforcement.

## Decisions

### 1. Ruff as linter and formatter
**Choice**: Use Ruff for both linting and formatting.
**Rationale**: Ruff is a single tool that replaces flake8, isort, black, and several other linters. It is extremely fast and configured via `pyproject.toml`. Alternatives considered: flake8 + black + isort (three tools to install and configure separately); pylint (slower, more opinionated, heavier setup).

### 2. Configuration in `pyproject.toml`
**Choice**: Put Ruff and pytest configuration inside `pyproject.toml` rather than separate config files.
**Rationale**: Reduces the number of config files in the repository root. `pyproject.toml` is the modern standard for Python project configuration per PEP 518/621.

### 3. GitHub Actions for CI
**Choice**: A single `.github/workflows/ci.yml` workflow with lint and test jobs.
**Rationale**: GitHub Actions is already the platform used by this repository (it has `.github/` infrastructure). A single workflow file keeps things simple. Matrix testing across Python versions is out of scope since the README specifies Python 3.10+.

### 4. Pre-commit for local checks
**Choice**: Add a `.pre-commit-config.yaml` with Ruff hooks.
**Rationale**: Pre-commit is the de facto standard for Git hook management in Python projects. It runs the same Ruff checks locally that CI runs remotely, catching issues early.

### 5. Linter rule selection
**Choice**: Enable Ruff rule sets `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `UP` (pyupgrade), `S` (bandit/security), and `B` (bugbear). Disable specific rules that conflict with existing code patterns (e.g., `S603`/`S607` for subprocess calls, which are core to the tool's function).
**Rationale**: These rule sets cover the most impactful checks without being overly noisy. Security rules (bandit) are particularly valuable given the tool's use of `subprocess` and shell commands.

## Risks / Trade-offs

- **[Linter noise on existing code]** → Mitigated by selecting per-file ignores and disabling rules that conflict with the tool's intentional use of subprocess/shell commands.
- **[CI adding friction]** → Mitigated by keeping CI fast (Ruff is sub-second; tests are lightweight) and non-blocking on the initial PR.
- **[Pre-commit adoption]** → Pre-commit is optional for contributors; CI enforces the same rules. No risk if contributors skip it.
