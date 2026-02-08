### Requirement: pyproject.toml with project metadata
The project SHALL include a `pyproject.toml` file containing project name, version, description, Python version requirement (>=3.10), and dependency declarations.

#### Scenario: Project metadata is present
- **WHEN** a developer or tool reads `pyproject.toml`
- **THEN** it SHALL contain `[project]` section with name, version, description, and requires-python fields

### Requirement: Tool configuration in pyproject.toml
The `pyproject.toml` SHALL contain configuration sections for Ruff (`[tool.ruff]`) and pytest (`[tool.pytest.ini_options]`).

#### Scenario: Ruff reads configuration from pyproject.toml
- **WHEN** `ruff check .` is run without a separate ruff config file
- **THEN** Ruff SHALL use the configuration from `[tool.ruff]` in `pyproject.toml`

#### Scenario: Pytest reads configuration from pyproject.toml
- **WHEN** `pytest` is run without a separate pytest config file
- **THEN** pytest SHALL use the configuration from `[tool.pytest.ini_options]` in `pyproject.toml`

### Requirement: Dependencies declared in pyproject.toml
The `pyproject.toml` SHALL declare runtime dependencies (mirroring `requirements.txt`) and optional dev dependencies including ruff, pytest, and pre-commit.

#### Scenario: Dev dependencies installable
- **WHEN** a developer runs `pip install -r requirements-dev.txt`
- **THEN** ruff, pytest, and pre-commit SHALL be installed
