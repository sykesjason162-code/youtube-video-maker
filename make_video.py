#!/usr/bin/env python3
"""
make_video.py — Turn audio + images into a video.

USAGE:
    python make_video.py config.json

CONFIG FORMAT (config.json):
    {
        "audio": "my_audio.mp3",
        "output": "my_video.mp4",
        "images": [
            { "file": "intro.jpg",   "start": 0  },
            { "file": "slide2.png",  "start": 10 },
            { "file": "slide3.jpg",  "start": 25 },
            { "file": "outro.png",   "start": 40 }
        ]
    }

    - "start" is in seconds (decimals OK, e.g. 10.5)
    - Each image shows from its "start" until the next image's "start"
    - The last image holds until the audio ends
    - Audio and images can be in the same folder or use full paths

REQUIREMENTS:
    - Python 3.7+
    - ffmpeg installed and on your PATH
      Install: https://ffmpeg.org/download.html
               macOS:   brew install ffmpeg
               Ubuntu:  sudo apt install ffmpeg
               Windows: https://ffmpeg.org/download.html#build-windows
"""

import json
import os
import sys
import subprocess
import tempfile
import shutil


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg not found. Please install it:")
        print("  macOS:   brew install ffmpeg")
        print("  Ubuntu:  sudo apt install ffmpeg")
        print("  Windows: https://ffmpeg.org/download.html")
        sys.exit(1)


def get_audio_duration(audio_path):
    """Use ffprobe to get audio duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def load_config(config_path):
    with open(config_path) as f:
        config = json.load(f)

    # Resolve paths relative to the config file's directory
    base = os.path.dirname(os.path.abspath(config_path))

    audio = os.path.join(base, config["audio"])
    output = config.get("output", "output.mp4")
    if not os.path.isabs(output):
        output = os.path.join(base, output)

    images = []
    for img in config["images"]:
        path = os.path.join(base, img["file"])
        start = float(img["start"])
        images.append({"file": path, "start": start})

    return audio, output, images


def validate(audio, images):
    if not os.path.exists(audio):
        print(f"ERROR: Audio file not found: {audio}")
        sys.exit(1)
    for img in images:
        if not os.path.exists(img["file"]):
            print(f"ERROR: Image not found: {img['file']}")
            sys.exit(1)


def build_video(audio, output, images):
    duration = get_audio_duration(audio)
    print(f"Audio duration: {duration:.2f}s")

    # Sort images by start time
    images = sorted(images, key=lambda x: x["start"])

    # Assign end time for each image
    segments = []
    for i, img in enumerate(images):
        start = img["start"]
        end = images[i + 1]["start"] if i + 1 < len(images) else duration
        if start >= duration:
            print(f"WARNING: Image '{img['file']}' starts at {start}s but audio is only {duration:.2f}s — skipping.")
            continue
        end = min(end, duration)
        segments.append({"file": img["file"], "start": start, "end": end, "dur": end - start})

    if not segments:
        print("ERROR: No valid image segments to render.")
        sys.exit(1)

    print(f"\nImage schedule:")
    for s in segments:
        print(f"  {s['start']:6.2f}s → {s['end']:6.2f}s  ({s['dur']:.2f}s)  {os.path.basename(s['file'])}")

    # Build ffmpeg filter_complex
    # Each image is an input; we scale it and set a duration, then concatenate
    inputs = ["-i", audio]
    for s in segments:
        inputs += ["-loop", "1", "-t", str(s["dur"]), "-i", s["file"]]

    n = len(segments)

    # Scale all images to 1920x1080 (letterboxed/padded), then concat
    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i+1}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black[v{i}]"
        )

    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")
    filter_complex = "; ".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            "-pix_fmt", "yuv420p",
            output
        ]
    )

    print(f"\nBuilding video → {output}")
    print("(This may take a moment...)\n")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("ERROR: ffmpeg failed.\n")
        print(result.stderr[-3000:])  # last 3000 chars of error
        sys.exit(1)

    size_mb = os.path.getsize(output) / (1024 * 1024)
    print(f"Done! Output: {output} ({size_mb:.1f} MB)")


def make_example_config():
    """Write an example config.json if none exists."""
    example = {
        "audio": "audio.mp3",
        "output": "output.mp4",
        "images": [
            {"file": "image1.jpg", "start": 0},
            {"file": "image2.jpg", "start": 10},
            {"file": "image3.jpg", "start": 25}
        ]
    }
    with open("config.json", "w") as f:
        json.dump(example, f, indent=4)
    print("Created example config.json — edit it with your files and run again.")


if __name__ == "__main__":
    check_ffmpeg()

    if len(sys.argv) < 2:
        print(__doc__)
        print("\nNo config file provided.")
        if not os.path.exists("config.json"):
            make_example_config()
        else:
            print("Found config.json in current directory — using it.")
            audio, output, images = load_config("config.json")
            validate(audio, images)
            build_video(audio, output, images)
        sys.exit(0)

    config_path = sys.argv[1]
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    audio, output, images = load_config(config_path)
    validate(audio, images)
    build_video(audio, output, images)
