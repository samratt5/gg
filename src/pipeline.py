"""
Main pipeline orchestrator.

Runs the full end-to-end pipeline:
  1. Generate script (Mistral)
  2. Generate TTS audio (Wavel.ai)
  3. Trigger Kaggle video generation (Wan2.1)
  4. Generate subtitles (WhisperX)
  5. Assemble final video (FFmpeg)
  6. Store memory record
  7. Export artifact

Designed to be called from GitHub Actions or CLI.
"""

import json
import os
import sys
import time
import argparse
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import OUTPUT_DIR, TEMP_DIR
from src.script_generator import generate_script, finalize_and_store
from src.tts_generator import generate_tts_audio
from src.kaggle_runner import run_kaggle_video_generation
from src.subtitle_generator import generate_subtitles
from src.video_assembler import assemble_video

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# PIPELINE RESULT
# ─────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.success: bool = False
        self.video_path: str = ""
        self.script: dict = {}
        self.duration_seconds: float = 0.0
        self.error: str = ""
        self.started_at: str = ""
        self.finished_at: str = ""
        self.stage_times: dict = {}

    def to_dict(self) -> dict:
        return self.__dict__

    def save_manifest(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def run_pipeline(dry_run: bool = False) -> PipelineResult:
    """
    Execute the full video generation pipeline.

    Args:
        dry_run: If True, skip Kaggle and TTS calls; use placeholder paths.

    Returns:
        PipelineResult with success status and output paths.
    """
    result = PipelineResult()
    result.started_at = datetime.utcnow().isoformat()

    # Build a unique run ID
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(TEMP_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    prefix = os.path.join(run_dir, run_id)

    print(f"\n{'='*60}")
    print(f"  VIRAL ANIMAL VIDEO PIPELINE  |  Run: {run_id}")
    print(f"{'='*60}\n")

    try:
        # ─────────────────────────────────────────
        # STAGE 1: Script Generation
        # ─────────────────────────────────────────
        t0 = time.time()
        print("▶ STAGE 1: Generating script…")
        script = generate_script()
        result.script = script
        result.stage_times["script_gen"] = round(time.time() - t0, 2)
        print(f"  Title: {script['title']}")
        print(f"  Animal: {script.get('animal_type')} | "
              f"Camera: {script['camera_style']} | "
              f"Duration: {script['duration']}s\n")

        # Save script JSON
        script_path = f"{prefix}_script.json"
        with open(script_path, "w") as f:
            json.dump(script, f, indent=2)

        if dry_run:
            print("  [DRY RUN] Skipping TTS, Kaggle, and assembly.\n")
            result.success = True
            result.finished_at = datetime.utcnow().isoformat()
            return result

        # ─────────────────────────────────────────
        # STAGE 2: TTS Audio
        # ─────────────────────────────────────────
        t0 = time.time()
        print("▶ STAGE 2: Generating TTS audio…")
        audio_path = generate_tts_audio(script, prefix)
        result.stage_times["tts"] = round(time.time() - t0, 2)
        print(f"  Audio: {audio_path}\n")

        # ─────────────────────────────────────────
        # STAGE 3: Kaggle Video Generation
        # ─────────────────────────────────────────
        t0 = time.time()
        print("▶ STAGE 3: Triggering Kaggle GPU notebook…")
        raw_video_path = run_kaggle_video_generation(
            script_data=script,
            output_dir=os.path.join(run_dir, "kaggle_out"),
        )
        result.stage_times["kaggle_gpu"] = round(time.time() - t0, 2)
        print(f"  Raw video: {raw_video_path}\n")

        # ─────────────────────────────────────────
        # STAGE 4: Subtitle Generation
        # ─────────────────────────────────────────
        t0 = time.time()
        print("▶ STAGE 4: Generating subtitles…")
        srt_path, drawtext_filter, captions = generate_subtitles(
            wav_path=audio_path,
            output_prefix=prefix,
        )
        result.stage_times["subtitles"] = round(time.time() - t0, 2)
        print(f"  SRT: {srt_path} | {len(captions)} caption events\n")

        # ─────────────────────────────────────────
        # STAGE 5: Video Assembly
        # ─────────────────────────────────────────
        t0 = time.time()
        print("▶ STAGE 5: Assembling final video…")

        # Output to OUTPUT_DIR with clean filename
        safe_title = "".join(
            c if c.isalnum() or c in " _-" else "_"
            for c in script["title"]
        )[:50].strip()
        final_prefix = os.path.join(OUTPUT_DIR, f"{run_id}_{safe_title}")

        final_video = assemble_video(
            raw_video_path=raw_video_path,
            audio_path=audio_path,
            script=script,
            drawtext_captions=drawtext_filter,
            output_prefix=final_prefix,
        )
        result.stage_times["assembly"] = round(time.time() - t0, 2)
        result.video_path = final_video

        # ─────────────────────────────────────────
        # STAGE 6: Store Memory Record
        # ─────────────────────────────────────────
        print("▶ STAGE 6: Storing memory record…")
        record_hash = finalize_and_store(script)
        print(f"  Stored hash: {record_hash[:12]}…\n")

        # ─────────────────────────────────────────
        # COMPLETE
        # ─────────────────────────────────────────
        result.success = True
        result.finished_at = datetime.utcnow().isoformat()
        total = sum(result.stage_times.values())

        print(f"\n{'='*60}")
        print(f"  ✅ PIPELINE COMPLETE")
        print(f"  Video: {final_video}")
        print(f"  Total time: {total:.0f}s")
        print(f"  Stage breakdown: {result.stage_times}")
        print(f"{'='*60}\n")

        # Save manifest
        manifest_path = f"{final_prefix}_manifest.json"
        result.save_manifest(manifest_path)

    except Exception as e:
        result.success = False
        result.error = str(e)
        result.finished_at = datetime.utcnow().isoformat()
        print(f"\n❌ PIPELINE FAILED at stage: {e}")
        traceback.print_exc()

    return result


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Viral Animal Video Pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run script generation only (no API calls)")
    parser.add_argument("--count", type=int, default=1,
                        help="Number of videos to generate sequentially")
    args = parser.parse_args()

    for i in range(args.count):
        if args.count > 1:
            print(f"\n{'#'*60}")
            print(f"  VIDEO {i+1} of {args.count}")
            print(f"{'#'*60}")

        r = run_pipeline(dry_run=args.dry_run)

        if not r.success:
            print(f"[Pipeline] Failed: {r.error}")
            sys.exit(1)

    sys.exit(0)
