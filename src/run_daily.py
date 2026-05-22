"""
run_daily.py — orchestrate the full morning-brief pipeline.

1. Fetch sources (news, stocks, podcasts)
2. Generate the two-host script via GPT
3. Render audio via OpenAI TTS
4. Publish to GitHub Pages (mp3 + RSS feed)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetch_sources import fetch_all  # noqa: E402
from src.generate_script import generate_script  # noqa: E402
from src.generate_audio import build_episode  # noqa: E402
from src.publish import publish_episode  # noqa: E402

logger = logging.getLogger("morning-brief")

# Episode dates use the listener's local timezone so a 22:00 UTC cron run
# produces tomorrow's commute episode in GST — matches the day the user
# will actually listen on, not the UTC calendar day.
LOCAL_TZ = ZoneInfo("Asia/Dubai")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = json.loads((PROJECT_ROOT / "config" / "settings.json").read_text())

    # Idempotency: if today's episode already exists, exit before any API call.
    # This lets us safely schedule the workflow multiple times per night to
    # work around GitHub's unreliable cron — the first run that fires wins,
    # all later runs that day are zero-cost no-ops.
    today_str = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    target_mp3 = PROJECT_ROOT / "docs" / "episodes" / f"{today_str}.mp3"
    if target_mp3.exists():
        logger.info(
            "Episode for %s already exists — skipping (no API calls made).",
            today_str,
        )
        return 0

    logger.info("Generating episode for %s", today_str)

    # 1. Fetch sources
    logger.info("=== Step 1: fetching sources ===")
    brief = fetch_all(
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "state" / "last_episodes.json",
    )
    logger.info(
        "Brief: %d news items, %d stocks, %d new episodes",
        len(brief["news"]), len(brief["stocks"]), len(brief["new_episodes"]),
    )
    (PROJECT_ROOT / "state" / "last_brief.json").write_text(
        json.dumps(brief, indent=2, default=str)
    )

    # 2. Generate script
    logger.info("=== Step 2: writing script ===")
    segments = generate_script(brief, settings)
    word_count = sum(len(seg["text"].split()) for seg in segments)
    logger.info("Script: %d segments, ~%d words", len(segments), word_count)
    (PROJECT_ROOT / "state" / "last_script.json").write_text(
        json.dumps(segments, indent=2, ensure_ascii=False)
    )

    # 3. Generate audio
    logger.info("=== Step 3: rendering audio ===")
    with tempfile.TemporaryDirectory() as td:
        mp3_path = Path(td) / "episode.mp3"
        build_episode(segments, settings, mp3_path)

        # 4. Publish
        logger.info("=== Step 4: publishing ===")
        base_url = os.environ.get("PODCAST_BASE_URL")
        if not base_url:
            owner = os.environ.get("GITHUB_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "irmoiz"
            repo = os.environ.get("GITHUB_REPO") or (
                os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1] or "morning-brief"
            )
            base_url = f"https://{owner}.github.io/{repo}"
        logger.info("Publishing with base URL: %s", base_url)
        publish_episode(PROJECT_ROOT, mp3_path, settings, base_url, date_str=today_str)

    logger.info("=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
