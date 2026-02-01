#!/usr/bin/python3

import os
import sys
import argparse
import subprocess
from ffprobe import FFProbe
import shutil

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

def bash_command(cmd):
  subprocess.run(['/bin/bash', '-c', cmd])

def calculateBitrate(source, bitratemodifier, mbits_max, ratio_max):

  file = FFProbe(source)

  match file.streams[0].coded_height:
    case "1080":
      bitrate = 14680064
    case "1520":
      bitrate = 18874368
    case "2160":
      bitrate = 23068672
    case _:
      bitrate = int(round(int(file.streams[0].coded_height) * int(file.streams[0].coded_width) * int(file.streams[0].framerate * bitratemodifier)))

  bitrate_limit = int(round(int(file.streams[0].bit_rate)*ratio_max))

  if bitrate > bitrate_limit:
    bitrate = bitrate_limit

  if bitrate > mbits_max*1024*1024:
    bitrate = mbits_max*1024*1024

  result = bitrate
  return result

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

  # Creating folders for each sequence
  for sequence in listOfSequences:
    os.makedirs(path + "/" + sequence, exist_ok=True)

  # Moving files to their respective folders
  for sequence in listOfSequences:
    for file in files:
      if sequence in file:
        os.rename(path + "/" + file, path + "/" + sequence + '/' + file)

  return listOfSequences

def convertVideos(path, options, bitratemodifier, mbits_max, ratio_max, convert, sequences=None):

  # Use provided sequences list or fall back to directory listing
  if sequences is not None:
    _listOfSequences = sequences
  else:
    _listOfSequences = os.listdir(path)
    _listOfSequences.sort()

  print("List: ")
  print(*_listOfSequences, sep = ", ")
  for sequence in _listOfSequences:
    files = os.listdir(path + "/" + sequence)
    files.sort()
    source = str(path + "/" + sequence + '/' + files[0])
    destination = str(path + '/' + files[0])
    bitrate = calculateBitrate(source, bitratemodifier, mbits_max, ratio_max)
    print()
    print()
    print()
    print("Sequence: " + sequence)
    file = FFProbe(source)
    if convert:
      if len(file.streams) > 2:
        if file.streams[3].codec_name == 'bin_data':
          bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) ' + options + ' -b:v ' + str(bitrate) + ' -maxrate ' + str(bitrate*1.5) + ' -bitrate_limit 0 -bufsize ' + str(bitrate*4) +' -fps_mode passthrough -g 120 -preset slower -look_ahead 1 -map 0:0 -map 0:1 -map 0:3 ' + destination)
          bash_command('udtacopy ' + source + ' ' + destination)
          bash_command('exiftool -TagsFromFile ' + source + ' -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate ' + destination)
        else:
          print("More, than 2 streams, but no bin_data")
          exit(1)
      else:
        bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) ' + options + ' -b:v ' + str(bitrate) + ' -maxrate ' + str(bitrate*1.5) + ' -bitrate_limit 0 -bufsize ' + str(bitrate*4) +' -fps_mode passthrough -g 120 -preset slower -look_ahead 1 -map 0:0 -map 0:1 ' + destination)
    else:
      if len(file.streams) > 2:
        if file.streams[3].codec_name == 'bin_data':
          bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) -c copy -map 0:0 -map 0:1 -map 0:3 ' + destination)
          bash_command('udtacopy ' + source + ' ' + destination)
          bash_command('exiftool -TagsFromFile ' + source + ' -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate ' + destination)
        else:
          print("More, than 2 streams, but no bin_data")
          exit(1)
      else:
        bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) -c copy -map 0:0 -map 0:1 ' + destination)
        bash_command('exiftool -TagsFromFile ' + source + ' -CreateDate -MediaCreateDate -MediaModifyDate -ModifyDate ' + destination)
    shutil.copystat(source, destination)

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

  return options

if __name__ == '__main__':

  args = arguments()

  # Validate that the videos path exists and is a directory
  videos_path = args["videos"]
  if not os.path.exists(videos_path):
    print(f"Error: The specified path does not exist: {videos_path}", file=sys.stderr)
    sys.exit(1)
  if not os.path.isdir(videos_path):
    print(f"Error: The specified path is not a directory: {videos_path}", file=sys.stderr)
    sys.exit(1)

  contents = os.listdir(args["videos"])
  contents.sort()

  # videostofolders now returns the list of sequences
  sequences = videostofolders(contents, args["videos"])

  # Skip conversion if there are no sequences to process
  if not sequences:
    print("No video sequences to convert. Exiting.")
    sys.exit(0)

  options = getOptions(args["codec"], args["accelerator"])

  convertVideos(args["videos"], options, args["bitratemodifier"], args["mbits_max"], args["ratio_max"], args["convert"], sequences)
