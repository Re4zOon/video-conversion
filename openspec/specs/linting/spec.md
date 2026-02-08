### Requirement: Ruff linting configuration
The project SHALL include a Ruff linter configuration that enforces pycodestyle (E), pyflakes (F), isort (I), pyupgrade (UP), bandit security checks (S), and bugbear (B) rule sets.

#### Scenario: Linting catches style violations
- **WHEN** a developer runs `ruff check .` on the repository
- **THEN** any violations of the enabled rule sets SHALL be reported with file, line, and rule code

#### Scenario: Linting passes on clean code
- **WHEN** all Python files conform to the configured rules
- **THEN** `ruff check .` SHALL exit with code 0 and produce no output

### Requirement: Ruff formatting configuration
The project SHALL include a Ruff formatter configuration that enforces consistent code formatting.

#### Scenario: Format check detects unformatted code
- **WHEN** a developer runs `ruff format --check .`
- **THEN** any files that differ from the canonical format SHALL be reported

#### Scenario: Format check passes on formatted code
- **WHEN** all Python files match the canonical Ruff format
- **THEN** `ruff format --check .` SHALL exit with code 0

### Requirement: Security-sensitive rule suppression
The linter configuration SHALL suppress subprocess-related security rules (S603, S607) for `video.py`, since subprocess invocation is core functionality of the tool.

#### Scenario: Subprocess calls do not trigger security warnings
- **WHEN** `ruff check video.py` is run
- **THEN** rules S603 and S607 SHALL NOT be reported for `video.py`

### Requirement: Pre-commit hook integration
The project SHALL include a `.pre-commit-config.yaml` that runs Ruff lint and format checks as Git pre-commit hooks.

#### Scenario: Pre-commit validates hooks
- **WHEN** a developer runs `pre-commit run --all-files`
- **THEN** Ruff lint and format hooks SHALL execute against all Python files
