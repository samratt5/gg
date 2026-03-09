"""
TTS generation using Wavel.ai public endpoint (no API key required).

Pipeline:
  1. Split narration script into part_a and part_b
  2. POST each to https://wavel.ai/wp-json/custom/v1/synthesize-audio
  3. Decode base64 MP3 response → save to disk
  4. Merge with crossfade using pydub
  5. Normalize volume
  6. Trim/pad to match target video duration
  7. Return path to final WAV file
"""

import os
import sys
import time
import base64
from typing import Dict, Any

import requests
from pydub import AudioSegment
from pydub.effects import normalize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    WAVEL_VOICE_ID, WAVEL_CROSSFADE_MS,
    MAX_RETRIES, BACKOFF_BASE, BACKOFF_MAX, TEMP_DIR,
)

# ─────────────────────────────────────────────────────────────────────────────
# Wavel public endpoint — no API key needed
# ─────────────────────────────────────────────────────────────────────────────
WAVEL_URL   = "https://wavel.ai/wp-json/custom/v1/synthesize-audio"
WAVEL_LANG  = "en-US"

WAVEL_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://wavel.ai/",
    "Origin":  "https://wavel.ai",
}

os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# LOW-LEVEL API CALL
# ─────────────────────────────────────────────────────────────────────────────

def _request_tts(text: str, voice_id: str, label: str = "") -> str:
    """
    POST text to Wavel public endpoint.
    Decodes the base64 MP3 from response and saves to a temp file.
    Returns local file path to the saved MP3.
    """
    payload = {
        "lang":    WAVEL_LANG,
        "text":    text,
        "voiceId": voice_id,
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                WAVEL_URL,
                data=payload,           # form-encoded (NOT json=)
                headers=WAVEL_HEADERS,
                timeout=60,
            )
            resp.raise_for_status()

            data = resp.json()
            raw_b64 = data.get("base64Audio", "")

            if not raw_b64:
                raise ValueError(f"Empty base64Audio in response: {data}")

            # Strip data-URI prefix → "data:audio/mp3;base64,SUQz..."
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]

            audio_bytes = base64.b64decode(raw_b64)

            # Save to temp file as MP3
            tag = label.replace(" ", "_") if label else f"part_{attempt}"
            out_path = os.path.join(TEMP_DIR, f"tts_{tag}_{int(time.time())}.mp3")
            with open(out_path, "wb") as f:
                f.write(audio_bytes)

            print(
                f"[TTS] ✓ {label or 'audio'} saved: "
                f"{os.path.basename(out_path)} ({len(audio_bytes) // 1024} KB)"
            )
            return out_path

        except Exception as e:
            last_error = e
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[TTS] Attempt {attempt}/{MAX_RETRIES} failed: {e}. Retry in {wait}s …")
            time.sleep(wait)

    raise RuntimeError(
        f"Wavel TTS failed after {MAX_RETRIES} attempts: {last_error}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def _merge_with_crossfade(
    path_a: str, path_b: str, crossfade_ms: int
) -> AudioSegment:
    """Merge two audio files with a smooth crossfade."""
    seg_a = AudioSegment.from_mp3(path_a)
    seg_b = AudioSegment.from_mp3(path_b)
    merged = seg_a.append(seg_b, crossfade=crossfade_ms)
    return merged


def _normalize_audio(
    seg: AudioSegment, target_dbfs: float = -14.0
) -> AudioSegment:
    """Normalize to target loudness level (approx -14 LUFS for social platforms)."""
    delta = target_dbfs - seg.dBFS
    return seg.apply_gain(delta)


def _fit_to_duration(
    seg: AudioSegment, target_seconds: float
) -> AudioSegment:
    """
    Trim or pad audio to exactly target_seconds.
      - Trim: 300ms fade-out at cut point
      - Pad:  append silence
    """
    target_ms  = int(target_seconds * 1000)
    current_ms = len(seg)

    if current_ms > target_ms:
        seg = seg[:target_ms].fade_out(300)
    elif current_ms < target_ms:
        silence = AudioSegment.silent(duration=target_ms - current_ms)
        seg = seg + silence

    return seg


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_tts_audio(script: Dict[str, Any], output_prefix: str) -> str:
    """
    Generate, merge, normalize, and fit TTS audio for a full script.

    Args:
        script:         full script dict (needs script_part_a, script_part_b, duration)
        output_prefix:  file path prefix without extension

    Returns:
        Path to the final WAV file
    """
    part_a:          str   = script["script_part_a"]
    part_b:          str   = script["script_part_b"]
    target_duration: float = float(script["duration"])
    voice_id:        str   = script.get("voice_id", WAVEL_VOICE_ID)

    print(f"[TTS] Generating part A ({len(part_a)} chars) …")
    path_a = _request_tts(part_a, voice_id, label="part_a")

    print(f"[TTS] Generating part B ({len(part_b)} chars) …")
    path_b = _request_tts(part_b, voice_id, label="part_b")

    print("[TTS] Merging with crossfade …")
    merged = _merge_with_crossfade(path_a, path_b, WAVEL_CROSSFADE_MS)

    print("[TTS] Normalizing volume …")
    merged = _normalize_audio(merged)

    print(f"[TTS] Fitting to {target_duration}s …")
    merged = _fit_to_duration(merged, target_duration)

    final_path = f"{output_prefix}_narration.wav"
    merged.export(final_path, format="wav")
    print(f"[TTS] ✓ Final audio: {final_path} ({len(merged) / 1000:.1f}s)")

    # Cleanup temp MP3 parts
    for p in (path_a, path_b):
        try:
            os.remove(p)
        except OSError:
            pass

    return final_path


def get_audio_duration(wav_path: str) -> float:
    """Return duration in seconds of a WAV file."""
    seg = AudioSegment.from_wav(wav_path)
    return len(seg) / 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_script = {
        "script_part_a": (
            "He waited by the door every morning for three years. "
            "The same spot. The same hope."
        ),
        "script_part_b": (
            "Today, for the first time, she came back. "
            "And he didn't move. He just looked at her."
        ),
        "duration": 35,
    }

    path = generate_tts_audio(test_script, "/tmp/test_tts")
    duration = get_audio_duration(path)
    print(f"\nOutput : {path}")
    print(f"Duration: {duration:.1f}s")
