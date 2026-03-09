"""
config/settings.py — Central config for the viral video pipeline.
All secrets come from environment variables (GitHub Secrets / .env).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Mistral ───────────────────────────────────────────────────────────────────
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# ── Wavel TTS (no API key needed — public endpoint) ───────────────────────────
# Find more voices at https://wavel.ai/studio → inspect network tab for voiceId
WAVEL_VOICE_ID    = os.environ.get(
    "WAVEL_VOICE_ID",
    "waveltts_f5066419-beae-43c6-bf67-d8ad0cec52a5",   # default: emotional voice
)
WAVEL_CROSSFADE_MS = int(os.environ.get("WAVEL_CROSSFADE_MS", "500"))   # 0.5s

# ── Kaggle ────────────────────────────────────────────────────────────────────
KAGGLE_USERNAME      = os.environ.get("KAGGLE_USERNAME", "")
KAGGLE_KEY           = os.environ.get("KAGGLE_KEY", "")
KAGGLE_NOTEBOOK_SLUG = os.environ.get("KAGGLE_NOTEBOOK_SLUG", "")

# ── Retry / backoff ───────────────────────────────────────────────────────────
MAX_RETRIES  = int(os.environ.get("MAX_RETRIES",  "3"))
BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "2.0"))
BACKOFF_MAX  = float(os.environ.get("BACKOFF_MAX",  "30.0"))

# ── Paths ─────────────────────────────────────────────────────────────────────
TEMP_DIR   = os.environ.get("TEMP_DIR",   "/tmp/viral_pipeline")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")

# ── Video settings ────────────────────────────────────────────────────────────
VIDEO_FPS        = int(os.environ.get("VIDEO_FPS",        "8"))
VIDEO_RESOLUTION = os.environ.get("VIDEO_RESOLUTION",     "480p")
VIDEO_SEGMENTS   = int(os.environ.get("VIDEO_SEGMENTS",   "7"))
WHISPER_MODEL    = os.environ.get("WHISPER_MODEL",         "base")
