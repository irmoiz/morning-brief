"""
generate_audio.py — turn parsed script segments into a stitched mp3.

Uses OpenAI TTS with a different voice per host, glues the segments
together with short pauses for natural-sounding turn-taking.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydub import AudioSegment

logger = logging.getLogger(__name__)


# OpenAI's TTS endpoint accepts up to ~4096 characters per call.
MAX_CHARS_PER_CALL = 3500


def _chunk_text(text: str, limit: int = MAX_CHARS_PER_CALL) -> list[str]:
    """Break a long segment along sentence boundaries to stay under the API limit."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    # Naive sentence split that respects ".", "?", "!" followed by space.
    parts: list[str] = []
    buf = ""
    for char in text:
        buf += char
        if char in ".!?" and (not buf or buf[-2:][-1] != "."):
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())

    for p in parts:
        if len(current) + len(p) + 1 <= limit:
            current = (current + " " + p).strip()
        else:
            if current:
                chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    return chunks


def _synthesize(client: OpenAI, text: str, voice: str, model: str) -> AudioSegment:
    """Call the TTS API once and return the result as a pydub AudioSegment."""
    resp = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format="mp3",
    )
    return AudioSegment.from_file(io.BytesIO(resp.content), format="mp3")


def build_episode(
    segments: list[dict[str, str]],
    settings: dict[str, Any],
    output_path: Path,
) -> Path:
    """Render each segment, splice them together, write a single mp3."""
    client = OpenAI()

    s = settings["script"]
    a = settings["audio"]

    voice_for = {
        s["host_1_name"]: a["voice_host_1"],
        s["host_2_name"]: a["voice_host_2"],
    }

    final = AudioSegment.silent(duration=400)
    short_pause = AudioSegment.silent(duration=300)

    for i, seg in enumerate(segments, start=1):
        text = seg["text"].strip()
        if not text:
            continue
        voice = voice_for.get(seg["speaker"], a["voice_host_1"])

        for chunk in _chunk_text(text):
            logger.info(
                "TTS %d/%d  speaker=%s  voice=%s  chars=%d",
                i, len(segments), seg["speaker"], voice, len(chunk),
            )
            audio = _synthesize(client, chunk, voice, a["tts_model"])
            final += audio
        final += short_pause

    final += AudioSegment.silent(duration=500)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.export(str(output_path), format="mp3", bitrate="128k")
    logger.info("Wrote %s  (%.1fs, %.1f MB)",
                output_path,
                len(final) / 1000.0,
                output_path.stat().st_size / 1_000_000.0)
    return output_path


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    base = Path(__file__).resolve().parent.parent
    segments = json.loads(Path(sys.argv[1]).read_text())
    settings = json.loads((base / "config/settings.json").read_text())
    build_episode(segments, settings, base / "out" / "episode.mp3")
