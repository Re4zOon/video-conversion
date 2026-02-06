#!/usr/bin/python3

import os
import sys
import argparse
import subprocess
import logging
import shlex
import signal
import atexit
from threading import RLock
from ffprobe import FFProbe
import shutil
import tempfile

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
    logger.warning("Failed to clean up %s %s: %s", label, sanitize_for_log(path), exc)
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

def arguments():

  parser = argparse.ArgumentParser(description="GoPro video compressor", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-v", "--videos", required=True, help="Path to the videos folder")
  parser.add_argument("-c", "--codec", type=str, default="h265", choices=['h265', 'h264'], help="Choose codec (default: h265)")
  parser.add_argument("-a", "--accelerator", type=str, default="qsv", choices=['qsv', 'cpu'], help="Choose accelerator (default: qsv)")
  parser.add_argument("-C", "--convert", action="store_false", help="Disable video conversion")
  parser.add_argument("-mx", "--mbits_max", type=int, default=25, help="Max bitrate for conversion (default: 25)")
  parser.add_argument("-rx", "--ratio_max", type=float, default=0.70, help="Max ratio of bitrate for conversion (default: 0.70)")
  parser.add_argument("-bm", "--bitratemodifier", type=float, default=0.12, help="Bitrate modifier for conversion (default: 0.12)")
  parser.add_argument("-R", "--resume", action="store_true", help="Skip sequences that already have output files")
  args = parser.parse_args()
  config = vars(args)
  return config

def bash_command(cmd, context="command execution"):

  try:
    subprocess.run(['/bin/bash', '-c', cmd], check=True)
  except FileNotFoundError as exc:
    raise VideoConversionError(f"Bash not available during {context}: {exc}") from exc
  except subprocess.CalledProcessError as exc:
    raise VideoConversionError(f"Command failed during {context}: {exc}") from exc

def probeVideo(source):

  try:
    file = FFProbe(source)
  except FileNotFoundError as exc:
    raise VideoConversionError(f"Source file not found while probing '{source}': {exc}") from exc
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
      raise VideoConversionError(f"Missing stream metadata in '{source}': {', '.join(missing_fields)}")

    try:
      coded_height = int(stream.coded_height)
    except (TypeError, ValueError) as exc:
      raise VideoConversionError(f"Invalid coded_height in '{source}': {stream.coded_height}") from exc

    try:
      coded_width = int(stream.coded_width)
    except (TypeError, ValueError) as exc:
      raise VideoConversionError(f"Invalid coded_width in '{source}': {stream.coded_width}") from exc

    try:
      framerate = float(stream.framerate)
    except (TypeError, ValueError) as exc:
      raise VideoConversionError(f"Invalid framerate in '{source}': {stream.framerate}") from exc

    try:
      bit_rate = int(stream.bit_rate)
    except (TypeError, ValueError) as exc:
      raise VideoConversionError(f"Invalid bit_rate in '{source}': {stream.bit_rate}") from exc

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
  except (OSError, ValueError, TypeError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
    raise VideoConversionError(f"Failed to calculate bitrate for '{source}': {exc}") from exc

def videostofolders(contents, path):

  # Checking if there is anything to move
  if any(".MP4" in word for word in contents) or any(".mp4" in word for word in contents):
    logger.info("There is something to sort")
  else:
    logger.info("There is nothing to sort")
    return []

  files = []
  # Selecting only files to be moved
  for content in contents:
    if "MP4" in content or "mp4" in content:
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
          os.rename(os.path.join(path, file), os.path.join(path, sequence, file))
  except OSError as exc:
    raise VideoConversionError(f"Failed to organize videos in '{path}': {exc}") from exc

  return listOfSequences

def convertVideos(path, options, bitratemodifier, mbits_max, ratio_max, convert, resume=False, sequences=None):

  # Use provided sequences list or fall back to directory listing
  try:
    if sequences is not None:
      _listOfSequences = sequences
    else:
      _listOfSequences = os.listdir(path)
      _listOfSequences.sort()
  except OSError as exc:
    raise VideoConversionError(f"Unable to list sequences in '{path}': {exc}") from exc

  sanitized_sequences = {sequence: sanitize_for_log(sequence) for sequence in _listOfSequences}
  logger.info("List: %s", ", ".join(sanitized_sequences[sequence] for sequence in _listOfSequences))
  for sequence in _listOfSequences:
    try:
      partial_destination = None
      conversion_successful = False
      sanitized_sequence = sanitized_sequences.get(sequence, sanitize_for_log(sequence))
      files = os.listdir(os.path.join(path, sequence))
      files.sort()
      if not files:
        raise VideoConversionError(f"No video files found in sequence '{sequence}'")
      source = os.path.join(path, sequence, files[0])
      destination = os.path.join(path, files[0])
      if resume and os.path.exists(destination):
        logger.info("Skipping sequence %s because output already exists (resume enabled).", sanitized_sequence)
        continue
      partial_destination = f"{destination}{PARTIAL_OUTPUT_SUFFIX}"
      # Warn if a stale partial output cannot be removed before converting.
      cleanup_tracked_path(partial_destination, "stale partial output")
      register_partial_output(partial_destination)
      file = probeVideo(source)
      if len(file.streams) < 2:
        raise VideoConversionError(
          f"Expected at least 2 streams in '{source}' but found {len(file.streams)} stream(s)"
        )
      bitrate = calculateBitrate(source, bitratemodifier, mbits_max, ratio_max, probe=file)
      logger.info("Sequence: %s", sanitized_sequence)

      quoted_source = shlex.quote(source)
      quoted_destination = shlex.quote(partial_destination)
      sanitized_source = sanitize_for_log(source)
      sanitized_destination = sanitize_for_log(destination)

      concat_path = None
      try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as concat_file:
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
          if file.streams[3].codec_name == 'bin_data':
            # This tool processes streams 0-1 and conditionally stream 3 when telemetry is present.
            ffmpeg_cmd = f"{ffmpeg_cmd} -map 0:3 {quoted_destination}"
            bash_command(ffmpeg_cmd, f"{'converting' if convert else 'concatenating'} sequence '{sanitized_sequence}'")
            bash_command(f"udtacopy {quoted_source} {quoted_destination}", f"copying telemetry for '{sanitized_sequence}'")
            bash_command(
              f"exiftool -TagsFromFile {quoted_source} -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate {quoted_destination}",
              f"copying metadata for '{sanitized_sequence}'"
            )
          else:
            raise VideoConversionError(
              f"Expected bin_data stream at index 3 in '{source}' but found '{file.streams[3].codec_name}'"
            )
        elif len(file.streams) == 3:
          raise VideoConversionError(
            f"Unsupported stream layout in '{source}': expected 2 streams (video+audio) or at least 4 streams (video+audio+extra+telemetry), but found {len(file.streams)} stream(s)"
          )
        else:
          ffmpeg_cmd = f"{ffmpeg_cmd} {quoted_destination}"
          bash_command(ffmpeg_cmd, f"{'converting' if convert else 'concatenating'} sequence '{sanitized_sequence}'")
          bash_command(
            f"exiftool -TagsFromFile {quoted_source} -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate {quoted_destination}",
            f"copying metadata for '{sanitized_sequence}'"
          )

        try:
          # Atomic when source/destination are on the same filesystem; ensures completed outputs replace the final file.
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
            exc,
          )
      finally:
        if concat_path:
          cleanup_tracked_path(concat_path, "temporary concat file", unregister_temp_file)
        # Skip partial cleanup when the output is finalized or resume has skipped the sequence.
        if partial_destination and not conversion_successful:
          cleanup_tracked_path(partial_destination, "partial output", unregister_partial_output)
    except VideoConversionError:
      raise
    except (OSError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
      raise VideoConversionError(f"Error processing sequence '{sequence}' in '{path}': {exc}") from exc

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
    raise VideoConversionError(f"Unsupported codec/accelerator combination: {codec}/{accelerator}")

  return options

if __name__ == '__main__':

  try:
    configure_logging()
    reset_signal_state()
    configure_signal_handlers()
    args = arguments()

    # Validate that the videos path exists and is a directory
    videos_path = args["videos"]
    if not os.path.exists(videos_path):
      logger.error("The specified path does not exist: %s", videos_path)
      sys.exit(1)
    if not os.path.isdir(videos_path):
      logger.error("The specified path is not a directory: %s", videos_path)
      sys.exit(1)

    try:
      contents = os.listdir(args["videos"])
      contents.sort()
    except OSError as exc:
      raise VideoConversionError(f"Unable to list contents of '{videos_path}': {exc}") from exc

    # videostofolders now returns the list of sequences
    sequences = videostofolders(contents, args["videos"])

    # Skip conversion if there are no sequences to process
    if not sequences:
      logger.info("No video sequences to convert. Exiting.")
      sys.exit(0)

    options = getOptions(args["codec"], args["accelerator"])

    convertVideos(
      args["videos"],
      options,
      args["bitratemodifier"],
      args["mbits_max"],
      args["ratio_max"],
      args["convert"],
      resume=args["resume"],
      sequences=sequences,
    )
  except VideoConversionError as exc:
    logger.error("Conversion halted: %s", exc)
    sys.exit(1)
  except (OSError, PermissionError) as exc:
    logger.error("Filesystem error during processing: %s", exc)
    sys.exit(1)
  except KeyboardInterrupt:
    logger.info("Operation cancelled by user (Ctrl+C).")
    sys.exit(1)
  except Exception as exc:
    logger.exception("Unexpected error: %s", exc)
    sys.exit(1)
