#!/usr/bin/python3

import os
import sys
import argparse
import subprocess
import logging
from ffprobe import FFProbe
import shutil

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class VideoConversionError(Exception):
  """Raised when video conversion fails, chaining underlying errors."""

def arguments():

  parser = argparse.ArgumentParser(description="GoPro video compressor", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-v", "--videos", required=True, help="Path to the videos folder")
  parser.add_argument("-c", "--codec", type=str, default="h265", choices=['h265', 'h264'], help="Choose codec (default: h265)")
  parser.add_argument("-a", "--accelerator", type=str, default="qsv", choices=['qsv', 'cpu'], help="Choose accelerator (default: qsv)")
  parser.add_argument("-C", "--convert", action="store_false", help="Disable video conversion")
  parser.add_argument("-mx", "--mbits_max", type=int, default=25, help="Max bitrate for conversion (default: 25)")
  parser.add_argument("-rx", "--ratio_max", type=float, default=0.70, help="Max ratio of bitrate for conversion (default: 0.70)")
  parser.add_argument("-bm", "--bitratemodifier", type=float, default=0.12, help="Bitrate modifier for conversion (default: 0.12)")
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

def calculateBitrate(source, bitratemodifier, mbits_max, ratio_max):

  try:
    file = FFProbe(source)
    if not file.streams:
      raise VideoConversionError(f"No streams found in source file '{source}'")

    match file.streams[0].coded_height:
      case "1080":
        bitrate = 14680064
      case "1520":
        bitrate = 18874368
      case "2160":
        bitrate = 23068672
      case _:
        bitrate = int(round(int(file.streams[0].coded_height) * int(file.streams[0].coded_width) * int(file.streams[0].framerate * bitratemodifier)))

    bitrate_limit = int(round(int(file.streams[0].bit_rate) * ratio_max))

    if bitrate > bitrate_limit:
      bitrate = bitrate_limit

    if bitrate > mbits_max * 1024 * 1024:
      bitrate = mbits_max * 1024 * 1024

    result = bitrate
    return result
  except VideoConversionError:
    raise
  except FileNotFoundError as exc:
    raise VideoConversionError(f"Source file not found while probing '{source}': {exc}") from exc
  except (OSError, ValueError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
    raise VideoConversionError(f"Failed to calculate bitrate for '{source}': {exc}") from exc

def videostofolders(contents, path):

  # Checking if there is anything to move
  if any(".MP4" in word for word in contents) or any(".mp4" in word for word in contents):
    print("There is something to sort")
  else:
    print("There is nothing to sort")
    return []

  files = []
  # Selecting only files to be moved
  for content in contents:
    if "MP4" in content or "mp4" in content:
      files.append(content)

  # Getting all unique sequences
  listOfSequences = []
  for file in files:
    if "GH" in file or "GX" in file:
      if file[4:][:-4] not in listOfSequences:
        listOfSequences.append(file[4:][:-4])
    elif file[:-4] not in listOfSequences:
      listOfSequences.append(file[:-4])

  try:
    # Creating folders for each sequence
    for sequence in listOfSequences:
      os.makedirs(path + "/" + sequence, exist_ok=True)

    # Moving files to their respective folders
    for sequence in listOfSequences:
      for file in files:
        if sequence in file:
          os.rename(path + "/" + file, path + "/" + sequence + '/' + file)
  except OSError as exc:
    raise VideoConversionError(f"Failed to organize videos in '{path}': {exc}") from exc

  return listOfSequences

def convertVideos(path, options, bitratemodifier, mbits_max, ratio_max, convert, sequences=None):

  # Use provided sequences list or fall back to directory listing
  try:
    if sequences is not None:
      _listOfSequences = sequences
    else:
      _listOfSequences = os.listdir(path)
      _listOfSequences.sort()
  except OSError as exc:
    raise VideoConversionError(f"Unable to list sequences in '{path}': {exc}") from exc

  print("List: ")
  print(*_listOfSequences, sep = ", ")
  for sequence in _listOfSequences:
    try:
      files = os.listdir(path + "/" + sequence)
      files.sort()
      if not files:
        raise VideoConversionError(f"No video files found in sequence '{sequence}'")
      source = str(path + "/" + sequence + '/' + files[0])
      destination = str(path + '/' + files[0])
      bitrate = calculateBitrate(source, bitratemodifier, mbits_max, ratio_max)
      print()
      print()
      print()
      print("Sequence: " + sequence)
      file = FFProbe(source)
      if convert:
        if len(file.streams) >= 4:
          if file.streams[3].codec_name == 'bin_data':
            bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) ' + options + ' -b:v ' + str(bitrate) + ' -maxrate ' + str(bitrate * 1.5) + ' -bitrate_limit 0 -bufsize ' + str(bitrate * 4) + ' -fps_mode passthrough -g 120 -preset slower -look_ahead 1 -map 0:0 -map 0:1 -map 0:3 ' + destination, f"converting sequence '{sequence}'")
            bash_command('udtacopy ' + source + ' ' + destination, f"copying telemetry for '{sequence}'")
            bash_command('exiftool -TagsFromFile ' + source + ' -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate ' + destination, f"copying metadata for '{sequence}'")
          else:
            raise VideoConversionError(f"Expected bin_data stream at index 3 in '{source}' but found '{file.streams[3].codec_name}'")
        elif len(file.streams) == 3:
          raise VideoConversionError(
            f"Stream index 3 not found in '{source}' (only {len(file.streams)} stream(s) available); bin_data stream requires at least 4 streams"
          )
        else:
          bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) ' + options + ' -b:v ' + str(bitrate) + ' -maxrate ' + str(bitrate * 1.5) + ' -bitrate_limit 0 -bufsize ' + str(bitrate * 4) + ' -fps_mode passthrough -g 120 -preset slower -look_ahead 1 -map 0:0 -map 0:1 ' + destination, f"converting sequence '{sequence}'")
      else:
        if len(file.streams) >= 4:
          if file.streams[3].codec_name == 'bin_data':
            bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) -c copy -map 0:0 -map 0:1 -map 0:3 ' + destination, f"concatenating sequence '{sequence}'")
            bash_command('udtacopy ' + source + ' ' + destination, f"copying telemetry for '{sequence}'")
            bash_command('exiftool -TagsFromFile ' + source + ' -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate ' + destination, f"copying metadata for '{sequence}'")
          else:
            raise VideoConversionError(f"Expected bin_data stream at index 3 in '{source}' but found '{file.streams[3].codec_name}'")
        elif len(file.streams) == 3:
          raise VideoConversionError(
            f"Stream index 3 not found in '{source}' (only {len(file.streams)} stream(s) available); bin_data stream requires at least 4 streams"
          )
        else:
          bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) -c copy -map 0:0 -map 0:1 ' + destination, f"concatenating sequence '{sequence}'")
          bash_command('exiftool -TagsFromFile ' + source + ' -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate ' + destination, f"copying metadata for '{sequence}'")
      shutil.copystat(source, destination)
    except VideoConversionError:
      raise
    except (OSError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
      raise VideoConversionError(f"Error processing sequence '{sequence}' in '{path}': {exc}") from exc

def getOptions(codec, accelerator):

  options = None
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

    convertVideos(args["videos"], options, args["bitratemodifier"], args["mbits_max"], args["ratio_max"], args["convert"], sequences)
  except VideoConversionError as exc:
    logger.error("%s", exc)
    sys.exit(1)
  except (OSError, PermissionError) as exc:
    logger.error("Filesystem error during processing: %s", exc)
    sys.exit(1)
  except Exception as exc:
    logger.exception("Unexpected error: %s", exc)
    sys.exit(1)
