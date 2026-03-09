"""
video_memory.json manager.

Stores hashes and metadata of every generated script to
prevent ANY repetition across 50,000+ videos.
"""

import json
import hashlib
import os
import time
from typing import Dict, Any, Optional
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import MEMORY_FILE


# ──────────────────────────────────────────────────────────────
# SCHEMA
# Each record:
# {
#   "hash": str,
#   "title": str,
#   "animal": str,
#   "scenario": str,
#   "location": str,
#   "camera_style": str,
#   "emotional_trigger": str,
#   "keywords": list[str],
#   "created_at": float  (unix timestamp)
# }
# ──────────────────────────────────────────────────────────────


def _load_memory() -> Dict[str, Any]:
    """Load memory from disk. Returns empty structure if missing."""
    if not os.path.exists(MEMORY_FILE):
        return {"hashes": [], "records": []}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_memory(memory: Dict[str, Any]) -> None:
    """Persist memory atomically."""
    tmp = MEMORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
    os.replace(tmp, MEMORY_FILE)


def compute_script_hash(script_data: Dict[str, Any]) -> str:
    """
    Deterministic hash from key content fields.
    Immune to whitespace or timestamp differences.
    """
    fingerprint = "|".join([
        script_data.get("title", "").lower().strip(),
        script_data.get("animal_type", "").lower().strip(),
        script_data.get("scenario", "").lower().strip(),
        script_data.get("location", "").lower().strip(),
        script_data.get("camera_style", "").lower().strip(),
    ])
    return hashlib.sha256(fingerprint.encode()).hexdigest()


def is_duplicate(script_data: Dict[str, Any]) -> bool:
    """
    Return True if this script (or a close variant) already exists.
    Checks:
      1. Exact hash match
      2. Same animal + same scenario (even different camera)
    """
    memory = _load_memory()
    new_hash = compute_script_hash(script_data)

    # 1. Exact hash
    if new_hash in memory["hashes"]:
        return True

    # 2. Same animal × scenario combo
    new_animal = script_data.get("animal_type", "").lower()
    new_scenario = script_data.get("scenario", "").lower()
    for record in memory["records"]:
        if (record.get("animal", "").lower() == new_animal
                and record.get("scenario", "").lower() == new_scenario):
            return True

    return False


def store_video_record(script_data: Dict[str, Any]) -> str:
    """
    Save a new record. Returns the hash.
    Should be called only after successful video generation.
    """
    memory = _load_memory()
    new_hash = compute_script_hash(script_data)

    if new_hash not in memory["hashes"]:
        memory["hashes"].append(new_hash)
        record = {
            "hash": new_hash,
            "title": script_data.get("title", ""),
            "animal": script_data.get("animal_type", ""),
            "scenario": script_data.get("scenario", ""),
            "location": script_data.get("location", ""),
            "camera_style": script_data.get("camera_style", ""),
            "emotional_trigger": script_data.get("emotional_trigger", ""),
            "keywords": _extract_keywords(script_data),
            "created_at": time.time(),
        }
        memory["records"].append(record)
        _save_memory(memory)

    return new_hash


def get_used_combinations() -> Dict[str, set]:
    """
    Return sets of used animals, scenarios, locations, camera styles.
    Used by the prompt mutation engine to bias away from overused combos.
    """
    memory = _load_memory()
    result: Dict[str, set] = {
        "animals": set(),
        "scenarios": set(),
        "locations": set(),
        "camera_styles": set(),
        "emotional_triggers": set(),
    }
    for record in memory["records"]:
        result["animals"].add(record.get("animal", ""))
        result["scenarios"].add(record.get("scenario", ""))
        result["locations"].add(record.get("location", ""))
        result["camera_styles"].add(record.get("camera_style", ""))
        result["emotional_triggers"].add(record.get("emotional_trigger", ""))
    return result


def get_recent_records(n: int = 20) -> list:
    """Return the N most recent records (for context injection into prompts)."""
    memory = _load_memory()
    records = sorted(memory["records"], key=lambda r: r.get("created_at", 0), reverse=True)
    return records[:n]


def get_stats() -> Dict[str, int]:
    """Return basic statistics about the memory."""
    memory = _load_memory()
    return {
        "total_videos": len(memory["records"]),
        "unique_hashes": len(memory["hashes"]),
    }


def _extract_keywords(script_data: Dict[str, Any]) -> list:
    """Pull keywords from title + hook for diversity tracking."""
    text = " ".join([
        script_data.get("title", ""),
        script_data.get("hook", ""),
        script_data.get("scenario", ""),
    ]).lower()
    stop = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "is", "was", "are", "were", "it", "its"}
    words = [w.strip(".,!?\"'") for w in text.split()]
    return list({w for w in words if len(w) > 3 and w not in stop})[:20]
