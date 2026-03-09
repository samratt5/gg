"""
Script generator using Mistral small API.

• High-entropy generation (temp 1.4, top_p 0.98)
• Prompt mutation engine rotates animal/scenario/location/trigger
• Anti-repetition guard via memory_manager
• Returns fully structured JSON script
"""

import json
import os
import random
import time
import sys
from typing import Dict, Any, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    MISTRAL_API_KEY, MISTRAL_MODEL, MISTRAL_TEMPERATURE, MISTRAL_TOP_P,
    MISTRAL_FREQUENCY_PENALTY, MISTRAL_PRESENCE_PENALTY, MISTRAL_MAX_TOKENS,
    ANIMAL_TYPES, SCENARIOS, LOCATIONS, EMOTIONAL_TRIGGERS, CAMERA_STYLES,
    PACING_TEMPLATE, VIDEO_DURATION_MIN, VIDEO_DURATION_MAX,
    MAX_RETRIES, BACKOFF_BASE, BACKOFF_MAX,
)
from src.memory_manager import (
    is_duplicate, get_used_combinations, get_recent_records, store_video_record
)

MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"

# ─────────────────────────────────────────────
# PROMPT MUTATION ENGINE
# ─────────────────────────────────────────────

def _weighted_choice(pool: list, used: set) -> str:
    """
    Pick from pool, strongly preferring items NOT yet used.
    Falls back to random if all used.
    """
    unused = [x for x in pool if x not in used]
    if unused:
        return random.choice(unused)
    return random.choice(pool)


def build_mutation_context() -> Dict[str, str]:
    """
    Build a diverse combo of animal / scenario / location / trigger / camera
    that has NOT been used recently.
    """
    used = get_used_combinations()

    animal = _weighted_choice(ANIMAL_TYPES, used["animals"])
    scenario = _weighted_choice(SCENARIOS, used["scenarios"])
    location = _weighted_choice(LOCATIONS, used["locations"])
    trigger = _weighted_choice(EMOTIONAL_TRIGGERS, used["emotional_triggers"])
    camera = _weighted_choice(CAMERA_STYLES, used["camera_styles"])
    duration = random.randint(VIDEO_DURATION_MIN, VIDEO_DURATION_MAX)

    return {
        "animal_type": animal,
        "scenario": scenario,
        "location": location,
        "emotional_trigger": trigger,
        "camera_style": camera,
        "duration": duration,
    }


def _build_system_prompt() -> str:
    return (
        "You are an elite viral short-video scriptwriter specializing in emotionally devastating "
        "animal moments. Your scripts make people stop scrolling and cry in seconds. "
        "You write ONLY in raw JSON. No markdown fences. No commentary. Pure JSON object."
    )


def _build_user_prompt(ctx: Dict[str, str], recent_records: list) -> str:
    # Build anti-repetition block from recent records
    recent_titles = [r.get("title", "") for r in recent_records[:10]]
    recent_block = "\n".join(f"  - {t}" for t in recent_titles) if recent_titles else "  (none yet)"

    pacing_block = "\n".join(f"  {k}: {v}" for k, v in PACING_TEMPLATE.items())

    return f"""Generate ONE viral short-video script with these EXACT specifications:

ANIMAL: {ctx['animal_type']}
SCENARIO: {ctx['scenario']}
LOCATION: {ctx['location']}
EMOTIONAL CORE: {ctx['emotional_trigger']}
CAMERA STYLE: {ctx['camera_style']}
DURATION: {ctx['duration']} seconds

RECENTLY USED TITLES (DO NOT REPEAT THESE THEMES):
{recent_block}

PACING STRUCTURE (follow exactly):
{pacing_block}

RULES:
1. The HOOK must hit within the first 2 seconds and be devastating.
2. script_part_a covers the first half of the video (tension → confusion).
3. script_part_b covers the second half (emotional peak → payoff).
4. video_prompt is a detailed cinematic description FOR the video generation AI.
   It must specify: the camera style ({ctx['camera_style']}), animal, action, 
   lighting, mood, and visual details. Written for Wan2.1-I2V diffusion model.
5. emotion_progression is an array of 5 strings: one per pacing stage.
6. The title must be under 60 characters and cause immediate emotional reaction.

Return ONLY this JSON schema, nothing else:
{{
  "title": "",
  "animal_type": "{ctx['animal_type']}",
  "scenario": "{ctx['scenario']}",
  "location": "{ctx['location']}",
  "emotional_trigger": "{ctx['emotional_trigger']}",
  "camera_style": "{ctx['camera_style']}",
  "duration": {ctx['duration']},
  "hook": "",
  "script_part_a": "",
  "script_part_b": "",
  "emotion_progression": ["", "", "", "", ""],
  "video_prompt": ""
}}"""


# ─────────────────────────────────────────────
# RETRY WRAPPER
# ─────────────────────────────────────────────

def _call_mistral_with_retry(messages: list) -> str:
    """
    Call Mistral API with exponential backoff retry.
    Returns raw string content.
    """
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": MISTRAL_TEMPERATURE,
        "top_p": MISTRAL_TOP_P,
        "max_tokens": MISTRAL_MAX_TOKENS,
        # Note: Mistral API uses different param names for penalties
        # frequency_penalty and presence_penalty may not be supported on all endpoints.
        # They are included here; the API will ignore unsupported ones.
        "random_seed": random.randint(0, 999999),
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(MISTRAL_ENDPOINT, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip()
        except requests.exceptions.HTTPError as e:
            last_error = e
            if resp.status_code in (401, 403):
                raise RuntimeError(f"Mistral auth error: {e}") from e
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[Mistral] Attempt {attempt} failed ({e}). Retrying in {wait}s…")
            time.sleep(wait)
        except Exception as e:
            last_error = e
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[Mistral] Attempt {attempt} failed ({e}). Retrying in {wait}s…")
            time.sleep(wait)

    raise RuntimeError(f"Mistral API failed after {MAX_RETRIES} attempts. Last error: {last_error}")


# ─────────────────────────────────────────────
# MAIN GENERATOR
# ─────────────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    """Strip any accidental markdown fences or preamble."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    # Find first { and last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in Mistral response.")
    return raw[start:end + 1]


def generate_script(max_duplicate_retries: int = 5) -> Dict[str, Any]:
    """
    Main entry point.
    Generates a fully unique, high-entropy script JSON.
    Retries with fresh mutation context if duplicate detected.
    """
    recent = get_recent_records(20)

    for dup_attempt in range(max_duplicate_retries):
        ctx = build_mutation_context()

        messages = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": _build_user_prompt(ctx, recent)},
        ]

        raw = _call_mistral_with_retry(messages)

        try:
            clean = _clean_json_response(raw)
            script = json.loads(clean)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ScriptGen] JSON parse failed: {e}. Raw:\n{raw[:300]}")
            continue

        # Validate required fields
        required = [
            "title", "hook", "script_part_a", "script_part_b",
            "video_prompt", "camera_style", "duration", "emotion_progression"
        ]
        if not all(k in script for k in required):
            print(f"[ScriptGen] Missing required fields. Got: {list(script.keys())}")
            continue

        # Fill in mutation context fields if Mistral omitted them
        for key in ("animal_type", "scenario", "location", "emotional_trigger", "camera_style"):
            if key not in script:
                script[key] = ctx[key]

        # Anti-repetition check
        if is_duplicate(script):
            print(f"[ScriptGen] Duplicate detected on attempt {dup_attempt + 1}. Regenerating…")
            continue

        print(f"[ScriptGen] ✓ Unique script: '{script['title']}'")
        return script

    raise RuntimeError(f"Could not generate unique script after {max_duplicate_retries} attempts.")


def finalize_and_store(script: Dict[str, Any]) -> str:
    """
    Call this after the FULL video is successfully generated
    to lock in the record and prevent future duplicates.
    """
    return store_video_record(script)


if __name__ == "__main__":
    # Quick smoke test
    from dotenv import load_dotenv
    load_dotenv()
    s = generate_script()
    print(json.dumps(s, indent=2))
