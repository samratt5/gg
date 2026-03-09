"""
TTS generation using Wavel.ai API.

Pipeline:
  1. Split narration script into part_a and part_b
  2. Generate each via Wavel.ai REST API with retry
  3. Merge with 0.5s crossfade using pydub
  4. Normalize volume
  5. Trim/pad to match target video duration
  6. Return path to final WAV file
"""

import os
import sys
import time
import tempfile
from typing import Dict, Any, Tuple

import requests

# pydub for audio processing (requires ffmpeg on PATH)
from pydub import AudioSegment
from pydub.effects import normalize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    WAVEL_API_KEY, WAVEL_VOICE_ID, WAVEL_SPEED, WAVEL_CROSSFADE_MS,
    MAX_RETRIES, BACKOFF_BASE, BACKOFF_MAX, TEMP_DIR,
)

WAVEL_BASE_URL = "https://api.wavel.ai"

os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# LOW-LEVEL API CALL
# ─────────────────────────────────────────────

def _request_tts(text: str, voice_id: str, speed: float) -> str:
    """
    Submit a TTS job to Wavel.ai and poll until done.
    Returns local file path to downloaded WAV.
    """
    headers = {
        "Authorization": f"Bearer {WAVEL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "voice": voice_id,
        "speed": speed,
        "output_format": "wav",
    }

    # ── Submit job ──────────────────────────────
    last_error = None
    job_id = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                f"{WAVEL_BASE_URL}/v1/tts/generate",
                headers=headers, json=payload, timeout=30
            )
            resp.raise_for_status()
            job_id = resp.json().get("job_id") or resp.json().get("id")
            break
        except Exception as e:
            last_error = e
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[TTS] Submit attempt {attempt} failed: {e}. Retry in {wait}s")
            time.sleep(wait)

    if not job_id:
        raise RuntimeError(f"Wavel TTS submit failed after {MAX_RETRIES} attempts: {last_error}")

    # ── Poll for completion ──────────────────────
    audio_url = None
    for _ in range(60):  # up to 5 minutes
        time.sleep(5)
        try:
            status_resp = requests.get(
                f"{WAVEL_BASE_URL}/v1/tts/status/{job_id}",
                headers=headers, timeout=15
            )
            status_resp.raise_for_status()
            data = status_resp.json()
            status = data.get("status", "")
            if status == "completed":
                audio_url = data.get("url") or data.get("audio_url")
                break
            elif status == "failed":
                raise RuntimeError(f"Wavel TTS job {job_id} failed: {data}")
        except RuntimeError:
            raise
        except Exception as e:
            print(f"[TTS] Poll error: {e}")

    if not audio_url:
        raise RuntimeError(f"Wavel TTS job {job_id} did not complete in time.")

    # ── Download ─────────────────────────────────
    out_path = os.path.join(TEMP_DIR, f"tts_{job_id}.wav")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            dl = requests.get(audio_url, timeout=60)
            dl.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(dl.content)
            return out_path
        except Exception as e:
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[TTS] Download attempt {attempt} failed: {e}. Retry in {wait}s")
            time.sleep(wait)

    raise RuntimeError("Wavel TTS download failed after retries.")


# ─────────────────────────────────────────────
# AUDIO PROCESSING
# ─────────────────────────────────────────────

def _merge_with_crossfade(path_a: str, path_b: str, crossfade_ms: int) -> AudioSegment:
    """Merge two audio files with crossfade."""
    seg_a = AudioSegment.from_wav(path_a)
    seg_b = AudioSegment.from_wav(path_b)
    merged = seg_a.append(seg_b, crossfade=crossfade_ms)
    return merged


def _normalize_audio(seg: AudioSegment, target_dbfs: float = -14.0) -> AudioSegment:
    """Normalize to target LUFS-ish level."""
    delta = target_dbfs - seg.dBFS
    return seg.apply_gain(delta)


def _fit_to_duration(seg: AudioSegment, target_seconds: float) -> AudioSegment:
    """
    Trim or pad audio to exactly target_seconds.
    Padding uses 300ms fade-out then silence.
    """
    target_ms = int(target_seconds * 1000)
    current_ms = len(seg)

    if current_ms > target_ms:
        # Trim with 300ms fade out at end
        seg = seg[:target_ms]
        seg = seg.fade_out(300)
    elif current_ms < target_ms:
        # Pad with silence
        silence = AudioSegment.silent(duration=target_ms - current_ms)
        seg = seg + silence

    return seg


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def generate_tts_audio(script: Dict[str, Any], output_prefix: str) -> str:
    """
    Generate, merge, normalize, and fit TTS audio.

    Args:
        script: the full script dict with script_part_a, script_part_b, duration
        output_prefix: file path prefix (no extension)

    Returns:
        Path to final WAV file
    """
    part_a: str = script["script_part_a"]
    part_b: str = script["script_part_b"]
    target_duration: float = float(script["duration"])

    voice = script.get("voice_id", WAVEL_VOICE_ID)
    speed = WAVEL_SPEED

    print(f"[TTS] Generating part A ({len(part_a)} chars)…")
    path_a = _request_tts(part_a, voice, speed)

    print(f"[TTS] Generating part B ({len(part_b)} chars)…")
    path_b = _request_tts(part_b, voice, speed)

    print("[TTS] Merging with crossfade…")
    merged = _merge_with_crossfade(path_a, path_b, WAVEL_CROSSFADE_MS)

    print("[TTS] Normalizing volume…")
    merged = _normalize_audio(merged)

    print(f"[TTS] Fitting to {target_duration}s…")
    merged = _fit_to_duration(merged, target_duration)

    final_path = f"{output_prefix}_narration.wav"
    merged.export(final_path, format="wav")
    print(f"[TTS] ✓ Saved: {final_path} ({len(merged)/1000:.1f}s)")

    # Cleanup temp files
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


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_script = {
        "script_part_a": "He waited by the door every morning for three years. The same spot. The same hope.",
        "script_part_b": "Today, for the first time, she came back. And he didn't move. He just looked at her.",
        "duration": 35,
    }
    path = generate_tts_audio(test_script, "/tmp/test_tts")
    print(f"Output: {path}")
