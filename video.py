#!/usr/bin/python3

# atfs needs to be installed for shutil.copystat
import os
import argparse
import subprocess
from ffprobe import FFProbe
import shutil

listOfSequences = []

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
      mbits = 15
    case "1520":
      mbits = 20
    case "2160":
      mbits = 25
    case _:
      bitrate = int(file.streams[0].coded_height) * int(file.streams[0].coded_width) * int(file.streams[0].framerate)
      mbits = int(round(bitrate /1024/1024 * bitratemodifier))

  mbits_limit = int(round(int(file.streams[0].bit_rate)/1024/1024*ratio_max))

  if mbits > mbits_limit:
    mbits = mbits_limit

  if mbits > mbits_max:
    mbits = mbits_max

  result = mbits*1024*1024
  return result

def videostofolders(contents, path):

  # Checking if there is anything to move
  if any(".MP4" in word for word in contents) or any(".mp4" in word for word in contents):
    print("There is something to sort")
  else:
    print("There is nothing to sort")
    return

  files = []
  # Selecting only files to be moved
  for content in contents:
    if "MP4" in content or "mp4" in content:
      files.append(content)

  # Getting all unique sequences
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

def convertVideos(path, options, bitratemodifier, mbits_max, ratio_max):

  _listOfSequences = os.listdir(args["videos"])
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
    if len(file.streams) > 2:
      if file.streams[3].codec_name == 'bin_data':
        bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) ' + options + ' -b:v ' + str(bitrate) + ' -maxrate ' + str(bitrate*1.5) + ' -bitrate_limit 0 -bufsize ' + str(bitrate*4) +' -fps_mode passthrough -g 120 -preset slower -look_ahead 1 -map 0:0 -map 0:1 -map 0:3 ' + destination)
        bash_command('udtacopy ' + source + ' ' + destination)
      else:
        print("More, than 2 streams, but no bin_data")
        exit(1)
    else:
      bash_command('cd ' + path + "/" + sequence + ';ffmpeg -y -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) ' + options + ' -b:v ' + str(bitrate) + ' -maxrate ' + str(bitrate*1.5) + ' -bitrate_limit 0 -bufsize ' + str(bitrate*4) +' -fps_mode passthrough -g 120 -preset slower -look_ahead 1 -map 0:0 -map 0:1 ' + destination)
    shutil.copystat(source, destination)

def getOptions(codec, accelerator):

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

  contents = os.listdir(args["videos"])
  contents.sort()

  videostofolders(contents, args["videos"])

  options = getOptions(args["codec"], args["accelerator"])

  if args["convert"]:
    convertVideos(args["videos"], options, args["bitratemodifier"], args["mbits_max"], args["ratio_max"])
