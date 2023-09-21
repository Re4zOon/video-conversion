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
  parser.add_argument("-c", "--convert", action="store_false", help="Disable video conversion")
  parser.add_argument("-bm", "--bitratemodifier", type=int, default=0.13, help="Bitrate modifier for conversion, defaults to 0.13")
  args = parser.parse_args()
  config = vars(args)
  return config

def bash_command(cmd):
  subprocess.run(['/bin/bash', '-c', cmd])

def calculateBitrate(sequence, path, modifier):

  file = FFProbe(path + "/" + sequence + '/GH01' + sequence + '.MP4')


  bitrate = (int(file.streams[0].coded_height) * int(file.streams[0].coded_width) * int(file.streams[0].framerate))
  mbits = int(round(bitrate /1024/1024 * modifier))

  if mbits > 25:
    mbits = 25
  result = str(mbits) + 'M'
  return result


def videostofolders(contents, path):

  # Checking if there is anything to move
  if any(".MP4" in word for word in contents):
    print("There is something to sort")
  else:
    print("There is nothing to sort")
    return

  files = []
  # Selecting only files to be moved
  for content in contents:
    if "MP4" in content:
      files.append(content)

  # Getting all unique sequences
  for file in files:
    if file[4:][:4] not in listOfSequences:
      listOfSequences.append(file[4:][:4])

  # Creating folders for each sequence
  for sequence in listOfSequences:
    os.makedirs(path + "/" + sequence, exist_ok=True)

  # Moving files to their respective folders
  for file in files:
    os.rename(path + "/" + file, path + "/" + file[4:][:4] + '/' + file)

def convertVideos(path, modifier):

  _listOfSequences = listOfSequences

  if len(_listOfSequences) == 0:
    _listOfSequences = os.listdir(args["videos"])

  _listOfSequences.sort()

  print("List: ")
  print(*_listOfSequences, sep = ", ")
  for sequence in _listOfSequences:
    source = str(path + "/" + sequence + '/GH01' + sequence + '.MP4')
    destination = str(path + '/GH01' + sequence + '.MP4')
    bitrate = calculateBitrate(sequence, path, modifier)
    print()
    print()
    print()
    print("Sequence: " + sequence)
    file = FFProbe(source)
    if file.streams[3].codec_name == 'bin_data':
      bash_command('cd ' + path + "/" + sequence + ';ffmpeg -f concat -safe 0 -i <(for f in *.MP4; do echo \"file \'$PWD/$f\'\"; done) -init_hw_device qsv=hw -c copy -c:v hevc_qsv -b:v ' + bitrate + ' -preset slow -map 0:0 -map 0:1 -map 0:3 ../GH01' + sequence + '.MP4')
      bash_command('udtacopy ' + source + ' ' + destination)
    else:
      bash_command('cd ' + path + "/" + sequence + ';ffmpeg -f concat -safe 0 -i <(for f in *.MP4; do echo \"file \'$PWD/$f\'\"; done) -init_hw_device qsv=hw -c copy -c:v hevc_qsv -b:v ' + bitrate + ' -preset slow -map 0:0 -map 0:1 ../GH01' + sequence + '.MP4')
    shutil.copystat(source, destination)

if __name__ == '__main__':

  args = arguments()

  contents = os.listdir(args["videos"])
  contents.sort()

  videostofolders(contents, args["videos"])

  if args["convert"]:
    convertVideos(args["videos"], args["bitratemodifier"])
