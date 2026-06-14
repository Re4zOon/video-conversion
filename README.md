# GoPro Video Compressor

A Python tool for organizing and compressing GoPro videos using FFmpeg. It automatically sorts multi-part GoPro video sequences into folders and concatenates/compresses them with hardware or software encoding.

## Features

- **Automatic Organization**: Sorts GoPro video files into sequence-based folders
- **Video Concatenation**: Merges multi-part GoPro recordings into single files
- **Hardware Acceleration**: Supports Intel Quick Sync Video (QSV) for faster encoding
- **Codec Options**: H.265 (HEVC) and H.264 encoding support
- **Metadata Preservation**: Retains original timestamps and GoPro telemetry data
- **Configurable Bitrate**: Automatic bitrate calculation based on resolution with customizable limits

## Prerequisites

### System Requirements

- Python 3.10+ (uses match-case syntax)
- Linux/Unix shell environment (the script uses `/bin/bash` for video commands)
- Enough free disk space for temporary concat files and converted output files

### Python Dependencies

```bash
python -m pip install -r requirements.txt
```

### Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### External Tools

- **ffmpeg**: Required for concatenation and conversion
- **exiftool**: Required for copying timestamps and metadata back to converted files
- **Intel Media Driver / VA-API tools**: Required only when using the default `--accelerator qsv`
- **udtacopy**: Optional; used when copying GoPro telemetry data in concat-only mode

## Installation

1. Install system packages.

   Debian/Ubuntu:
   ```bash
   sudo apt update
   sudo apt install python3 python3-venv python3-pip ffmpeg libimage-exiftool-perl
   ```

   Fedora:
   ```bash
   sudo dnf install python3 python3-pip ffmpeg perl-Image-ExifTool
   ```

   macOS with Homebrew:
   ```bash
   brew install python ffmpeg exiftool
   ```

   If you plan to use Intel Quick Sync Video (the default accelerator), also install the Intel media driver for your distribution. On Ubuntu this is commonly:
   ```bash
   sudo apt install vainfo intel-media-va-driver-non-free
   ```

2. Clone the repository:
   ```bash
   git clone https://github.com/re4zoon-team/video-conversion.git
   cd video-conversion
   ```

3. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   ```

4. Install Python dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

5. Verify the installation:
   ```bash
   python --version
   python -c "from ffprobe import FFProbe; print('ffprobe-python OK')"
   ffmpeg -version
   exiftool -ver
   python video.py --help
   ```

6. Choose an accelerator before the first long conversion:
   - Use the default `-a qsv` only on systems with Intel Quick Sync support and working VA-API drivers.
   - Use `-a cpu` when QSV is not available or when you want the most portable option.

## Docker Deployment

Build the container image from the repository root:

```bash
docker build -t video-conversion .
```

Run the converter by bind-mounting a host folder at `/data`. CPU encoding is the
most portable option:

```bash
docker run --rm -it \
  -v "$PWD/videos:/data" \
  video-conversion -v /data -a cpu
```

The image uses `python /app/video.py` as its entry point, so any CLI option can be
passed directly after the image name:

```bash
docker run --rm -it \
  -v "$PWD/videos:/data" \
  video-conversion -v /data -c h264 -a cpu --resume
```

For Intel Quick Sync Video acceleration on Linux hosts, pass the DRM device into
the container and keep the default `qsv` accelerator:

```bash
docker run --rm -it \
  --device /dev/dri:/dev/dri \
  -v "$PWD/videos:/data" \
  video-conversion -v /data
```

If the mounted video folder is not writable by the container's default user, run
with your host user and group IDs:

```bash
docker run --rm -it \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/videos:/data" \
  video-conversion -v /data -a cpu
```

## Usage

```bash
python video.py -v /path/to/videos [options]
```

For an interactive terminal interface:

```bash
python video.py --tui
```

### Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--videos` | `-v` | *required* | Path to the videos folder |
| `--tui` |  | disabled | Launch a terminal interface for choosing a folder and conversion options |
| `--codec` | `-c` | `h265` | Video codec (`h265` or `h264`) |
| `--accelerator` | `-a` | `qsv` | Encoding method (`qsv` for Intel QuickSync, `cpu` for software) |
| `--convert` | `-C` | enabled | Disable to skip video conversion (concatenate only) |
| `--mbits_max` | `-mx` | `25` | Maximum bitrate in Mbps |
| `--ratio_max` | `-rx` | `0.70` | Maximum ratio of original bitrate |
| `--bitratemodifier` | `-bm` | `0.12` | Bitrate calculation modifier |
| `--resume` | `-R` | disabled | Skip sequences that already have output files |

### Examples

Compress videos with H.265 using Intel QSV:
```bash
python video.py -v /path/to/gopro/videos
```

Use software encoding with H.264:
```bash
python video.py -v /path/to/videos -c h264 -a cpu
```

Concatenate only (no re-encoding):
```bash
python video.py -v /path/to/videos -C
```

Set maximum bitrate to 15 Mbps:
```bash
python video.py -v /path/to/videos -mx 15
```

Open the terminal interface:
```bash
python video.py --tui
```

### Terminal Interface

The TUI uses the Python standard-library `curses` module and does not require extra
dependencies. It provides:

- Video folder selection
- H.265/H.264 codec choice
- QSV/CPU accelerator choice
- Conversion and resume toggles
- Start/quit controls
- Sequence progress and runtime error messages

Use the arrow keys to move between fields, `Enter` to edit or toggle a value, and
`q` to quit. While a conversion is running, use `Ctrl+C` to stop; temporary and
partial files are cleaned up the same way as the CLI mode.

### Interruptions and Resume

- Press `Ctrl+C` or send `SIGTERM` to stop conversion. Temporary concat files and partial outputs are cleaned up on interruption.
- Use `--resume` to skip sequences that already have converted output files from a previous run. FFmpeg does not support mid-file resume, so interrupted conversions restart from the beginning.
- If an output file already exists, the tool prompts to overwrite, rename, or cancel (unless `--resume` is used).

## How It Works

### 1. Video Organization

GoPro cameras create file sequences with naming conventions like:
- `GH010001.MP4`, `GH020001.MP4`, ... (Hero cameras)
- `GX010001.MP4`, `GX020001.MP4`, ... (Hero cameras with GPS)

The tool extracts the sequence identifier (e.g., `0001`) and groups related files into folders.

### 2. Concatenation & Conversion

For each sequence folder:
1. Files are concatenated using FFmpeg's concat demuxer
2. Video is re-encoded (if conversion enabled) with calculated bitrate
3. Metadata (timestamps) are preserved using exiftool
4. GoPro telemetry data (bin_data stream) is optionally preserved

### Bitrate Calculation

The target bitrate is calculated based on:
- Video resolution (preset values for 1080p, 1520p, 4K)
- Frame rate and pixel count for non-standard resolutions
- Limited by `ratio_max` (percentage of original bitrate)
- Capped at `mbits_max` megabits per second

## File Structure

```
videos_folder/
├── GH010001.MP4          # Before: loose video files
├── GH020001.MP4
├── GX010002.MP4
└── GX020002.MP4

videos_folder/            # After: organized and converted
├── 0001/
│   ├── GH010001.MP4
│   └── GH020001.MP4
├── 0002/
│   ├── GX010002.MP4
│   └── GX020002.MP4
├── GH010001.MP4          # Converted output files
└── GX010002.MP4
```

## Troubleshooting

### `ffmpeg: command not found`

Install FFmpeg with your package manager, then open a new shell and run:
```bash
ffmpeg -version
```

If the command still is not found, confirm that the installation directory is on your `PATH`.

### `exiftool: command not found`

Install ExifTool, then verify it:
```bash
exiftool -ver
```

Package names vary by platform:
- Debian/Ubuntu: `libimage-exiftool-perl`
- Fedora: `perl-Image-ExifTool`
- macOS/Homebrew: `exiftool`

### `ModuleNotFoundError: No module named 'ffprobe'`

Install the Python dependencies in the same environment that runs the script:
```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "from ffprobe import FFProbe; print('ffprobe-python OK')"
```

If you are not using a virtual environment, replace `python` with the exact interpreter used to run `video.py`.

### Permission denied errors

The tool needs read/write access to the videos folder because it organizes source files into sequence folders and writes converted output files next to them.

Check ownership and permissions:
```bash
ls -ld /path/to/videos
ls -l /path/to/videos | head
```

Run the tool from a user account that owns the files, or copy the GoPro files into a writable working folder before converting. Avoid running with `sudo` unless the video folder is intentionally root-owned, because root-created output files can cause later permission problems.

### Intel QSV not working

The default accelerator is `qsv`. If your system does not have Intel Quick Sync support or the media driver is missing, FFmpeg may fail with encoder or device errors.

Check VA-API and QSV encoder support:
```bash
vainfo
ffmpeg -hide_banner -encoders | grep -E 'qsv|hevc_qsv|h264_qsv'
```

Install the Intel media driver if needed:
```bash
sudo apt install intel-media-va-driver-non-free
```

If hardware encoding is still unavailable, rerun with software encoding:
```bash
python video.py -v /path/to/videos -a cpu
```

Software encoding is slower, but it avoids QSV driver and hardware requirements.

### "More than 2 streams, but no bin_data"

This error occurs when a video has additional streams that aren't recognized as GoPro telemetry. The tool expects stream index 3 to be `bin_data` for GoPro files with telemetry.

Try these options:
- Confirm the input files are original GoPro MP4 files and were not modified by another editor first.
- Use `ffprobe /path/to/file.MP4` to inspect the stream layout.
- Run with `-C` to concatenate without re-encoding if you only need a joined file.
- Open an issue with the `ffprobe` stream output if the file is from a supported GoPro camera but still fails.

### Metadata copy warnings

If file metadata (timestamps/permissions) cannot be copied after conversion, the tool logs a warning but keeps the converted output file.

Common causes include read-only files, restrictive directory permissions, files stored on network drives, or missing ExifTool. Verify `exiftool -ver` and test in a local writable folder if the warning appears on external storage.

### Conversion was interrupted

Pressing `Ctrl+C` or receiving `SIGTERM` removes tracked temporary files and partial outputs. To continue later, rerun with:
```bash
python video.py -v /path/to/videos --resume
```

The resume option skips sequences that already have output files. It does not continue from the middle of a partially encoded file because FFmpeg restarts interrupted conversions from the beginning.

### Existing output file prompt appears

When a target output file already exists, choose overwrite, rename, or cancel at the prompt. For unattended reruns, use `--resume` to skip completed outputs instead of prompting.

### Need more detail for debugging

Enable debug logging:
```bash
GOPRO_LOG_LEVEL=DEBUG python video.py -v /path/to/videos -a cpu
```

When asking for help, include:
- The command you ran
- Your operating system and Python version
- `ffmpeg -version`
- `exiftool -ver`
- The full error message or debug log excerpt

## License

This project is open source. Feel free to modify and distribute.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
