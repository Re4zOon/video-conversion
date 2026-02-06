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
- FFmpeg with QSV support (for hardware acceleration)
- Linux/Unix environment (uses bash commands)

### Python Dependencies

```bash
pip install ffprobe-python
```

### Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### External Tools

- **ffmpeg**: Video processing
- **exiftool**: Metadata handling
- **udtacopy** (optional): GoPro telemetry data copying

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Re4zOon/video-conversion.git
   cd video-conversion
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure FFmpeg and exiftool are installed:
   ```bash
   # Debian/Ubuntu
   sudo apt install ffmpeg exiftool
   
   # Fedora
   sudo dnf install ffmpeg perl-Image-ExifTool
   ```

## Usage

```bash
python video.py -v /path/to/videos [options]
```

### Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--videos` | `-v` | *required* | Path to the videos folder |
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

### Interruptions and Resume

- Press `Ctrl+C` or send `SIGTERM` to stop conversion. Temporary concat files and partial outputs are cleaned up on interruption.
- Use `--resume` to skip sequences that already have converted output files from a previous run. FFmpeg does not support mid-file resume, so interrupted conversions restart from the beginning.

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

### Intel QSV Not Working

Ensure Intel Media Driver is installed:
```bash
# Check for VA-API support
vainfo

# Install Intel media driver (Ubuntu)
sudo apt install intel-media-va-driver-non-free
```

### "More than 2 streams, but no bin_data"

This error occurs when a video has additional streams that aren't recognized as GoPro telemetry. The tool expects stream index 3 to be `bin_data` for GoPro files with telemetry.

### Metadata copy warnings

If file metadata (timestamps/permissions) cannot be copied after conversion, the tool logs a warning but keeps the converted output file.

## License

This project is open source. Feel free to modify and distribute.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
