import subprocess

import pytest

import video


class DummyStream:
    """Lightweight stream mock with configurable metadata for tests."""
    def __init__(
        self,
        coded_height=1080,
        coded_width=1920,
        framerate=30.0,
        bit_rate=1000,
        codec_name="h264",
    ):
        self.coded_height = coded_height
        self.coded_width = coded_width
        self.framerate = framerate
        self.bit_rate = bit_rate
        self.codec_name = codec_name


class DummyProbe:
    """Simple probe mock that exposes a streams list for tests."""
    def __init__(self, streams):
        self.streams = streams


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


def test_probe_video_handles_missing_file(monkeypatch):
    def raise_missing(_source):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(video, "FFProbe", raise_missing)

    with pytest.raises(video.VideoConversionError, match="Source file not found"):
        video.probeVideo("/tmp/missing.mp4")


def test_probe_video_handles_empty_streams(monkeypatch):
    monkeypatch.setattr(video, "FFProbe", lambda _source: DummyProbe([]))

    with pytest.raises(video.VideoConversionError, match="No streams found"):
        video.probeVideo("/tmp/empty.mp4")


def test_calculate_bitrate_invalid_metadata():
    invalid_probe = DummyProbe([DummyStream(coded_height=None)])

    with pytest.raises(video.VideoConversionError, match="Missing stream metadata"):
        video.calculateBitrate("/tmp/source.mp4", 0.12, 25, 0.7, probe=invalid_probe)


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("coded_height", "invalid", "Invalid coded_height"),
        ("coded_width", "invalid", "Invalid coded_width"),
        ("framerate", "invalid", "Invalid framerate"),
        ("bit_rate", "invalid", "Invalid bit_rate"),
    ],
)
def test_calculate_bitrate_invalid_types(field, value, expected):
    kwargs = {field: value}
    invalid_probe = DummyProbe([DummyStream(**kwargs)])

    with pytest.raises(video.VideoConversionError, match=expected):
        video.calculateBitrate("/tmp/source.mp4", 0.12, 25, 0.7, probe=invalid_probe)


def test_videos_to_folders_permission_error(monkeypatch, tmp_path):
    def raise_permission(_path, exist_ok=True):
        raise PermissionError("denied")

    monkeypatch.setattr(video.os, "makedirs", raise_permission)
    contents = ["GH010001.MP4"]

    with pytest.raises(video.VideoConversionError, match="Failed to organize videos"):
        video.videostofolders(contents, str(tmp_path))


def test_convert_videos_rejects_single_stream(monkeypatch, tmp_path):
    sequence_path = tmp_path / "0001"
    sequence_path.mkdir()
    source_path = sequence_path / "GH010001.MP4"
    source_path.write_text("video")

    def fake_listdir(path):
        if path == str(tmp_path):
            return ["0001"]
        if path == str(sequence_path):
            return ["GH010001.MP4"]
        return []

    monkeypatch.setattr(video.os, "listdir", fake_listdir)
    monkeypatch.setattr(video, "probeVideo", lambda _source: DummyProbe([DummyStream()]))
    monkeypatch.setattr(video, "calculateBitrate", lambda *_args, **_kwargs: 1000)

    with pytest.raises(video.VideoConversionError, match="Expected at least 2 streams"):
        video.convertVideos(str(tmp_path), "-c copy", 0.12, 25, 0.7, True, sequences=["0001"])


def test_convert_videos_rejects_three_streams(monkeypatch, tmp_path):
    sequence_path = tmp_path / "0002"
    sequence_path.mkdir()
    (sequence_path / "GH010002.MP4").write_text("video")

    def fake_listdir(path):
        if path == str(tmp_path):
            return ["0002"]
        if path == str(sequence_path):
            return ["GH010002.MP4"]
        return []

    monkeypatch.setattr(video.os, "listdir", fake_listdir)
    monkeypatch.setattr(video, "probeVideo", lambda _source: DummyProbe([DummyStream()] * 3))
    monkeypatch.setattr(video, "calculateBitrate", lambda *_args, **_kwargs: 1000)
    monkeypatch.setattr(video, "bash_command", lambda *_args, **_kwargs: None)

    with pytest.raises(video.VideoConversionError, match="Unsupported stream layout"):
        video.convertVideos(str(tmp_path), "-c copy", 0.12, 25, 0.7, True, sequences=["0002"])


def test_convert_videos_rejects_missing_telemetry(monkeypatch, tmp_path):
    sequence_path = tmp_path / "0003"
    sequence_path.mkdir()
    (sequence_path / "GH010003.MP4").write_text("video")

    def fake_listdir(path):
        if path == str(tmp_path):
            return ["0003"]
        if path == str(sequence_path):
            return ["GH010003.MP4"]
        return []

    streams_with_wrong_telemetry_codec = [DummyStream() for _ in range(3)] + [DummyStream(codec_name="h264")]

    monkeypatch.setattr(video.os, "listdir", fake_listdir)
    monkeypatch.setattr(video, "probeVideo", lambda _source: DummyProbe(streams_with_wrong_telemetry_codec))
    monkeypatch.setattr(video, "calculateBitrate", lambda *_args, **_kwargs: 1000)
    monkeypatch.setattr(video, "bash_command", lambda *_args, **_kwargs: None)

    with pytest.raises(video.VideoConversionError, match="Expected bin_data stream"):
        video.convertVideos(str(tmp_path), "-c copy", 0.12, 25, 0.7, True, sequences=["0003"])


def test_convert_videos_resume_skips_existing_output(monkeypatch, tmp_path):
    sequence_path = tmp_path / "0004"
    sequence_path.mkdir()
    (sequence_path / "GH010004.MP4").write_text("video")
    (tmp_path / "GH010004.MP4").write_text("existing")

    def fake_listdir(path):
        if path == str(tmp_path):
            return ["0004"]
        if path == str(sequence_path):
            return ["GH010004.MP4"]
        return []

    def fail_probe(_source):
        raise AssertionError("probe should not be called")

    calls = []

    monkeypatch.setattr(video.os, "listdir", fake_listdir)
    monkeypatch.setattr(video, "probeVideo", fail_probe)
    monkeypatch.setattr(video, "bash_command", lambda *_args, **_kwargs: calls.append(True))

    video.convertVideos(str(tmp_path), "-c copy", 0.12, 25, 0.7, True, resume=True, sequences=["0004"])

    assert not calls


def test_convert_videos_resume_allows_conversion(monkeypatch, tmp_path):
    sequence_path = tmp_path / "0005"
    sequence_path.mkdir()
    source_path = sequence_path / "GH010005.MP4"
    source_path.write_text("video")

    def fake_listdir(path):
        if path == str(tmp_path):
            return ["0005"]
        if path == str(sequence_path):
            return ["GH010005.MP4"]
        return []

    replace_calls = []
    bash_calls = []

    video._TRACKED_PARTIAL_OUTPUTS.clear()
    video._CLEANUP_DONE = False

    monkeypatch.setattr(video.os, "listdir", fake_listdir)
    monkeypatch.setattr(video, "probeVideo", lambda _source: DummyProbe([DummyStream(), DummyStream()]))
    monkeypatch.setattr(video, "calculateBitrate", lambda *_args, **_kwargs: 1000)
    monkeypatch.setattr(video, "bash_command", lambda *_args, **_kwargs: bash_calls.append(True))
    monkeypatch.setattr(video.os, "replace", lambda *_args: replace_calls.append(True))
    monkeypatch.setattr(video.shutil, "copystat", lambda *_args, **_kwargs: None)

    video.convertVideos(str(tmp_path), "-c copy", 0.12, 25, 0.7, True, resume=True, sequences=["0005"])

    assert bash_calls
    assert replace_calls
    assert not video._TRACKED_PARTIAL_OUTPUTS


def test_cleanup_temporary_artifacts_removes_files(tmp_path):
    temp_file = tmp_path / "concat.txt"
    temp_file.write_text("temp")
    partial_file = tmp_path / "output.mp4.partial"
    partial_file.write_text("temp")

    video._TRACKED_TEMP_FILES.clear()
    video._TRACKED_PARTIAL_OUTPUTS.clear()
    video._CLEANUP_DONE = False
    video.register_temp_file(str(temp_file))
    video.register_partial_output(str(partial_file))

    video.cleanup_temporary_artifacts()

    assert not temp_file.exists()
    assert not partial_file.exists()
    assert not video._TRACKED_TEMP_FILES
    assert not video._TRACKED_PARTIAL_OUTPUTS


def test_handle_shutdown_signal_sigint_triggers_cleanup(monkeypatch):
    calls = []

    def record_cleanup():
        calls.append(True)

    video._SIGNAL_HANDLED = False
    video._CLEANUP_DONE = False
    monkeypatch.setattr(video, "cleanup_temporary_artifacts", record_cleanup)

    with pytest.raises(SystemExit) as excinfo:
        video.handle_shutdown_signal(video.signal.SIGINT, None)

    assert excinfo.value.code == video.EXIT_CODE_SIGINT
    assert calls
    assert video._SIGNAL_HANDLED


def test_handle_shutdown_signal_sigterm_triggers_cleanup(monkeypatch):
    calls = []

    def record_cleanup():
        calls.append(True)

    video._SIGNAL_HANDLED = False
    video._CLEANUP_DONE = False
    monkeypatch.setattr(video, "cleanup_temporary_artifacts", record_cleanup)

    with pytest.raises(SystemExit) as excinfo:
        video.handle_shutdown_signal(video.signal.SIGTERM, None)

    assert excinfo.value.code == video.EXIT_CODE_SIGTERM
    assert calls


def test_configure_signal_handlers_registers(monkeypatch):
    registered = []
    atexit_calls = []

    def record_signal(sig, handler):
        registered.append((sig, handler))

    def record_atexit(handler):
        atexit_calls.append(handler)

    monkeypatch.setattr(video.signal, "signal", record_signal)
    monkeypatch.setattr(video.atexit, "register", record_atexit)

    video.configure_signal_handlers()

    assert (video.signal.SIGINT, video.handle_shutdown_signal) in registered
    assert (video.signal.SIGTERM, video.handle_shutdown_signal) in registered
    assert video.cleanup_temporary_artifacts in atexit_calls
