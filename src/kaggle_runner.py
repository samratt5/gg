"""
Kaggle runner: pushes a config to Kaggle, triggers a GPU notebook,
polls for completion, and downloads the generated MP4.

Uses the official kaggle Python API package.
"""

import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional

import kaggle  # pip install kaggle
from kaggle.api.kaggle_api_extended import KaggleApiExtended

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    KAGGLE_USERNAME, KAGGLE_KEY, KAGGLE_KERNEL_SLUG,
    KAGGLE_POLL_INTERVAL, KAGGLE_TIMEOUT, TEMP_DIR,
    MAX_RETRIES, BACKOFF_BASE, BACKOFF_MAX,
)

os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# API CLIENT
# ─────────────────────────────────────────────

def _get_api() -> KaggleApiExtended:
    """Authenticate and return Kaggle API client."""
    os.environ["KAGGLE_USERNAME"] = KAGGLE_USERNAME
    os.environ["KAGGLE_KEY"] = KAGGLE_KEY
    api = KaggleApiExtended()
    api.authenticate()
    return api


# ─────────────────────────────────────────────
# NOTEBOOK CONFIG INJECTION
# ─────────────────────────────────────────────

def _inject_config_into_notebook(
    notebook_template_path: str,
    script_data: Dict[str, Any],
    output_path: str,
) -> str:
    """
    Read the template notebook, inject the video_config as a JSON variable
    in the first code cell, and write the result to output_path.
    Returns output_path.
    """
    with open(notebook_template_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    config_cell_source = [
        "# ── AUTO-INJECTED CONFIG ──────────────────────────────────────────\n",
        f"VIDEO_CONFIG = {json.dumps(script_data, indent=2)}\n",
        "# ──────────────────────────────────────────────────────────────────\n",
    ]

    # Prepend to first code cell
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["source"] = config_cell_source + cell["source"]
            break

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2)

    return output_path


# ─────────────────────────────────────────────
# KERNEL PUSH + RUN
# ─────────────────────────────────────────────

def _push_and_run_kernel(
    api: KaggleApiExtended,
    notebook_path: str,
    kernel_slug: str,
) -> str:
    """
    Push notebook source and trigger a run.
    Returns the full kernel ref string (username/slug).
    """
    kernel_meta = {
        "id": f"{KAGGLE_USERNAME}/{kernel_slug}",
        "title": kernel_slug,
        "code_file": os.path.basename(notebook_path),
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
    }

    meta_path = os.path.join(os.path.dirname(notebook_path), "kernel-metadata.json")
    with open(meta_path, "w") as f:
        json.dump(kernel_meta, f, indent=2)

    # Push kernel (this also triggers a run)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            api.kernels_push(os.path.dirname(notebook_path))
            print(f"[Kaggle] ✓ Kernel pushed: {KAGGLE_USERNAME}/{kernel_slug}")
            return f"{KAGGLE_USERNAME}/{kernel_slug}"
        except Exception as e:
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[Kaggle] Push attempt {attempt} failed: {e}. Retry in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Failed to push Kaggle kernel after {MAX_RETRIES} attempts.")


# ─────────────────────────────────────────────
# STATUS POLLING
# ─────────────────────────────────────────────

def _poll_until_done(api: KaggleApiExtended, kernel_ref: str) -> bool:
    """
    Poll kernel status until complete, failed, or timeout.
    Returns True on success.
    """
    username, slug = kernel_ref.split("/")
    deadline = time.time() + KAGGLE_TIMEOUT
    print(f"[Kaggle] Polling kernel {kernel_ref}…")

    while time.time() < deadline:
        time.sleep(KAGGLE_POLL_INTERVAL)
        try:
            status = api.kernel_status(username, slug)
            run_status = status.get("status", "unknown")
            print(f"[Kaggle] Status: {run_status} | "
                  f"Elapsed: {int(time.time() % 3600)}s | "
                  f"Remaining: {int(deadline - time.time())}s")

            if run_status == "complete":
                return True
            elif run_status in ("error", "cancel"):
                log = api.kernel_output(username, slug)
                raise RuntimeError(
                    f"Kaggle kernel {kernel_ref} ended with status '{run_status}'. "
                    f"Log:\n{log}"
                )
        except RuntimeError:
            raise
        except Exception as e:
            print(f"[Kaggle] Poll error (non-fatal): {e}")

    raise TimeoutError(f"Kaggle kernel {kernel_ref} did not complete within {KAGGLE_TIMEOUT}s.")


# ─────────────────────────────────────────────
# OUTPUT DOWNLOAD
# ─────────────────────────────────────────────

def _download_output(api: KaggleApiExtended, kernel_ref: str, dest_dir: str) -> str:
    """
    Download kernel output zip, extract MP4, return MP4 path.
    """
    username, slug = kernel_ref.split("/")
    os.makedirs(dest_dir, exist_ok=True)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            api.kernel_output(username, slug, path=dest_dir)
            break
        except Exception as e:
            wait = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            print(f"[Kaggle] Download attempt {attempt} failed: {e}. Retry in {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError("Failed to download Kaggle output after retries.")

    # Extract zip if needed
    zip_files = list(Path(dest_dir).glob("*.zip"))
    for zf in zip_files:
        with zipfile.ZipFile(zf, "r") as z:
            z.extractall(dest_dir)
        zf.unlink()

    # Find the MP4
    mp4_files = list(Path(dest_dir).glob("*.mp4"))
    if not mp4_files:
        raise FileNotFoundError(f"No MP4 found in Kaggle output at {dest_dir}")

    # Return the largest (most likely the final assembled video)
    mp4_files.sort(key=lambda p: p.stat().st_size, reverse=True)
    print(f"[Kaggle] ✓ Downloaded: {mp4_files[0]}")
    return str(mp4_files[0])


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_kaggle_video_generation(
    script_data: Dict[str, Any],
    notebook_template: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    Full Kaggle pipeline:
      1. Inject config into notebook
      2. Push and trigger
      3. Poll until done
      4. Download MP4
      5. Return MP4 path

    Args:
        script_data: full script dict from generate_script()
        notebook_template: path to template .ipynb (defaults to kaggle/wan21_video_generator.ipynb)
        output_dir: where to save the MP4

    Returns:
        Path to downloaded MP4
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if notebook_template is None:
        notebook_template = os.path.join(base_dir, "kaggle", "wan21_video_generator.ipynb")

    if output_dir is None:
        output_dir = os.path.join(TEMP_DIR, "kaggle_output")

    os.makedirs(output_dir, exist_ok=True)

    # 1. Inject config
    injected_nb = os.path.join(TEMP_DIR, "wan21_injected.ipynb")
    _inject_config_into_notebook(notebook_template, script_data, injected_nb)

    # Also write kernel-metadata.json sibling
    api = _get_api()

    # 2. Push
    kernel_ref = _push_and_run_kernel(api, injected_nb, KAGGLE_KERNEL_SLUG)

    # 3. Poll
    _poll_until_done(api, kernel_ref)

    # 4. Download
    mp4_path = _download_output(api, kernel_ref, output_dir)

    return mp4_path
