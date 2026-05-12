"""
fetch_sources.py — pulls every input the morning brief needs.

Sources:
  - Al Jazeera RSS for world news
  - Yahoo Finance per ticker for price moves, latest company news,
    and analyst consensus (rating + mean price target)
  - Podcast RSS for each show in podcasts.json, returning only
    episodes that are NEW since the last successful run
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests
import yfinance as yf

logger = logging.getLogger(__name__)


AL_JAZEERA_FEEDS = {
    "all": "https://www.aljazeera.com/xml/rss/all.xml",
}


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

def fetch_news(max_items: int = 12, hours_back: int = 24) -> list[dict[str, Any]]:
    """Return the freshest Al Jazeera headlines from the last `hours_back` hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    items: list[dict[str, Any]] = []

    for category, url in AL_JAZEERA_FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            continue

        for entry in feed.entries:
            pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if not pub_struct:
                continue
            published = datetime(*pub_struct[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue
            items.append({
                "category": category,
                "title": entry.title.strip(),
                "summary": (entry.get("summary") or "").strip()[:500],
                "published": published.isoformat(),
                "link": entry.link,
            })

    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:max_items]


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------

def fetch_stocks(tickers: list[str]) -> list[dict[str, Any]]:
    """For each ticker, pull last close, % change, latest news, and analyst data."""
    results: list[dict[str, Any]] = []

    for symbol in tickers:
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="5d", auto_adjust=False)

            if hist.empty or len(hist) < 2:
                logger.warning("No price history for %s", symbol)
                continue

            last_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            pct_change = ((last_close - prev_close) / prev_close) * 100.0

            # yfinance has shifted its `.news` shape over time. Handle both.
            raw_news: list[Any] = []
            try:
                raw_news = list(t.news or [])
            except Exception:
                pass

            news_items: list[dict[str, str]] = []
            for n in raw_news[:3]:
                if not isinstance(n, dict):
                    continue
                content = n.get("content")
                if isinstance(content, dict):
                    title = (content.get("title") or "").strip()
                    publisher = ((content.get("provider") or {}).get("displayName") or "").strip()
                else:
                    title = (n.get("title") or "").strip()
                    publisher = (n.get("publisher") or "").strip()
                if title:
                    news_items.append({"title": title, "publisher": publisher})

            results.append({
                "symbol": symbol,
                "name": info.get("shortName") or info.get("longName") or symbol,
                "currency": info.get("currency", "USD"),
                "last_close": round(last_close, 2),
                "pct_change": round(pct_change, 2),
                "recommendation": info.get("recommendationKey") or "n/a",
                "target_mean": info.get("targetMeanPrice"),
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
                "news": news_items,
            })
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", symbol, exc)

    return results


# ---------------------------------------------------------------------------
# Podcasts
# ---------------------------------------------------------------------------

def discover_rss(show_name: str) -> str | None:
    """Resolve a podcast's RSS feed URL by searching the iTunes Search API."""
    try:
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": show_name, "entity": "podcast", "limit": 5},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("iTunes lookup failed for %s: %s", show_name, exc)
        return None

    results = data.get("results", [])
    # Exact name match first.
    for result in results:
        if result.get("collectionName", "").strip().lower() == show_name.strip().lower():
            return result.get("feedUrl")
    # Otherwise the top hit.
    return results[0].get("feedUrl") if results else None


def fetch_podcast_episodes(
    podcasts: list[dict[str, Any]],
    state: dict[str, list[str]],
    days_back: int = 7,
    per_show_limit: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """
    Return episodes published within the last `days_back` days that haven't been seen.

    State is per-show: a list of GUIDs already reported (capped at 50 each). This makes
    us robust to feeds that don't list newest-first and to feeds that occasionally reorder.
    """
    new_episodes: list[dict[str, Any]] = []
    new_state: dict[str, list[str]] = {k: list(v) for k, v in state.items()}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    for show in podcasts:
        name = show["name"]
        rss = show.get("rss") or discover_rss(name)
        if not rss:
            logger.warning("No RSS feed found for %s", name)
            continue

        feed = feedparser.parse(rss)
        if not feed.entries:
            continue

        seen = set(new_state.get(name, []))
        candidates: list[dict[str, Any]] = []

        for entry in feed.entries:
            pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if not pub_struct:
                continue
            published = datetime(*pub_struct[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue

            guid = entry.get("id") or entry.get("guid") or entry.link
            if guid in seen:
                continue

            candidates.append({
                "show": name,
                "title": entry.title.strip(),
                "summary": (entry.get("summary") or entry.get("description") or "").strip()[:1200],
                "published": published.isoformat(),
                "_published_dt": published,
                "guid": guid,
            })

        # Newest first, cap per show.
        candidates.sort(key=lambda x: x["_published_dt"], reverse=True)
        kept = candidates[:per_show_limit]
        for c in kept:
            c.pop("_published_dt", None)
            seen.add(c["guid"])

        # Bound state size per show.
        new_state[name] = list(seen)[-50:]
        new_episodes.extend(kept)

    return new_episodes, new_state


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def fetch_all(config_dir: Path, state_path: Path) -> dict[str, Any]:
    """Top-level: load config, run every fetcher, persist new state, return brief."""
    tickers = json.loads((config_dir / "tickers.json").read_text())["tickers"]
    podcasts = json.loads((config_dir / "podcasts.json").read_text())["podcasts"]

    state: dict[str, str] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text())

    news = fetch_news()
    stocks = fetch_stocks(tickers)
    episodes, new_state = fetch_podcast_episodes(podcasts, state)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, indent=2))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "news": news,
        "stocks": stocks,
        "new_episodes": episodes,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    base = Path(__file__).resolve().parent.parent
    brief = fetch_all(base / "config", base / "state" / "last_episodes.json")
    print(json.dumps(brief, indent=2, default=str))
