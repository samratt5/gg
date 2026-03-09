"""
Central configuration for the Viral Animal Video Pipeline.
All secrets loaded from environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import List

# ──────────────────────────────────────────────
# API KEYS  (loaded from environment)
# ──────────────────────────────────────────────
MISTRAL_API_KEY: str = os.environ.get("MISTRAL_API_KEY", "")
WAVEL_API_KEY: str = os.environ.get("WAVEL_API_KEY", "")
KAGGLE_USERNAME: str = os.environ.get("KAGGLE_USERNAME", "")
KAGGLE_KEY: str = os.environ.get("KAGGLE_KEY", "")

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
MEMORY_FILE = os.path.join(BASE_DIR, "video_memory.json")
OVERLAY_DIR = os.path.join(BASE_DIR, "overlays")
TEMP_DIR = os.path.join(BASE_DIR, "tmp")

# ──────────────────────────────────────────────
# MISTRAL GENERATION PARAMS
# ──────────────────────────────────────────────
MISTRAL_MODEL = "mistral-small-latest"
MISTRAL_TEMPERATURE = 1.4
MISTRAL_TOP_P = 0.98
MISTRAL_FREQUENCY_PENALTY = 1.2
MISTRAL_PRESENCE_PENALTY = 1.0
MISTRAL_MAX_TOKENS = 1800

# ──────────────────────────────────────────────
# VIDEO SPECS
# ──────────────────────────────────────────────
VIDEO_WIDTH = 480
VIDEO_HEIGHT = 854          # 9:16 at 480p
VIDEO_FPS = 8
VIDEO_DURATION_MIN = 30     # seconds
VIDEO_DURATION_MAX = 50     # seconds
SEGMENT_FRAMES = 48         # frames per segment (~6s at 8fps)
SEGMENT_OVERLAP = 8         # overlap frames for crossfade
NUM_SEGMENTS_MIN = 6
NUM_SEGMENTS_MAX = 8
WAN_INFERENCE_STEPS = 30

# ──────────────────────────────────────────────
# KAGGLE SETTINGS
# ──────────────────────────────────────────────
KAGGLE_KERNEL_SLUG = "wan21-animal-video-gen"   # set to your notebook slug
KAGGLE_DATASET_SLUG = ""                         # optional input dataset
KAGGLE_POLL_INTERVAL = 60   # seconds between status checks
KAGGLE_TIMEOUT = 3600       # 1 hour max wait

# ──────────────────────────────────────────────
# WAVEL TTS SETTINGS
# ──────────────────────────────────────────────
WAVEL_VOICE_ID = "en-US-Neural2-J"   # deep emotional male voice
WAVEL_SPEED = 0.92                    # slightly slower for gravitas
WAVEL_CROSSFADE_MS = 500              # ms crossfade between TTS parts

# ──────────────────────────────────────────────
# RETRY / BACKOFF
# ──────────────────────────────────────────────
MAX_RETRIES = 5
BACKOFF_BASE = 2            # exponential backoff base (seconds)
BACKOFF_MAX = 120           # cap backoff at 2 minutes

# ──────────────────────────────────────────────
# PROMPT MUTATION POOLS
# ──────────────────────────────────────────────
ANIMAL_TYPES: List[str] = [
    "golden retriever", "border collie", "labrador", "German shepherd",
    "husky", "beagle", "poodle", "dachshund", "pitbull", "rottweiler",
    "maine coon cat", "siamese cat", "tabby cat", "black cat",
    "horse", "wild mustang", "elephant", "wolf", "fox", "deer",
    "baby duck", "penguin", "sea otter", "chimpanzee", "gorilla",
    "lion cub", "bear cub", "baby elephant", "dolphin", "crow",
    "parrot", "owl", "rabbit", "pig", "cow", "goat", "sheep",
]

SCENARIOS: List[str] = [
    "owner leaving for the last time",
    "reuniting after years apart",
    "protecting a newborn baby",
    "rescuing from floodwater",
    "final goodbye at the vet",
    "recognizing a rescuer years later",
    "betrayed by owner then saved by stranger",
    "waiting at the door every day for months",
    "saving a drowning child",
    "refusing to leave injured companion",
    "comforting a grieving human",
    "escaping abuse and finding safety",
    "mother searching for lost baby",
    "two animals parting after years together",
    "animal hearing owner's voice on phone",
    "recognizing owner's scent after blindness",
    "carrying owner's lost item to rescue team",
    "guiding help to trapped person",
    "sitting vigil at owner's grave",
    "first meeting with forever family",
]

LOCATIONS: List[str] = [
    "suburban driveway at dawn",
    "hospital parking lot",
    "rural farm at sunset",
    "city shelter hallway",
    "beach at low tide",
    "snowy mountain trail",
    "apartment stairwell",
    "airport arrivals gate",
    "flooded street",
    "forest clearing at dusk",
    "suburban backyard",
    "nursing home corridor",
    "empty highway",
    "riverbank at sunrise",
    "children's playground",
]

EMOTIONAL_TRIGGERS: List[str] = [
    "unconditional love",
    "abandonment fear",
    "loyalty beyond death",
    "grief and loss",
    "unexpected forgiveness",
    "protective instinct",
    "desperate hope",
    "quiet heartbreak",
    "joyful reunion",
    "silent sacrifice",
    "maternal love",
    "betrayal and redemption",
]

CAMERA_STYLES: List[str] = [
    "CCTV fisheye",
    "doorbell camera",
    "helmet cam",
    "dashcam",
    "phone vertical recording",
    "bodycam",
    "security ceiling cam",
    "baby monitor cam",
    "store surveillance cam",
    "bike handlebar cam",
]

# Pacing markers injected into every script
PACING_TEMPLATE = {
    "0-2s": "HOOK",
    "3-10s": "TENSION BUILD",
    "10-20s": "CONFUSION / DOUBT",
    "20-30s": "EMOTIONAL PEAK",
    "30-45s": "PAYOFF",
}
