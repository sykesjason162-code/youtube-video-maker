# 🎬 Audio + Images → Video Maker

Two lightweight Python scripts that use **ffmpeg** to turn audio files and images into videos. No heavy dependencies — just Python and ffmpeg.

---

## Files

| File | Purpose |
|---|---|
| `make_video.py` | Single video: one audio file + images at exact times |
| `batch_video.py` | Batch mode: whole folder of songs → one video each, same images |
| `config.json` | Example config for `make_video.py` |
| `batch_config.json` | Example config for `batch_video.py` |

---

## Requirements

- Python 3.7+
- ffmpeg (system install — not a pip package)

### Install ffmpeg

| OS | Command |
|---|---|
| macOS | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows | Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH |

---

## Setup (venv)

```bash
# Create the virtual environment
python -m venv venv

# Activate it
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# No pip installs needed — all dependencies are stdlib
# Just verify ffmpeg is accessible:
ffmpeg -version
```

To deactivate when you're done:
```bash
deactivate
```

---

## make_video.py — Single Video

Combine one audio file with images that appear at specific times.

### Usage

```bash
python make_video.py config.json
```

### Config format

```json
{
    "audio": "my_audio.mp3",
    "output": "my_video.mp4",
    "images": [
        { "file": "intro.jpg",  "start": 0  },
        { "file": "slide2.png", "start": 10 },
        { "file": "slide3.jpg", "start": 25 },
        { "file": "outro.png",  "start": 40 }
    ]
}
```

- `"start"` is in seconds. Decimals are fine (e.g. `10.5`).
- Each image shows from its `start` until the next image's `start`.
- The last image holds until the audio ends.
- Paths are relative to the config file's location.

---

## batch_video.py — Batch Mode

Process an entire folder of audio files at once. Every song gets the same images with smart relative positioning — so the layout automatically adapts to each song's length.

### Usage

```bash
python batch_video.py batch_config.json
```

### Config format

```json
{
    "audio_folder":  "songs/",
    "output_folder": "videos/",
    "audio_extensions": [".mp3", ".wav", ".flac", ".m4a", ".aac"],

    "images": [
        { "file": "images/intro.jpg",  "position": "start"                },
        { "file": "images/middle.jpg", "position": "fill"                  },
        { "file": "images/outro.jpg",  "position": "end",  "duration": 10 }
    ]
}
```

### Position types

| Position | Description |
|---|---|
| `"start"` | Anchors to the beginning of the song. Runs until the next segment. |
| `"fill"` | Stretches dynamically to fill all time between start and end segments. Only one allowed. |
| `"end"` | Anchors to the tail of the song. **Requires a `"duration"` field (seconds).** |
| `30` *(number)* | Absolute time — appears at exactly that second in every video. |

### Example: 10s intro / fill middle / 10s outro

```json
"images": [
    { "file": "intro.jpg",  "position": "start"               },
    { "file": "middle.jpg", "position": "fill"                 },
    { "file": "outro.jpg",  "position": "end",  "duration": 10 }
]
```

For a **3-minute song** (180s):
```
intro.jpg   →   0s to  10s  (10s)
middle.jpg  →  10s to 170s  (160s)
outro.jpg   → 170s to 180s  (10s)
```

For a **4-minute song** (240s):
```
intro.jpg   →   0s to  10s  (10s)
middle.jpg  →  10s to 230s  (220s)
outro.jpg   → 230s to 240s  (10s)
```

The middle image stretches automatically — no manual adjustment needed per song.

### What it prints while running

```
Found 12 audio file(s) in 'songs/'
Output folder: 'videos/'

[1/12] MySong  (214.3s)
  0.0s → 10.0s   (10.0s)    intro.jpg
  10.0s → 204.3s (194.3s)   middle.jpg
  204.3s → 214.3s (10.0s)   outro.jpg
  Saved → videos/MySong.mp4 (28.4 MB)

[2/12] AnotherSong  (187.1s)
  ...
```

---

## Output

- All videos are rendered at **1920×1080**
- Images are automatically letterboxed/pillarboxed with black bars if needed
- Output format: H.264 video + AAC audio, `.mp4`

---

## Folder structure example

```
project/
├── make_video.py
├── batch_video.py
├── config.json
├── batch_config.json
├── requirements.txt
├── venv/
├── songs/
│   ├── track01.mp3
│   ├── track02.mp3
│   └── track03.flac
├── images/
│   ├── intro.jpg
│   ├── middle.jpg
│   └── outro.jpg
└── videos/
    ├── track01.mp4
    ├── track02.mp4
    └── track03.mp4
```
