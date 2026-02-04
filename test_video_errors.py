import subprocess

import pytest

import video


def test_bash_command_handles_missing_shell(monkeypatch):
    def raise_missing(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(video.subprocess, "run", raise_missing)

    with pytest.raises(video.VideoConversionError, match="Bash not available"):
        video.bash_command("echo test", context="test")


def test_bash_command_handles_command_failure(monkeypatch):
    def raise_failure(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "echo test")

    monkeypatch.setattr(video.subprocess, "run", raise_failure)

    with pytest.raises(video.VideoConversionError, match="Command failed"):
        video.bash_command("echo test", context="test")


def test_get_options_rejects_invalid_combo():
    with pytest.raises(video.VideoConversionError, match="Unsupported codec/accelerator"):
        video.getOptions("bad", "cpu")
