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
  parser.add_argument("-g", "--gopro", action="store_false", help="Disable gopro specific stuff")
  parser.add_argument("-crf", "--crf-setting", type=int, default=25, help="CRF setting for target filesize (default: 25)")
  args = parser.parse_args()
  config = vars(args)
  return config

def bash_command(cmd):
  subprocess.run(['/bin/bash', '-c', cmd])

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
    if any("GH" in word for word in contents) or any("GX" in word for word in contents):
      if file[4:][:4] not in listOfSequences:
        listOfSequences.append(file[4:][:4])
    elif file[:4] not in listOfSequences:
      listOfSequences.append(file[:4])

  # Creating folders for each sequence
  for sequence in listOfSequences:
    os.makedirs(path + "/" + sequence, exist_ok=True)

  # Moving files to their respective folders
  for sequence in listOfSequences:
    for file in files:
      if any(sequence in word for word in file):
        os.rename(path + "/" + file, path + "/" + sequence + '/' + file)

def convertVideos(path, crf):

  _listOfSequences = os.listdir(args["videos"])
  _listOfSequences.sort()

  print("List: ")
  print(*_listOfSequences, sep = ", ")
  for sequence in _listOfSequences:
    files = os.listdir(path + "/" + sequence)
    files.sort()
    source = str(path + "/" + sequence + '/' + files[0])
    destination = str(path + '/' + files[0])
    print()
    print()
    print()
    print("Sequence: " + sequence)
    file = FFProbe(source)
    if file.streams[3].codec_name == 'bin_data':
      bash_command('cd ' + path + "/" + sequence + ';ffmpeg -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) -init_hw_device qsv=hw -c copy -c:v hevc_qsv -crf ' + crf + ' -preset slow -map 0:0 -map 0:1 -map 0:3 ' + destination)
      bash_command('udtacopy ' + source + ' ' + destination)
    else:
      bash_command('cd ' + path + "/" + sequence + ';ffmpeg -f concat -safe 0 -i <(for f in *; do echo \"file \'$PWD/$f\'\"; done) -init_hw_device qsv=hw -c copy -c:v hevc_qsv -crf ' + crf + ' -preset slow -map 0:0 -map 0:1 ' + destination)
    shutil.copystat(source, destination)

if __name__ == '__main__':

  args = arguments()

  contents = os.listdir(args["videos"])
  contents.sort()

  videostofolders(contents, args["videos"])

  if args["convert"]:
    convertVideos(args["videos"], args["crf-setting"])
