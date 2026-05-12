"""
publish.py — copy today's mp3 into the repo's GitHub Pages dir,
rebuild the podcast RSS feed from the current episode list, and
commit + push back to the repo.

Assumes the working directory is a git checkout with credentials
already configured (in GitHub Actions, this is automatic).
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)


def _git(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *cmd], cwd=cwd, check=True, text=True, capture_output=True,
    )


def commit_and_push(repo_dir: Path, message: str) -> bool:
    """Stage everything, commit if there are changes, push. Returns True if pushed."""
    _git(["add", "-A"], repo_dir)
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repo_dir,
    )
    if status.returncode == 0:
        logger.info("No changes to commit")
        return False
    _git(["commit", "-m", message], repo_dir)
    _git(["push"], repo_dir)
    return True


def build_rss(
    settings: dict[str, Any],
    episode_files: list[Path],
    base_url: str,
) -> str:
    """Render the iTunes-compatible podcast feed XML from disk."""
    p = settings["podcast"]
    items_xml: list[str] = []

    for ep in sorted(episode_files, reverse=True):
        date_str = ep.stem  # filename: YYYY-MM-DD.mp3
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning("Skipping non-date episode file: %s", ep.name)
            continue
        size = ep.stat().st_size
        url = f"{base_url}/episodes/{ep.name}"
        pub_date = format_datetime(dt)
        title = f"Morning Brief — {date_str}"

        items_xml.append(f"""
    <item>
      <title>{escape(title)}</title>
      <description>{escape(p['description'])}</description>
      <pubDate>{pub_date}</pubDate>
      <enclosure url="{escape(url)}" length="{size}" type="audio/mpeg" />
      <guid isPermaLink="false">morning-brief-{escape(date_str)}</guid>
      <itunes:author>{escape(p['author'])}</itunes:author>
      <itunes:duration>10:00</itunes:duration>
      <itunes:explicit>{'true' if p.get('explicit') else 'false'}</itunes:explicit>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{escape(p['title'])}</title>
    <link>{escape(base_url)}</link>
    <language>{escape(p['language'])}</language>
    <description>{escape(p['description'])}</description>
    <itunes:author>{escape(p['author'])}</itunes:author>
    <itunes:summary>{escape(p['subtitle'])}</itunes:summary>
    <itunes:owner>
      <itunes:name>{escape(p['author'])}</itunes:name>
      <itunes:email>{escape(p['email'])}</itunes:email>
    </itunes:owner>
    <itunes:image href="{escape(base_url)}/{escape(p['cover_image'])}" />
    <itunes:category text="{escape(p['category'])}" />
    <itunes:explicit>{'true' if p.get('explicit') else 'false'}</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{''.join(items_xml)}
  </channel>
</rss>
"""


def publish_episode(
    repo_dir: Path,
    mp3_source: Path,
    settings: dict[str, Any],
    base_url: str,
) -> None:
    """Place the new mp3, rebuild the feed, commit + push."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    docs_dir = repo_dir / "docs"
    episodes_dir = docs_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    target = episodes_dir / f"{date_str}.mp3"
    target.write_bytes(mp3_source.read_bytes())
    logger.info("Copied today's episode to %s", target)

    episode_files = sorted(episodes_dir.glob("*.mp3"))
    rss_xml = build_rss(settings, episode_files, base_url)
    feed_path = docs_dir / "feed.xml"
    feed_path.write_text(rss_xml)
    logger.info("Rebuilt feed with %d episode(s) at %s", len(episode_files), feed_path)

    commit_and_push(repo_dir, f"Add episode {date_str}")
