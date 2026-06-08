#!/usr/bin/python3

import argparse
import atexit
import curses
import logging
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from threading import RLock

from ffprobe import FFProbe

logger = logging.getLogger(__name__)

_TRACKED_TEMP_FILES = set()
_TRACKED_PARTIAL_OUTPUTS = set()
_SIGNAL_HANDLED = False
_CLEANUP_DONE = False
_TEMP_LOCK = RLock()
EXIT_CODE_SIGINT = 130  # Standard Unix exit code for SIGINT (128 + 2).
EXIT_CODE_SIGTERM = 143  # Standard Unix exit code for SIGTERM (128 + 15).
PARTIAL_OUTPUT_SUFFIX = ".partial"


def configure_logging():
    """Configure logging based on the GOPRO_LOG_LEVEL environment variable."""
    log_level_name = os.getenv("GOPRO_LOG_LEVEL", "INFO").upper()
    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level_name not in allowed_levels:
        log_level_name = "INFO"
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")


def sanitize_for_log(value):
    """Return a sanitized string safe for logging with newlines and carriage returns escaped."""
    return str(value).replace("\n", "\\n").replace("\r", "\\r")


def sanitize_for_display(value):
    """Return a display-safe string with non-printable characters escaped."""
    return str(value).encode("unicode_escape").decode("ascii")


def is_valid_filename(name):
    """Return True if the provided name is a safe filename without path components."""
    if "\x00" in name:
        return False
    if name in {".", ".."}:
        return False
    if os.path.isabs(name):
        return False
    if os.path.sep in name:
        return False
    if os.path.altsep is not None and os.path.altsep in name:
        return False
    return True


def resolve_output_destination(destination):
    """Resolve conflicts for output files, returning the chosen destination or None to cancel."""
    while True:
        try:
            path_exists = os.path.lexists(destination)
        except ValueError:
            logger.error(
                "Invalid output destination path (possible embedded NUL): %s",
                sanitize_for_log(destination),
            )
            return None
        if not path_exists:
            return destination
        display_destination = sanitize_for_display(destination)
        prompt = (
            f"Output file '{display_destination}' already exists. "
            "Choose [o]verwrite, [r]ename, or [c]ancel: "
        )
        try:
            choice = input(prompt).strip().lower()
        except EOFError:
            logger.info(
                "No input available to resolve output conflict for '%s'.",
                sanitize_for_log(destination),
            )
            return None
        if choice in {"o", "overwrite"}:
            # Only allow overwrite for regular files; disallow directories and other non-file paths.
            try:
                path_stat = os.lstat(destination)
            except FileNotFoundError:
                logger.info(
                    "Destination '%s' disappeared before overwrite; proceeding.",
                    sanitize_for_log(destination),
                )
                return destination
            except PermissionError as exc:
                logger.error(
                    "Permission denied accessing existing path '%s': %s",
                    sanitize_for_log(destination),
                    sanitize_for_log(exc),
                )
                print(
                    "Cannot access the existing path due to permissions. "
                    "Please choose rename or cancel."
                )
                continue
            except OSError as exc:
                logger.error(
                    "Error accessing existing path '%s': %s",
                    sanitize_for_log(destination),
                    sanitize_for_log(exc),
                )
                print("Error accessing the existing path. Please choose rename or cancel.")
                continue
            if stat.S_ISLNK(path_stat.st_mode):
                logger.error(
                    "Cannot overwrite symlink '%s'. Please choose rename or cancel.",
                    sanitize_for_log(destination),
                )
                print("Cannot overwrite a symlink. Please choose rename or cancel.")
                continue
            if stat.S_ISDIR(path_stat.st_mode):
                logger.error(
                    "Cannot overwrite existing directory '%s'. Please choose rename or cancel.",
                    sanitize_for_log(destination),
                )
                print("Cannot overwrite a directory. Please choose rename or cancel.")
                continue
            if not stat.S_ISREG(path_stat.st_mode):
                logger.error(
                    "Cannot overwrite non-regular file '%s'. Please choose rename or cancel.",
                    sanitize_for_log(destination),
                )
                print("Cannot overwrite this type of path. Please choose rename or cancel.")
                continue
            return destination
        if choice in {"r", "rename"}:
            try:
                new_destination = input(
                    "Enter a new output filename (leave blank to cancel): "
                ).strip()
            except EOFError:
                logger.info(
                    "No input available to rename output for '%s'.",
                    sanitize_for_log(destination),
                )
                return None
            if not new_destination:
                return None
            if not is_valid_filename(new_destination):
                print(
                    "Invalid filename. Please enter a name without any directory path components."
                )
                logger.warning(
                    "Rejected invalid rename target '%s' for destination '%s'.",
                    sanitize_for_log(new_destination),
                    sanitize_for_log(destination),
                )
                continue
            destination = os.path.join(os.path.dirname(destination), new_destination)
            continue
        if choice in {"c", "cancel"}:
            return None
        print("Invalid choice. Please enter 'o', 'r', or 'c'.")


def register_temp_file(path):
    if path:
        with _TEMP_LOCK:
            _TRACKED_TEMP_FILES.add(path)


def unregister_temp_file(path):
    if path:
        with _TEMP_LOCK:
            _TRACKED_TEMP_FILES.discard(path)


def register_partial_output(path):
    if path:
        with _TEMP_LOCK:
            _TRACKED_PARTIAL_OUTPUTS.add(path)


def unregister_partial_output(path):
    if path:
        with _TEMP_LOCK:
            _TRACKED_PARTIAL_OUTPUTS.discard(path)


def cleanup_temporary_artifacts():
    global _CLEANUP_DONE
    with _TEMP_LOCK:
        if _CLEANUP_DONE:
            return
        _CLEANUP_DONE = True
        temp_files = list(_TRACKED_TEMP_FILES)
        partial_outputs = list(_TRACKED_PARTIAL_OUTPUTS)

    for path in temp_files:
        cleanup_tracked_path(path, "temporary file", unregister_temp_file)

    for path in partial_outputs:
        cleanup_tracked_path(path, "partial output", unregister_partial_output)


def cleanup_tracked_path(path, label, unregister_callback=None, *, raise_on_error=False):
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        # The file is already gone; nothing left to clean up.
        pass
    except OSError as exc:
        if raise_on_error:
            raise VideoConversionError(f"Failed to clean up {label} '{path}': {exc}") from exc
        logger.warning(
            "Failed to clean up %s %s: %s",
            label,
            sanitize_for_log(path),
            sanitize_for_log(exc),
        )
    finally:
        if unregister_callback:
            unregister_callback(path)


def handle_shutdown_signal(signum, _frame):
    global _SIGNAL_HANDLED
    with _TEMP_LOCK:
        if _SIGNAL_HANDLED:
            return
        _SIGNAL_HANDLED = True
    logger.info("Received signal %s. Cleaning up temporary files.", signum)
    cleanup_temporary_artifacts()
    if signum == signal.SIGINT:
        raise SystemExit(EXIT_CODE_SIGINT)
    if signum == signal.SIGTERM:
        raise SystemExit(EXIT_CODE_SIGTERM)
    # Fallback for any future signals registered here.
    raise SystemExit(128 + signum)


def configure_signal_handlers():
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    atexit.register(cleanup_temporary_artifacts)


def reset_signal_state():
    global _SIGNAL_HANDLED, _CLEANUP_DONE
    with _TEMP_LOCK:
        _SIGNAL_HANDLED = False
        _CLEANUP_DONE = False


def escape_concat_path(path):
    """Escape file paths for use in ffmpeg concat files."""
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


BITRATE_1080P = 14680064  # Optimized bitrate for 1080p video
BITRATE_1520P = 18874368  # Optimized bitrate for 1520p video
BITRATE_2160P = 23068672  # Optimized bitrate for 2160p (4K) video
HEIGHT_1080P = 1080
HEIGHT_1520P = 1520
HEIGHT_2160P = 2160
MAXRATE_MULTIPLIER = 1.5
BUFSIZE_MULTIPLIER = 4
GOPRO_PREFIX_LENGTH = 4
MP4_EXTENSION_LENGTH = 4


def get_file_sequence(filename):
    if len(filename) <= MP4_EXTENSION_LENGTH:
        return filename
    if filename.startswith("GH") or filename.startswith("GX"):
        return filename[GOPRO_PREFIX_LENGTH:][:-MP4_EXTENSION_LENGTH]
    return filename[:-MP4_EXTENSION_LENGTH]


class VideoConversionError(Exception):
    """Raised when video processing operations fail (probe, organize, convert), chaining errors."""


class VideoConversionCancelled(Exception):
    """Raised when the user cancels conversion before processing starts."""


def arguments():

    parser = argparse.ArgumentParser(
        description="GoPro video compressor (prompts before overwriting output files)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--videos", help="Path to the videos folder")
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch an interactive terminal interface for selecting options",
    )
    parser.add_argument(
        "-c",
        "--codec",
        type=str,
        default="h265",
        choices=["h265", "h264"],
        help="Choose codec (default: h265)",
    )
    parser.add_argument(
        "-a",
        "--accelerator",
        type=str,
        default="qsv",
        choices=["qsv", "cpu"],
        help="Choose accelerator (default: qsv)",
    )
    parser.add_argument("-C", "--convert", action="store_false", help="Disable video conversion")
    parser.add_argument(
        "-mx",
        "--mbits_max",
        type=int,
        default=25,
        help="Max bitrate for conversion (default: 25)",
    )
    parser.add_argument(
        "-rx",
        "--ratio_max",
        type=float,
        default=0.70,
        help="Max ratio of bitrate for conversion (default: 0.70)",
    )
    parser.add_argument(
        "-bm",
        "--bitratemodifier",
        type=float,
        default=0.12,
        help="Bitrate modifier for conversion (default: 0.12)",
    )
    parser.add_argument(
        "-R",
        "--resume",
        action="store_true",
        help="Skip sequences that already have output files (no overwrite prompt)",
    )
    args = parser.parse_args()
    if not args.tui and not args.videos:
        parser.error("the following arguments are required unless --tui is used: -v/--videos")
    config = vars(args)
    return config


def bash_command(cmd, context="command execution"):

    try:
        subprocess.run(["/bin/bash", "-c", cmd], check=True)
    except FileNotFoundError as exc:
        raise VideoConversionError(f"Bash not available during {context}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoConversionError(f"Command failed during {context}: {exc}") from exc


def probeVideo(source):

    try:
        file = FFProbe(source)
    except FileNotFoundError as exc:
        raise VideoConversionError(
            f"Source file not found while probing '{source}': {exc}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise VideoConversionError(f"Failed to probe source file '{source}': {exc}") from exc

    if not file.streams:
        raise VideoConversionError(f"No streams found in source file '{source}'")

    return file


def calculateBitrate(source, bitratemodifier, mbits_max, ratio_max, probe=None):

    try:
        file = probe or probeVideo(source)
        if not file.streams:
            raise VideoConversionError(f"No streams found in probe for '{source}'")
        stream = file.streams[0]

        required_fields = {
            "coded_height": stream.coded_height,
            "coded_width": stream.coded_width,
            "framerate": stream.framerate,
            "bit_rate": stream.bit_rate,
        }
        missing_fields = [name for name, value in required_fields.items() if value is None]
        if missing_fields:
            raise VideoConversionError(
                f"Missing stream metadata in '{source}': {', '.join(missing_fields)}"
            )

        try:
            coded_height = int(stream.coded_height)
        except (TypeError, ValueError) as exc:
            raise VideoConversionError(
                f"Invalid coded_height in '{source}': {stream.coded_height}"
            ) from exc

        try:
            coded_width = int(stream.coded_width)
        except (TypeError, ValueError) as exc:
            raise VideoConversionError(
                f"Invalid coded_width in '{source}': {stream.coded_width}"
            ) from exc

        try:
            framerate = float(stream.framerate)
        except (TypeError, ValueError) as exc:
            raise VideoConversionError(
                f"Invalid framerate in '{source}': {stream.framerate}"
            ) from exc

        try:
            bit_rate = int(stream.bit_rate)
        except (TypeError, ValueError) as exc:
            raise VideoConversionError(
                f"Invalid bit_rate in '{source}': {stream.bit_rate}"
            ) from exc

        if coded_height == HEIGHT_1080P:
            bitrate = BITRATE_1080P
        elif coded_height == HEIGHT_1520P:
            bitrate = BITRATE_1520P
        elif coded_height == HEIGHT_2160P:
            bitrate = BITRATE_2160P
        else:
            bitrate = int(round(coded_height * coded_width * framerate * bitratemodifier))

        bitrate_limit = int(round(bit_rate * ratio_max))

        if bitrate > bitrate_limit:
            bitrate = bitrate_limit

        if bitrate > mbits_max * 1024 * 1024:
            bitrate = mbits_max * 1024 * 1024

        result = bitrate
        return result
    except VideoConversionError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        IndexError,
        AttributeError,
        subprocess.SubprocessError,
    ) as exc:
        raise VideoConversionError(f"Failed to calculate bitrate for '{source}': {exc}") from exc


def videostofolders(contents, path):

    # Checking if there is anything to move
    if any(word.lower().endswith(".mp4") for word in contents):
        logger.info("There is something to sort")
    else:
        logger.info("There is nothing to sort")
        return []

    files = []
    # Selecting only files to be moved
    for content in contents:
        if content.lower().endswith(".mp4"):
            files.append(content)

    file_sequences = {file: get_file_sequence(file) for file in files}

    # Getting all unique sequences
    listOfSequences = []
    for file in files:
        file_sequence = file_sequences[file]
        if file_sequence not in listOfSequences:
            listOfSequences.append(file_sequence)

    try:
        # Creating folders for each sequence
        for sequence in listOfSequences:
            os.makedirs(os.path.join(path, sequence), exist_ok=True)

        # Moving files to their respective folders
        for sequence in listOfSequences:
            for file in files:
                file_sequence = file_sequences[file]

                if file_sequence == sequence:
                    src_path = os.path.join(path, file)
                    dst_path = os.path.join(path, sequence, file)
                    if os.path.exists(dst_path):
                        logger.warning(
                            "Skipping moving '%s' to '%s' because destination already exists",
                            src_path,
                            dst_path,
                        )
                        continue
                    os.rename(src_path, dst_path)
    except OSError as exc:
        raise VideoConversionError(f"Failed to organize videos in '{path}': {exc}") from exc

    return listOfSequences


def convertVideos(
    path,
    options,
    bitratemodifier,
    mbits_max,
    ratio_max,
    convert,
    resume=False,
    sequences=None,
    progress_callback=None,
):

    # Use provided sequences list or fall back to directory listing
    try:
        if sequences is not None:
            _listOfSequences = sequences
        else:
            _listOfSequences = os.listdir(path)
            _listOfSequences.sort()
    except OSError as exc:
        raise VideoConversionError(f"Unable to list sequences in '{path}': {exc}") from exc

    sanitized_sequences = [sanitize_for_log(sequence) for sequence in _listOfSequences]
    logger.info("List: %s", ", ".join(sanitized_sequences))
    total_sequences = len(_listOfSequences)
    for index, (sequence, sanitized_sequence) in enumerate(
        zip(_listOfSequences, sanitized_sequences, strict=True), start=1
    ):
        try:
            partial_destination = None
            conversion_successful = False
            files = os.listdir(os.path.join(path, sequence))
            files.sort()
            if not files:
                raise VideoConversionError(f"No video files found in sequence '{sequence}'")
            source = os.path.join(path, sequence, files[0])
            destination = os.path.join(path, files[0])
            if resume and os.path.lexists(destination):
                logger.info(
                    "Skipping sequence %s because output already exists (resume enabled).",
                    sanitized_sequence,
                )
                notify_progress(
                    progress_callback,
                    "skip",
                    sanitized_sequence,
                    index,
                    total_sequences,
                    "Output already exists; resume skipped it.",
                )
                continue
            if not resume:
                resolved_destination = resolve_output_destination(destination)
                if resolved_destination is None:
                    raise VideoConversionCancelled(
                        "Conversion cancelled by user before processing sequence "
                        f"'{sanitized_sequence}'."
                    )
                destination = resolved_destination
            partial_destination = f"{destination}{PARTIAL_OUTPUT_SUFFIX}"
            # Attempt to clean up stale partial output; log a warning on failure.
            cleanup_tracked_path(partial_destination, "stale partial output", raise_on_error=False)
            register_partial_output(partial_destination)
            file = probeVideo(source)
            if len(file.streams) < 2:
                stream_count = len(file.streams)
                raise VideoConversionError(
                    f"Expected at least 2 streams in '{source}' but found {stream_count} stream(s)"
                )
            bitrate = calculateBitrate(source, bitratemodifier, mbits_max, ratio_max, probe=file)
            logger.info("Sequence: %s", sanitized_sequence)
            notify_progress(
                progress_callback,
                "start",
                sanitized_sequence,
                index,
                total_sequences,
                "Starting conversion.",
            )

            quoted_source = shlex.quote(source)
            quoted_destination = shlex.quote(partial_destination)
            sanitized_source = sanitize_for_log(source)
            sanitized_destination = sanitize_for_log(destination)

            concat_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", delete=False, suffix=".txt"
                ) as concat_file:
                    concat_path = concat_file.name
                    register_temp_file(concat_path)
                    # Follow ffmpeg concat demuxer file list format (file '/absolute/path').
                    for filename in files:
                        file_path = os.path.abspath(os.path.join(path, sequence, filename))
                        escaped_path = escape_concat_path(file_path)
                        concat_file.write(f"file '{escaped_path}'\n")

                quoted_concat = shlex.quote(concat_path)
                concat_cmd = f"ffmpeg -y -f concat -safe 0 -i {quoted_concat} "

                if convert:
                    maxrate = int(bitrate * MAXRATE_MULTIPLIER)
                    bufsize = int(bitrate * BUFSIZE_MULTIPLIER)
                    ffmpeg_cmd = (
                        f"{concat_cmd}{options} -b:v {bitrate} -maxrate {maxrate} "
                        f"-bitrate_limit 0 -bufsize {bufsize} -fps_mode passthrough -g 120 "
                        f"-preset slower -look_ahead 1 -map 0:0 -map 0:1"
                    )
                else:
                    ffmpeg_cmd = f"{concat_cmd}-c copy -map 0:0 -map 0:1"

                if len(file.streams) >= 4:
                    if file.streams[3].codec_name == "bin_data":
                        # Processes streams 0-1 and conditionally stream 3
                        # when telemetry is present.
                        ffmpeg_cmd = f"{ffmpeg_cmd} -map 0:3 {quoted_destination}"
                        action = "converting" if convert else "concatenating"
                        bash_command(
                            ffmpeg_cmd,
                            f"{action} sequence '{sanitized_sequence}'",
                        )
                        bash_command(
                            f"udtacopy {quoted_source} {quoted_destination}",
                            f"copying telemetry for '{sanitized_sequence}'",
                        )
                        exiftool_cmd = (
                            f"exiftool -TagsFromFile {quoted_source}"
                            f" -CreateDate -MediaCreateDate"
                            f" -MediaModifyDate -ModifyDate"
                            f" {quoted_destination}"
                        )
                        bash_command(
                            exiftool_cmd,
                            f"copying metadata for '{sanitized_sequence}'",
                        )
                    else:
                        codec = file.streams[3].codec_name
                        raise VideoConversionError(
                            f"Expected bin_data stream at index 3 in '{source}' but found '{codec}'"
                        )
                elif len(file.streams) == 3:
                    stream_count = len(file.streams)
                    raise VideoConversionError(
                        f"Unsupported stream layout in '{source}':"
                        f" expected 2 streams (video+audio) or at least"
                        f" 4 streams (video+audio+extra+telemetry),"
                        f" but found {stream_count} stream(s)"
                    )
                else:
                    ffmpeg_cmd = f"{ffmpeg_cmd} {quoted_destination}"
                    action = "converting" if convert else "concatenating"
                    bash_command(
                        ffmpeg_cmd,
                        f"{action} sequence '{sanitized_sequence}'",
                    )
                    exiftool_cmd = (
                        f"exiftool -TagsFromFile {quoted_source}"
                        f" -CreateDate -MediaCreateDate"
                        f" -MediaModifyDate -ModifyDate"
                        f" {quoted_destination}"
                    )
                    bash_command(
                        exiftool_cmd,
                        f"copying metadata for '{sanitized_sequence}'",
                    )

                try:
                    # Atomic when source/destination are on the same filesystem;
                    # ensures completed outputs replace the final file.
                    os.replace(partial_destination, destination)
                    unregister_partial_output(partial_destination)
                    conversion_successful = True
                except OSError as exc:
                    raise VideoConversionError(
                        f"Failed to finalize output file for '{sanitized_sequence}': {exc}"
                    ) from exc

                try:
                    shutil.copystat(source, destination)
                except OSError as exc:
                    logger.warning(
                        "Failed to copy file metadata from '%s' to '%s': %s",
                        sanitized_source,
                        sanitized_destination,
                        sanitize_for_log(exc),
                    )
                notify_progress(
                    progress_callback,
                    "done",
                    sanitized_sequence,
                    index,
                    total_sequences,
                    f"Finished {os.path.basename(destination)}.",
                )
            finally:
                if concat_path:
                    cleanup_tracked_path(concat_path, "temporary concat file", unregister_temp_file)
                # Skip partial cleanup when the output is finalized
                # or resume has skipped the sequence.
                if partial_destination and not conversion_successful:
                    cleanup_tracked_path(
                        partial_destination, "partial output", unregister_partial_output
                    )
        except VideoConversionError:
            raise
        except (OSError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
            raise VideoConversionError(
                f"Error processing sequence '{sequence}' in '{path}': {exc}"
            ) from exc


def getOptions(codec, accelerator):

    options = ""
    if accelerator == "qsv":
        if codec == "h265":
            options = "-init_hw_device qsv=hw -c copy -c:v hevc_qsv -extbrc 1 -refs 20 -bf 7"
        elif codec == "h264":
            options = "-init_hw_device qsv=hw -c copy -c:v h264_qsv"
    elif accelerator == "cpu":
        if codec == "h265":
            options = "-c copy -c:v libx265"
        elif codec == "h264":
            options = "-c copy -c:v libx264"

    if not options:
        raise VideoConversionError(
            f"Unsupported codec/accelerator combination: {codec}/{accelerator}"
        )

    return options


def notify_progress(callback, event, sequence, index, total, message):
    """Report conversion progress to optional callers such as the TUI."""
    if callback is None:
        return
    callback(
        {
            "event": event,
            "sequence": sequence,
            "index": index,
            "total": total,
            "message": message,
        }
    )


def validate_videos_path(videos_path):
    sanitized_path = sanitize_for_log(videos_path)
    if not os.path.exists(videos_path):
        raise VideoConversionError(f"The specified path does not exist: {sanitized_path}")
    if not os.path.isdir(videos_path):
        raise VideoConversionError(f"The specified path is not a directory: {sanitized_path}")


def run_conversion(config, progress_callback=None):
    videos_path = config["videos"]
    validate_videos_path(videos_path)

    try:
        contents = os.listdir(videos_path)
        contents.sort()
    except OSError as exc:
        raise VideoConversionError(f"Unable to list contents of '{videos_path}': {exc}") from exc

    sequences = videostofolders(contents, videos_path)
    if not sequences:
        logger.info("No video sequences to convert. Exiting.")
        notify_progress(
            progress_callback,
            "done",
            "",
            0,
            0,
            "No video sequences to convert.",
        )
        return

    options = getOptions(config["codec"], config["accelerator"])
    convertVideos(
        videos_path,
        options,
        config["bitratemodifier"],
        config["mbits_max"],
        config["ratio_max"],
        config["convert"],
        resume=config["resume"],
        sequences=sequences,
        progress_callback=progress_callback,
    )


class TuiLogHandler(logging.Handler):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def emit(self, record):
        self.messages.append(self.format(record))
        del self.messages[:-8]


def draw_tui(stdscr, config, selected, messages, progress):
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    fields = [
        ("Videos folder", config["videos"]),
        ("Codec", config["codec"]),
        ("Accelerator", config["accelerator"]),
        ("Convert", "yes" if config["convert"] else "no"),
        ("Resume", "yes" if config["resume"] else "no"),
        ("Start conversion", ""),
        ("Quit", ""),
    ]
    title = "GoPro Video Compressor"
    stdscr.addnstr(0, 2, title, max(0, width - 4), curses.A_BOLD)
    stdscr.addnstr(
        1,
        2,
        "Use arrows to move, Enter to edit/toggle/start, q to quit.",
        max(0, width - 4),
    )

    for row, (label, value) in enumerate(fields, start=3):
        attr = curses.A_REVERSE if row - 3 == selected else curses.A_NORMAL
        line = f"{label}: {value}" if value else label
        stdscr.addnstr(row, 2, line, max(0, width - 4), attr)

    progress_row = 11
    total = progress["total"]
    index = progress["index"]
    if total:
        bar_width = max(10, min(40, width - 20))
        filled = int(bar_width * index / total)
        bar = "#" * filled + "-" * (bar_width - filled)
        progress_text = f"[{bar}] {index}/{total} {progress['sequence']}"
    else:
        progress_text = progress["message"]
    stdscr.addnstr(progress_row, 2, progress_text, max(0, width - 4))

    log_start = progress_row + 2
    stdscr.addnstr(log_start, 2, "Messages", max(0, width - 4), curses.A_BOLD)
    for offset, message in enumerate(messages[-8:], start=1):
        if log_start + offset >= height - 1:
            break
        stdscr.addnstr(log_start + offset, 2, sanitize_for_display(message), max(0, width - 4))
    stdscr.refresh()


def prompt_tui_input(stdscr, prompt, current):
    curses.echo()
    height, width = stdscr.getmaxyx()
    row = height - 2
    stdscr.move(row, 0)
    stdscr.clrtoeol()
    stdscr.addnstr(row, 2, f"{prompt} [{current}]: ", max(0, width - 4))
    value = stdscr.getstr(row, min(width - 1, len(prompt) + len(str(current)) + 7))
    curses.noecho()
    decoded = value.decode(errors="replace").strip()
    return decoded or current


def run_tui(initial_config):
    config = initial_config.copy()
    config["videos"] = config.get("videos") or os.getcwd()
    messages = []
    progress = {"index": 0, "total": 0, "sequence": "", "message": "Ready."}

    def progress_callback(event):
        progress.update(
            {
                "index": event["index"],
                "total": event["total"],
                "sequence": event["sequence"],
                "message": event["message"],
            }
        )
        messages.append(event["message"])
        del messages[:-8]

    def app(stdscr):
        selected = 0
        logger_handler = TuiLogHandler(messages)
        logger_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(logger_handler)
        try:
            curses.curs_set(0)
            while True:
                draw_tui(stdscr, config, selected, messages, progress)
                key = stdscr.getch()
                if key in (ord("q"), ord("Q")):
                    return 0
                if key in (curses.KEY_UP, ord("k")):
                    selected = (selected - 1) % 7
                    continue
                if key in (curses.KEY_DOWN, ord("j")):
                    selected = (selected + 1) % 7
                    continue
                if key not in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                    continue
                if selected == 0:
                    config["videos"] = prompt_tui_input(stdscr, "Videos folder", config["videos"])
                elif selected == 1:
                    config["codec"] = "h264" if config["codec"] == "h265" else "h265"
                elif selected == 2:
                    config["accelerator"] = "cpu" if config["accelerator"] == "qsv" else "qsv"
                elif selected == 3:
                    config["convert"] = not config["convert"]
                elif selected == 4:
                    config["resume"] = not config["resume"]
                elif selected == 5:
                    try:
                        messages.append("Starting conversion. Press Ctrl+C to stop.")
                        run_conversion(config, progress_callback=progress_callback)
                        messages.append("Conversion finished.")
                    except VideoConversionCancelled as exc:
                        messages.append(f"Cancelled: {exc}")
                    except VideoConversionError as exc:
                        messages.append(f"Error: {exc}")
                    progress["message"] = "Ready."
                elif selected == 6:
                    return 0
        finally:
            logger.removeHandler(logger_handler)

    return curses.wrapper(app)


if __name__ == "__main__":
    if sys.version_info < (3, 10):  # noqa: UP036 — runtime guard for direct script execution
        print("Error: Python 3.10 or later is required.", file=sys.stderr)
        sys.exit(1)

    try:
        configure_logging()
        reset_signal_state()
        configure_signal_handlers()
        args = arguments()
        if args["tui"]:
            sys.exit(run_tui(args))
        run_conversion(args)
    except VideoConversionCancelled as exc:
        logger.info("Conversion cancelled by user: %s", sanitize_for_log(exc))
        sys.exit(1)
    except VideoConversionError as exc:
        logger.error("Conversion halted: %s", sanitize_for_log(exc))
        sys.exit(1)
    except (OSError, PermissionError) as exc:
        logger.error("Filesystem error during processing: %s", sanitize_for_log(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user (Ctrl+C).")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected error: %s", sanitize_for_log(exc))
        sys.exit(1)
