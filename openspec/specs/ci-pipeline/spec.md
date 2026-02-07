### Requirement: CI workflow runs on push and pull request
The project SHALL include a GitHub Actions workflow at `.github/workflows/ci.yml` that triggers on pushes to the `main` branch and on all pull requests.

#### Scenario: Push to main triggers CI
- **WHEN** a commit is pushed to the `main` branch
- **THEN** the CI workflow SHALL run lint and test jobs

#### Scenario: Pull request triggers CI
- **WHEN** a pull request is opened or updated
- **THEN** the CI workflow SHALL run lint and test jobs

### Requirement: CI lint job
The CI workflow SHALL include a lint job that runs `ruff check .` and `ruff format --check .` and fails if either reports violations.

#### Scenario: Lint job fails on violations
- **WHEN** the lint job runs and Ruff detects violations
- **THEN** the job SHALL fail with a non-zero exit code

#### Scenario: Lint job passes on clean code
- **WHEN** the lint job runs and no violations are found
- **THEN** the job SHALL pass with exit code 0

### Requirement: CI test job
The CI workflow SHALL include a test job that installs dependencies and runs `pytest`.

#### Scenario: Test job fails on test failure
- **WHEN** the test job runs and any pytest test fails
- **THEN** the job SHALL fail with a non-zero exit code

#### Scenario: Test job passes when all tests pass
- **WHEN** the test job runs and all tests pass
- **THEN** the job SHALL pass with exit code 0
