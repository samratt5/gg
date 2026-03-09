# 🎬 Viral Animal Video Pipeline

A **fully automated AI factory** that generates emotionally intense, viral-ready 9:16 short videos of animal moments — optimized for **TikTok, YouTube Shorts, and Instagram Reels**.

Designed to run indefinitely with **zero repetition across 50,000+ videos**.

---

## Pipeline Architecture

```
GitHub Actions (cron every 6h)
    │
    ▼
[1] Mistral small API
    └─ Generates: title, hook, script A/B, video prompt, emotion arc
    │
    ▼
[2] Wavel.ai TTS
    └─ Splits narration → generates 2 audio files → merges with 0.5s crossfade
    │
    ▼
[3] Kaggle GPU Notebook (T4)
    └─ Loads Wan2.1-I2V-1.3B
    └─ Generates 6-8 overlapping segments (48 frames each)
    └─ Crossfade-blends segments into one continuous shot
    └─ Exports raw MP4 (no audio, no captions)
    │
    ▼
[4] WhisperX (GitHub Actions runner)
    └─ Transcribes narration WAV → word-level timestamps → SRT
    └─ Formats into TikTok-style captions (≤3 words/line, emphasis detection)
    │
    ▼
[5] FFmpeg Assembler
    └─ Scales/crops to 480×854 (9:16)
    └─ Applies camera overlay (noise, timestamp, distortion, lens effects)
    └─ Merges audio track
    └─ Burns TikTok drawtext captions
    └─ Exports final H.264 MP4
    │
    ▼
[6] Memory Manager
    └─ Hashes script → stores in video_memory.json → blocks future duplicates
```

---

## Folder Structure

```
viral-animal-videos/
├── .github/
│   └── workflows/
│       └── video_pipeline.yml      ← GitHub Actions automation
├── src/
│   ├── __init__.py
│   ├── pipeline.py                 ← Main orchestrator
│   ├── script_generator.py         ← Mistral + mutation engine
│   ├── tts_generator.py            ← Wavel.ai TTS
│   ├── kaggle_runner.py            ← Kaggle API runner
│   ├── subtitle_generator.py       ← WhisperX + TikTok formatter
│   ├── video_assembler.py          ← FFmpeg assembler
│   └── memory_manager.py           ← Anti-repetition DB
├── config/
│   ├── __init__.py
│   └── settings.py                 ← All configuration
├── kaggle/
│   └── wan21_video_generator.ipynb ← Kaggle notebook (Wan2.1)
├── output/                         ← Final MP4s (git-ignored)
├── tmp/                            ← Temp files (git-ignored)
├── video_memory.json               ← Anti-repetition database
├── .env.example                    ← Environment variables template
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/YOUR_USER/viral-animal-videos.git
cd viral-animal-videos

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install system dependencies

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg fonts-dejavu-core

# macOS
brew install ffmpeg

# Windows
# Download FFmpeg from https://ffmpeg.org/download.html and add to PATH
```

### 3. Install WhisperX (GPU recommended)

```bash
pip install git+https://github.com/m-bain/whisperX.git
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required keys:
| Variable | Where to get it |
|---|---|
| `MISTRAL_API_KEY` | https://console.mistral.ai/ |
| `WAVEL_API_KEY` | https://wavel.ai/ |
| `KAGGLE_USERNAME` | Your Kaggle username |
| `KAGGLE_KEY` | Kaggle → Settings → API → Create New Token |

### 5. Set up Kaggle notebook

1. Go to [kaggle.com](https://kaggle.com) → Create new Notebook
2. Name it exactly as set in `config/settings.py` → `KAGGLE_KERNEL_SLUG` (default: `wan21-animal-video-gen`)
3. Enable GPU (T4 x2 recommended)
4. Enable Internet Access
5. The pipeline will auto-inject the video config and push the notebook on each run.

### 6. Test with dry run

```bash
python -m src.pipeline --dry-run
```

This runs only script generation (no API costs beyond Mistral).

### 7. Run full pipeline

```bash
python -m src.pipeline
```

### 8. Run multiple videos

```bash
python -m src.pipeline --count 4
```

---

## GitHub Actions Setup

### Add secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name | Value |
|---|---|
| `MISTRAL_API_KEY` | Your Mistral API key |
| `WAVEL_API_KEY` | Your Wavel.ai API key |
| `KAGGLE_USERNAME` | Your Kaggle username |
| `KAGGLE_KEY` | Your Kaggle API key |

### Trigger manually

Go to **Actions → Viral Animal Video Pipeline → Run workflow**

- Set `count` to number of videos (default: 1)
- Set `dry_run` to `true` to test without API calls

### Scheduled runs

The workflow runs automatically every **6 hours** (00:00, 06:00, 12:00, 18:00 UTC).

Edit `.github/workflows/video_pipeline.yml` to change the cron schedule.

---

## Video Specs

| Parameter | Value |
|---|---|
| Resolution | 480×854 (9:16 vertical) |
| FPS | 8 |
| Duration | 30–50 seconds |
| Codec | H.264 (libx264) |
| Audio | AAC 192kbps |
| Inference steps | 30 |
| Segments | 6–8 |
| Segment overlap | 8 frames (crossfade) |

---

## Camera Styles

Each video randomly uses one of these camera styles, each with specific overlays and distortions:

| Style | Overlay effects |
|---|---|
| CCTV fisheye | Fisheye distortion, timestamp, heavy grain |
| Doorbell camera | Vignette, timestamp, medium grain |
| Helmet cam | Vignette, bottom timestamp, light grain |
| Dashcam | Sharpen filter, GPS timestamp, minimal grain |
| Phone vertical | No timestamp, minimal grain |
| Bodycam | Unit ID overlay, medium grain |
| Security ceiling cam | Heavy vignette, timestamp, heavy grain |
| Baby monitor cam | Green tint, night-vision grain, temp display |
| Store surveillance | Timestamp, heavy grain |
| Bike handlebar cam | No timestamp, light grain |

---

## Anti-Repetition System

Every generated script is:

1. **Hashed** (SHA-256 of title + animal + scenario + location + camera)
2. **Checked** against `video_memory.json` before use
3. **Blocked** if the same animal × scenario combination already exists
4. **Stored** after successful video generation

The **prompt mutation engine** tracks which animals, scenarios, locations, triggers, and camera styles have been used and **biases toward unused combinations** before falling back to random selection.

This ensures unique videos even at 50,000+ scale.

---

## Emotional Retention System

Every script follows this pacing arc:

| Timestamp | Stage |
|---|---|
| 0–2s | **HOOK** — devastatingly emotional first line |
| 3–10s | **TENSION** — something feels wrong |
| 10–20s | **CONFUSION** — viewer questions what's happening |
| 20–30s | **EMOTIONAL PEAK** — the moment hits |
| 30–45s | **PAYOFF** — resolution or devastating twist |

---

## Cost Estimates

| Component | Estimated cost per video |
|---|---|
| Mistral small (1.4k tokens) | ~$0.001 |
| Wavel.ai TTS (2× ~200 words) | ~$0.05–0.10 |
| Kaggle GPU T4 | Free (30h/week quota) |
| GitHub Actions | Free (2000 min/month) |
| **Total per video** | **~$0.05–0.15** |

---

## Troubleshooting

**Kaggle notebook fails with OOM:**
- Reduce `FRAMES_PER_SEG` in `config/settings.py` from 48 to 32
- Reduce `NUM_SEGMENTS_MAX` from 8 to 6

**Wavel.ai returns 401:**
- Check `WAVEL_API_KEY` is set correctly
- Verify your Wavel.ai plan supports the selected voice ID

**WhisperX import error:**
- Install with: `pip install git+https://github.com/m-bain/whisperX.git`
- Requires `ffmpeg` on PATH

**FFmpeg `drawtext` fails with font error:**
- Ensure `fonts-dejavu-core` is installed
- Or set a custom `font_path` in the `generate_subtitles()` call

**Duplicate script warning loops:**
- Your `video_memory.json` may have many records. This is expected behavior.
- The system will still find unique combos from the large pool of 37 animals × 20 scenarios × 15 locations × 12 triggers × 10 cameras = **1,332,000+ unique combinations**.

---

## License

MIT — use freely, credit appreciated.
