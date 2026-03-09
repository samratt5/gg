"""
Subtitle generation pipeline:
  1. Run WhisperX on the narration WAV to get word-level timestamps
  2. Convert to SRT format
  3. Reformat into TikTok-style (≤3 words/line, emphasis on emotional words)
  4. Generate FFmpeg drawtext filter string for burning captions
  5. Return both SRT path and FFmpeg filter_complex string
"""

import os
import re
import sys
from typing import List, Dict, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import TEMP_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

os.makedirs(TEMP_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# EMOTIONAL EMPHASIS WORDS
# These trigger uppercase + larger font in captions
# ─────────────────────────────────────────────
EMPHASIS_WORDS = {
    "never", "forever", "left", "alone", "goodbye", "died", "dead",
    "lost", "found", "saved", "cried", "loved", "betrayed", "waited",
    "years", "last", "final", "gone", "home", "back", "stayed", "cried",
    "heart", "broke", "screamed", "silent", "begged", "refused", "knew",
    "looked", "still", "only", "always", "every", "real", "true",
    "pain", "hope", "love", "fear", "held", "left", "saw", "feel",
}


# ─────────────────────────────────────────────
# WHISPERX TRANSCRIPTION
# ─────────────────────────────────────────────

def transcribe_audio(wav_path: str) -> List[Dict[str, Any]]:
    """
    Run WhisperX on the WAV file.
    Returns list of word-level dicts: {word, start, end}
    """
    try:
        import whisperx
        import torch
    except ImportError:
        raise ImportError(
            "whisperx not installed. Run: pip install whisperx"
        )

    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    print(f"[Whisper] Loading model on {device}…")
    model = whisperx.load_model("base", device, compute_type=compute_type)

    audio = whisperx.load_audio(wav_path)
    result = model.transcribe(audio, batch_size=16)

    # Align for word-level timestamps
    model_a, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    result = whisperx.align(
        result["segments"], model_a, metadata, audio, device,
        return_char_alignments=False
    )

    # Flatten to word list
    words = []
    for seg in result.get("word_segments", []):
        words.append({
            "word": seg.get("word", "").strip(),
            "start": seg.get("start", 0.0),
            "end": seg.get("end", 0.0),
        })

    return words


# ─────────────────────────────────────────────
# SRT GENERATION
# ─────────────────────────────────────────────

def _ts(seconds: float) -> str:
    """Convert float seconds to SRT timestamp HH:MM:SS,mmm"""
    ms = int((seconds % 1) * 1000)
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def words_to_srt(words: List[Dict], max_words_per_line: int = 3) -> str:
    """
    Group words into subtitle lines of ≤ max_words_per_line.
    Returns SRT string.
    """
    if not words:
        return ""

    lines = []
    i = 0
    idx = 1
    while i < len(words):
        chunk = words[i: i + max_words_per_line]
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["word"] for w in chunk).upper()
        lines.append(f"{idx}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
        idx += 1
        i += max_words_per_line

    return "\n".join(lines)


def save_srt(srt_content: str, output_path: str) -> str:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return output_path


# ─────────────────────────────────────────────
# TIKTOK CAPTION FORMATTER
# ─────────────────────────────────────────────

def _is_emphasis(word: str) -> bool:
    return word.lower().strip(".,!?'\"") in EMPHASIS_WORDS


def format_tiktok_captions(words: List[Dict]) -> List[Dict]:
    """
    Convert word-level data to TikTok-style caption events.
    Each event: {start, end, text, is_emphasis}
    Groups: ≤3 words, emphasis words get their own line.
    """
    captions = []
    i = 0

    while i < len(words):
        # Check if this word should stand alone for emphasis
        w = words[i]
        if _is_emphasis(w["word"]):
            captions.append({
                "start": w["start"],
                "end": w["end"] + 0.05,
                "text": w["word"].upper(),
                "is_emphasis": True,
            })
            i += 1
            continue

        # Group up to 3 non-emphasis words
        chunk = []
        while i < len(words) and len(chunk) < 3:
            cw = words[i]
            if _is_emphasis(cw["word"]) and chunk:
                break
            chunk.append(cw)
            i += 1

        if chunk:
            captions.append({
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"] + 0.05,
                "text": " ".join(c["word"].upper() for c in chunk),
                "is_emphasis": False,
            })

    return captions


# ─────────────────────────────────────────────
# FFMPEG DRAWTEXT FILTER BUILDER
# ─────────────────────────────────────────────

def build_ffmpeg_drawtext_filters(
    captions: List[Dict],
    font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
) -> str:
    """
    Build FFmpeg filter_complex drawtext chain from caption events.
    Returns a string to be inserted into -vf / filter_complex.
    """
    filters = []
    y_center = int(VIDEO_HEIGHT * 0.72)  # 72% down the frame

    for cap in captions:
        text = cap["text"].replace("'", "\\'").replace(":", "\\:")
        start = cap["start"]
        end = cap["end"]

        # Emphasis words: bigger, white with black outline, slight scale
        if cap["is_emphasis"]:
            fontsize = 80
            fontcolor = "white"
            box = 1
            boxcolor = "black@0.5"
            borderw = 4
        else:
            fontsize = 60
            fontcolor = "white"
            box = 1
            boxcolor = "black@0.4"
            borderw = 3

        enable_expr = f"between(t,{start:.3f},{end:.3f})"
        filter_str = (
            f"drawtext=fontfile='{font_path}'"
            f":text='{text}'"
            f":fontcolor={fontcolor}"
            f":fontsize={fontsize}"
            f":x=(w-text_w)/2"
            f":y={y_center}"
            f":box={box}"
            f":boxcolor={boxcolor}"
            f":boxborderw=8"
            f":borderw={borderw}"
            f":bordercolor=black"
            f":enable='{enable_expr}'"
        )
        filters.append(filter_str)

    return ",".join(filters) if filters else "null"


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def generate_subtitles(
    wav_path: str,
    output_prefix: str,
    font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
) -> Tuple[str, str, List[Dict]]:
    """
    Full subtitle pipeline.

    Args:
        wav_path: path to narration WAV
        output_prefix: output file prefix (no extension)
        font_path: path to bold font for drawtext

    Returns:
        (srt_path, ffmpeg_drawtext_filter_string, captions_list)
    """
    print("[Subtitles] Transcribing with WhisperX…")
    words = transcribe_audio(wav_path)

    print(f"[Subtitles] Got {len(words)} words. Building SRT…")
    srt_content = words_to_srt(words, max_words_per_line=3)
    srt_path = save_srt(srt_content, f"{output_prefix}.srt")
    print(f"[Subtitles] ✓ SRT saved: {srt_path}")

    print("[Subtitles] Formatting TikTok-style captions…")
    captions = format_tiktok_captions(words)

    print("[Subtitles] Building FFmpeg drawtext filter…")
    drawtext_filter = build_ffmpeg_drawtext_filters(captions, font_path)

    return srt_path, drawtext_filter, captions
