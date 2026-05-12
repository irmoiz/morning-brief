"""
generate_script.py — turn the brief into a tagged two-host podcast script.

Output is a list of segments, each a dict with "speaker" + "text", ready
for the TTS step to render each segment with the right voice.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are writing a daily ~10-minute morning news podcast for one specific listener (Moiz) on his drive to work.

TWO HOSTS:
  - {host_1_name} ({voice_1_desc})
  - {host_2_name} ({voice_2_desc})

CRITICAL FORMAT RULES:
1. Output ONLY dialog lines, no stage directions, music cues, or scene descriptions.
2. Every line MUST start with [{host_1_name}] or [{host_2_name}] — exactly that, no variations.
3. Total target: ~{target_words} words (≈{target_minutes} minutes at normal pace).
4. Hosts alternate naturally — don't let one host monologue for more than ~120 words at a stretch.

VOICE:
- Two smart friends chatting over coffee, not stiff radio anchors.
- Specific reactions are good ("oh that's wild", "huh, didn't expect that").
- Don't invent facts. If a number or detail isn't in the brief, don't say it.
- Don't promise "we'll be back tomorrow" or shill anything. This is for an audience of one.

STRUCTURE (loose, don't announce the sections):
- (≈15s) Cold open — one host reacts to the most interesting thing in the brief, the other picks it up.
- (3–4 min) WORLD NEWS — Al Jazeera headlines. Group related stories, add context, don't just read titles.
- (3–4 min) MARKETS — for each ticker in the brief: how it moved (% + direction), why if there's news, analyst rating + mean price target ONLY if interesting or significantly out of line with current price. Don't recite every number — it's a podcast, not a Bloomberg terminal.
- (2–3 min) NEW IN YOUR PODCASTS — for each new episode in the brief, the 2-sentence "this is what it's about, here's whether it's worth your time" pitch. SKIP THIS SECTION ENTIRELY if the brief has no new_episodes.
- (≈10s) Outro — quick, dry sign-off."""


USER_PROMPT_TEMPLATE = """Today's brief (raw data):

```json
{brief_json}
```

Write the full podcast script following the rules above. Output ONLY the tagged dialog lines."""


def generate_script(brief: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, str]]:
    """Call the LLM and parse the response into ordered speaker segments."""
    client = OpenAI()

    s = settings["script"]
    a = settings["audio"]

    voice_descriptions = {
        "onyx": "deeper male voice, anchor-like",
        "nova": "warm female voice",
        "alloy": "neutral voice",
        "echo": "smooth male voice",
        "fable": "British male voice",
        "shimmer": "bright female voice",
    }

    system_prompt = SYSTEM_PROMPT.format(
        host_1_name=s["host_1_name"],
        host_2_name=s["host_2_name"],
        voice_1_desc=voice_descriptions.get(a["voice_host_1"], "host voice"),
        voice_2_desc=voice_descriptions.get(a["voice_host_2"], "host voice"),
        target_words=s["target_words"],
        target_minutes=s["target_minutes"],
    )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        brief_json=json.dumps(brief, indent=2, default=str),
    )

    response = client.chat.completions.create(
        model=s["llm_model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.75,
    )

    raw_script = response.choices[0].message.content or ""
    return parse_script(raw_script, s["host_1_name"], s["host_2_name"])


def parse_script(raw: str, host_1: str, host_2: str) -> list[dict[str, str]]:
    """Split a [Speaker]-tagged script into a list of segments."""
    line_re = re.compile(
        rf"^\s*\[(?P<who>{re.escape(host_1)}|{re.escape(host_2)})\]\s*(?P<text>.*)$",
        re.IGNORECASE,
    )

    segments: list[dict[str, str]] = []
    current_speaker: str | None = None
    current_text: list[str] = []

    def flush() -> None:
        if current_speaker and current_text:
            text = " ".join(current_text).strip()
            if text:
                segments.append({"speaker": current_speaker, "text": text})

    for line in raw.splitlines():
        m = line_re.match(line)
        if m:
            flush()
            # Normalize speaker capitalization to canonical config name.
            who = m.group("who")
            current_speaker = host_1 if who.lower() == host_1.lower() else host_2
            current_text = []
            first = m.group("text").strip()
            if first:
                current_text.append(first)
        elif current_speaker and line.strip():
            current_text.append(line.strip())

    flush()
    return segments


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    base = Path(__file__).resolve().parent.parent
    brief = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else {}
    settings = json.loads((base / "config/settings.json").read_text())
    segments = generate_script(brief, settings)
    print(json.dumps(segments, indent=2, ensure_ascii=False))
