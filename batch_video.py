#!/usr/bin/env python3
"""
batch_video.py — Make one video per song in a folder, all using the same images.

Supports smart relative positioning:
  - "start"  : image appears at the beginning (offset from 0)
  - "end"    : image appears relative to the END of the song
  - "fill"   : image fills all remaining space between other images
  - absolute : a plain number means a fixed second from the start

USAGE:
    python batch_video.py config.json

CONFIG FORMAT (config.json):
    {
        "audio_folder": "songs/",
        "output_folder": "videos/",
        "audio_extensions": [".mp3", ".wav", ".flac", ".m4a", ".aac"],

        "images": [
            { "file": "images/intro.jpg",   "position": "start" },
            { "file": "images/middle.jpg",  "position": "fill"  },
            { "file": "images/outro.jpg",   "position": "end",  "duration": 10 }
        ]
    }

POSITION TYPES:
    "start"             First image. Shows from 0s until the next image starts.
                        Duration = however long until next segment begins.

    "fill"              Middle image. Stretches to fill all time not covered
                        by start/end images. There can only be one "fill".

    "end"               Last image. Requires a "duration" field (seconds).
                        Shows for that many seconds at the tail of the song.

    <number>            Absolute start time in seconds from the beginning.
                        e.g. "position": 15  means it starts at 15s.

SIMPLE EXAMPLE — intro 10s, outro 10s, middle fills the rest:
    "images": [
        { "file": "intro.jpg",  "position": "start" },
        { "file": "middle.jpg", "position": "fill"  },
        { "file": "outro.jpg",  "position": "end", "duration": 10 }
    ]

    For a 3-minute song (180s):
        intro.jpg  → 0s   to 10s   (10s)
        middle.jpg → 10s  to 170s  (160s)
        outro.jpg  → 170s to 180s  (10s)

REQUIREMENTS:
    - Python 3.7+
    - ffmpeg installed and on your PATH
      macOS:   brew install ffmpeg
      Ubuntu:  sudo apt install ffmpeg
      Windows: https://ffmpeg.org/download.html
"""

import json
import os
import sys
import subprocess
import shutil
import glob


# ─── ffmpeg helpers ──────────────────────────────────────────────────────────

def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg not found. Please install it:")
        print("  macOS:   brew install ffmpeg")
        print("  Ubuntu:  sudo apt install ffmpeg")
        print("  Windows: https://ffmpeg.org/download.html")
        sys.exit(1)


def get_audio_duration(audio_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


# ─── Config loading ───────────────────────────────────────────────────────────

def load_config(config_path):
    with open(config_path) as f:
        config = json.load(f)

    base = os.path.dirname(os.path.abspath(config_path))

    audio_folder  = os.path.join(base, config["audio_folder"])
    output_folder = os.path.join(base, config.get("output_folder", "videos"))
    extensions    = config.get("audio_extensions", [".mp3", ".wav", ".flac", ".m4a", ".aac"])

    images = []
    for img in config["images"]:
        images.append({
            "file":     os.path.join(base, img["file"]),
            "position": img["position"],
            "duration": img.get("duration", None)
        })

    return audio_folder, output_folder, extensions, images


# ─── Segment resolver ─────────────────────────────────────────────────────────

def resolve_segments(images, total_duration):
    """
    Convert position definitions into concrete (start, end, dur) segments.

    Positions are processed in order:
      "start"  → begins at 0, ends where the next segment starts
      "fill"   → stretches to fill all time not covered by start/end images
      "end"    → anchored to the tail; requires "duration"
      <number> → absolute start time in seconds
    """

    # Validate
    fill_count = sum(1 for img in images if img["position"] == "fill")
    if fill_count > 1:
        print("ERROR: Only one image can have position 'fill'.")
        sys.exit(1)
    for img in images:
        if img["position"] in ("start", "end") and img["duration"] is None:
            print(f"ERROR: position '{img["position"]}' requires a 'duration' field: {img['file']}")
            sys.exit(1)

    # Calculate how much time start/end-anchored images consume
    end_total = sum(img["duration"] for img in images if img["position"] == "end")
    fill_end  = total_duration - end_total

    # Walk through images in order, tracking a cursor
    cursor = 0.0
    raw = []  # list of (file, start, end)

    for img in images:
        pos = img["position"]

        if pos == "start":
            dur = img["duration"]
            raw.append({"file": img["file"], "start": cursor, "end": cursor + dur})
            cursor += dur

        elif pos == "fill":
            raw.append({"file": img["file"], "start": cursor, "end": fill_end})
            cursor = fill_end

        elif pos == "end":
            dur   = img["duration"]
            start = total_duration - end_total
            end_total -= dur  # peel off so next "end" image stacks correctly
            raw.append({"file": img["file"], "start": start, "end": start + dur})

        elif isinstance(pos, (int, float)):
            raw.append({"file": img["file"], "start": float(pos), "end": None})
            cursor = float(pos)

        else:
            print(f"ERROR: Unknown position '{pos}' for {img['file']}")
            sys.exit(1)

    # Fix any segment whose end is still None: it ends where the next one starts
    for i, seg in enumerate(raw):
        if seg["end"] is None:
            next_start = raw[i + 1]["start"] if i + 1 < len(raw) else total_duration
            seg["end"] = next_start

    # Clip, compute dur, drop zero-length
    result = []
    for seg in raw:
        s = max(0.0, min(seg["start"], total_duration))
        e = max(s,   min(seg["end"],   total_duration))
        d = e - s
        if d > 0:
            result.append({"file": seg["file"], "start": s, "end": e, "dur": d})

    return result


# ─── Video builder ────────────────────────────────────────────────────────────

def build_video(audio_path, output_path, segments):
    """Run ffmpeg to combine segments into a video."""

    inputs = ["-i", audio_path]
    for s in segments:
        inputs += ["-loop", "1", "-t", str(s["dur"]), "-i", s["file"]]

    n = len(segments)

    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i+1}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1[v{i}]"
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
            output_path
        ]
    )

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  ERROR: ffmpeg failed for {os.path.basename(audio_path)}")
        print(result.stderr[-2000:])
        return False

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Saved → {output_path} ({size_mb:.1f} MB)")
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(config_path):
    check_ffmpeg()

    audio_folder, output_folder, extensions, images = load_config(config_path)

    # Validate images exist
    for img in images:
        if not os.path.exists(img["file"]):
            print(f"ERROR: Image not found: {img['file']}")
            sys.exit(1)

    # Find all audio files
    audio_files = []
    for ext in extensions:
        audio_files += glob.glob(os.path.join(audio_folder, f"*{ext}"))
        audio_files += glob.glob(os.path.join(audio_folder, f"*{ext.upper()}"))
    audio_files = sorted(set(audio_files))

    if not audio_files:
        print(f"ERROR: No audio files found in: {audio_folder}")
        print(f"  Looking for: {', '.join(extensions)}")
        sys.exit(1)

    os.makedirs(output_folder, exist_ok=True)

    print(f"Found {len(audio_files)} audio file(s) in '{audio_folder}'")
    print(f"Output folder: '{output_folder}'\n")

    success, failed = 0, []

    for i, audio_path in enumerate(audio_files, 1):
        name     = os.path.splitext(os.path.basename(audio_path))[0]
        out_path = os.path.join(output_folder, f"{name}.mp4")

        duration = get_audio_duration(audio_path)
        segments = resolve_segments(images, duration)

        print(f"[{i}/{len(audio_files)}] {name}  ({duration:.1f}s)")
        for s in segments:
            label = f"{s['start']:.1f}s → {s['end']:.1f}s  ({s['dur']:.1f}s)"
            print(f"  {label:<30}  {os.path.basename(s['file'])}")

        if build_video(audio_path, out_path, segments):
            success += 1
        else:
            failed.append(name)
        print()

    print(f"─── Done: {success}/{len(audio_files)} videos created ───")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    main(sys.argv[1])
