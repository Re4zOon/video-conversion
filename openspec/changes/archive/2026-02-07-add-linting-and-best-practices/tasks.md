## 1. Project Configuration

- [x] 1.1 Create `pyproject.toml` with project metadata (name, version, description, requires-python >=3.10), runtime dependencies (ffprobe-python), and optional dev dependencies (ruff, pytest, pre-commit)
- [x] 1.2 Add `[tool.pytest.ini_options]` section to `pyproject.toml` with test discovery settings

## 2. Linting and Formatting

- [x] 2.1 Add `[tool.ruff]` configuration to `pyproject.toml` with target Python version, rule sets (E, F, I, UP, S, B), and per-file ignores for subprocess rules in `video.py`
- [x] 2.2 Fix any existing linting violations in `video.py` and `test_video_errors.py` so that `ruff check .` passes
- [x] 2.3 Format `video.py` and `test_video_errors.py` with `ruff format` so that `ruff format --check .` passes

## 3. Pre-commit Hooks

- [x] 3.1 Create `.pre-commit-config.yaml` with Ruff lint and format hooks

## 4. CI Pipeline

- [x] 4.1 Create `.github/workflows/ci.yml` with lint job (ruff check + ruff format --check) and test job (pip install + pytest), triggered on push to main and pull requests

## 5. Verification

- [x] 5.1 Run `ruff check .` and `ruff format --check .` and verify both pass
- [x] 5.2 Run `pytest` and verify all existing tests still pass
