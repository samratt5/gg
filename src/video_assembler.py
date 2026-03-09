"""
Video assembler: merges raw MP4 + audio + camera overlays + captions into
the final TikTok-ready 9:16 vertical short video.

Steps:
  1. Scale and crop raw video to 480x854 (9:16)
  2. Apply camera-style overlay (timestamp, noise, distortion)
  3. Merge narration audio (replacing original)
  4. Burn TikTok-style captions via drawtext
  5. Export final H.264 MP4

FFmpeg must be on PATH.
"""

import os
import subprocess
import sys
import json
import random
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    OVERLAY_DIR, TEMP_DIR, OUTPUT_DIR,
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# FFMPEG RUNNER
# ─────────────────────────────────────────────

def _run_ffmpeg(args: List[str], desc: str = "") -> None:
    """Run an ffmpeg command and raise on failure."""
    cmd = ["ffmpeg", "-y"] + args
    print(f"[FFmpeg] {desc}: {' '.join(cmd[:8])}…")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed ({desc}):\nSTDERR:\n{result.stderr[-2000:]}"
        )


# ─────────────────────────────────────────────
# CAMERA OVERLAY BUILDERS
# ─────────────────────────────────────────────

def _get_timestamp_text(camera_style: str) -> str:
    """Fake timestamp appropriate for each camera type."""
    now = datetime.now()
    if "cctv" in camera_style.lower() or "security" in camera_style.lower():
        return now.strftime("%Y/%m/%d %H:%M:%S")
    elif "doorbell" in camera_style.lower():
        return now.strftime("%b %d  %H:%M")
    elif "dashcam" in camera_style.lower():
        return now.strftime("%Y-%m-%d %H:%M:%S  GPS:ON")
    elif "bodycam" in camera_style.lower():
        return now.strftime("REC %H:%M:%S  UNIT-04")
    elif "baby monitor" in camera_style.lower():
        return now.strftime("%H:%M:%S  TEMP:68°F")
    else:
        return now.strftime("%H:%M:%S")


def _camera_style_to_vf(camera_style: str, drawtext_captions: str, font_path: str) -> str:
    """
    Build the complete video filter chain for a given camera style.
    Includes: scale, crop, noise, distortion, timestamp, captions.
    """
    style_lower = camera_style.lower()
    ts_text = _get_timestamp_text(camera_style).replace(":", "\\:")
    ts_fontsize = 22

    # Base: scale to 9:16 with black padding if needed
    base_filters = [
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase",
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
    ]

    # Camera-specific distortions
    if "fisheye" in style_lower or "cctv" in style_lower:
        base_filters += [
            "lensfun=make=Nikon:model='Nikkor 28mm f/2.8D AF':lens='Nikkor 28mm f/2.8D AF'"
            ":mode=geometry:target_geometry=rectilinear",
        ]
        noise_strength = 18
        ts_color = "white@0.85"
        ts_x, ts_y = 10, 10
    elif "doorbell" in style_lower:
        base_filters += ["vignette=PI/5"]
        noise_strength = 12
        ts_color = "white@0.8"
        ts_x, ts_y = 10, 10
    elif "helmet" in style_lower:
        base_filters += ["vignette=PI/4"]
        noise_strength = 8
        ts_color = "white@0.9"
        ts_x, ts_y = 10, "h-30"
    elif "dashcam" in style_lower:
        base_filters += ["unsharp=5:5:0.5:5:5:0"]
        noise_strength = 6
        ts_color = "white@0.9"
        ts_x, ts_y = 10, 10
    elif "phone" in style_lower:
        noise_strength = 4
        ts_color = "white@0.0"  # no timestamp for phone
        ts_x, ts_y = 10, 10
    elif "bodycam" in style_lower:
        noise_strength = 10
        ts_color = "white@0.9"
        ts_x, ts_y = 10, "h-30"
    elif "baby monitor" in style_lower:
        base_filters += ["colorchannelmixer=0.9:0:0.1:0:0.1:0.8:0.1:0:0.1:0:0.9:0.1"]
        noise_strength = 25  # night-vision graininess
        ts_color = "green@0.9"
        ts_x, ts_y = 10, 10
    elif "ceiling" in style_lower:
        base_filters += ["vignette=PI/3"]
        noise_strength = 20
        ts_color = "white@0.8"
        ts_x, ts_y = 10, 10
    elif "bike" in style_lower:
        noise_strength = 6
        ts_color = "white@0.0"
        ts_x, ts_y = 10, 10
    else:
        noise_strength = 10
        ts_color = "white@0.8"
        ts_x, ts_y = 10, 10

    # Add noise (sensor grain / compression artifacts)
    base_filters.append(f"noise=alls={noise_strength}:allf=t+u")

    # Slight exposure fluctuation (simulate auto-exposure)
    exposure_shift = random.uniform(-0.05, 0.05)
    base_filters.append(f"eq=brightness={exposure_shift:.3f}:contrast=1.02")

    # Timestamp overlay (skip for phone/bike)
    if ts_color != "white@0.0":
        ts_filter = (
            f"drawtext=fontfile='{font_path}'"
            f":text='{ts_text}'"
            f":fontcolor={ts_color}"
            f":fontsize={ts_fontsize}"
            f":x={ts_x}:y={ts_y}"
            f":box=1:boxcolor=black@0.3:boxborderw=3"
        )
        base_filters.append(ts_filter)

    # TikTok captions
    if drawtext_captions and drawtext_captions != "null":
        base_filters.append(drawtext_captions)

    return ",".join(base_filters)


# ─────────────────────────────────────────────
# MAIN ASSEMBLER
# ─────────────────────────────────────────────

def assemble_video(
    raw_video_path: str,
    audio_path: str,
    script: Dict[str, Any],
    drawtext_captions: str,
    output_prefix: str,
    font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
) -> str:
    """
    Full assembly pipeline.

    Args:
        raw_video_path: Path to raw MP4 from Kaggle (no audio/captions)
        audio_path: Path to normalized narration WAV
        script: Full script dict (needs camera_style, duration, title)
        drawtext_captions: FFmpeg drawtext filter string from subtitle_generator
        output_prefix: File path prefix for output
        font_path: Path to bold font

    Returns:
        Path to final MP4
    """
    camera_style: str = script.get("camera_style", "CCTV fisheye")
    target_duration: float = float(script.get("duration", 40))

    # ── Step 1: Build video filter chain ───────────────────
    vf = _camera_style_to_vf(camera_style, drawtext_captions, font_path)

    # ── Step 2: Assemble with audio ─────────────────────────
    intermediate = os.path.join(TEMP_DIR, "assembled_intermediate.mp4")
    _run_ffmpeg([
        "-i", raw_video_path,
        "-i", audio_path,
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-t", str(target_duration),
        "-r", str(VIDEO_FPS),
        "-movflags", "+faststart",
        intermediate,
    ], desc="Assemble video+audio+filters")

    # ── Step 3: Final output ─────────────────────────────────
    final_path = f"{output_prefix}_final.mp4"
    _run_ffmpeg([
        "-i", intermediate,
        "-c:v", "copy",
        "-c:a", "copy",
        "-metadata", f"title={script.get('title', '')}",
        "-metadata", f"comment={script.get('hook', '')}",
        final_path,
    ], desc="Finalize metadata")

    # Cleanup intermediate
    try:
        os.remove(intermediate)
    except OSError:
        pass

    # Verify output
    if not os.path.exists(final_path) or os.path.getsize(final_path) < 10_000:
        raise RuntimeError(f"Final video is missing or too small: {final_path}")

    size_mb = os.path.getsize(final_path) / 1_048_576
    print(f"[Assembler] ✓ Final video: {final_path} ({size_mb:.1f} MB)")
    return final_path


def get_video_duration(mp4_path: str) -> float:
    """Use ffprobe to get video duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", mp4_path,
        ],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
