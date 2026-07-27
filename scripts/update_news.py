from __future__ import annotations

import calendar
import difflib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "news-sources.json"
OUTPUT_PATH = ROOT / "data" / "news.json"
MAX_STORIES = 10
TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}
STOP_WORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "is", "of",
    "on", "the", "to", "with",
}
REQUEST_HEADERS = {
    "User-Agent": (
        "RohaanAhmedNewsReader/1.0 "
        "(https://github.com/rohaan-ahmed/rohaanahmed_website)"
    )
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMETERS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def normalized_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", title.casefold()))


def title_tokens(title: str) -> set[str]:
    return {
        token
        for token in normalized_title(title).split()
        if token not in STOP_WORDS and len(token) > 2
    }


def duplicate_story(candidate: dict, accepted: list[dict]) -> bool:
    candidate_url = canonical_url(candidate["url"])
    candidate_title = normalized_title(candidate["title"])
    candidate_tokens = title_tokens(candidate["title"])

    for story in accepted:
        if candidate_url == canonical_url(story["url"]):
            return True

        existing_title = normalized_title(story["title"])
        if candidate_title == existing_title:
            return True

        if difflib.SequenceMatcher(None, candidate_title, existing_title).ratio() >= 0.9:
            return True

        existing_tokens = title_tokens(story["title"])
        union = candidate_tokens | existing_tokens
        if len(candidate_tokens) >= 5 and len(existing_tokens) >= 5 and union:
            if len(candidate_tokens & existing_tokens) / len(union) >= 0.8:
                return True

    return False


def entry_date(entry: dict) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_source(source: dict) -> list[dict]:
    response = requests.get(source["feed"], headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)

    if parsed.bozo and not parsed.entries:
        raise ValueError(str(parsed.bozo_exception))

    stories = []
    for entry in parsed.entries:
        title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue

        published = entry_date(entry)
        stories.append(
            {
                "title": title,
                "url": canonical_url(url),
                "publishedAt": published.replace(microsecond=0).isoformat(),
                "source": source["name"],
            }
        )

    return stories


def load_previous() -> dict:
    if not OUTPUT_PATH.exists():
        return {}
    try:
        return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    previous = load_previous()
    previous_topics = {
        topic["id"]: topic for topic in previous.get("topics", []) if "id" in topic
    }
    generated_at = iso_now()
    output_topics = []
    failures = []
    feeds_succeeded = 0

    topic_results = {
        topic["id"]: {"candidates": [], "successes": 0}
        for topic in config["topics"]
    }

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_source, source): (topic["id"], source)
            for topic in config["topics"]
            for source in topic["sources"]
        }
        for future in as_completed(futures):
            topic_id, source = futures[future]
            try:
                source_stories = future.result()
                topic_results[topic_id]["candidates"].extend(source_stories)
                topic_results[topic_id]["successes"] += 1
                feeds_succeeded += 1
                print(f"Fetched {len(source_stories):>3} stories from {source['name']}")
            except Exception as error:
                failures.append(f"{source['name']}: {error}")
                print(
                    f"Warning: could not read {source['name']}: {error}",
                    file=sys.stderr,
                )

    for topic in config["topics"]:
        candidates = topic_results[topic["id"]]["candidates"]
        topic_successes = topic_results[topic["id"]]["successes"]
        candidates.sort(key=lambda story: story["publishedAt"], reverse=True)
        stories = []
        for candidate in candidates:
            if not duplicate_story(candidate, stories):
                stories.append(candidate)
            if len(stories) == MAX_STORIES:
                break

        if topic_successes == 0 and topic["id"] in previous_topics:
            old_topic = previous_topics[topic["id"]]
            stories = old_topic.get("stories", [])
            updated_at = old_topic.get(
                "updatedAt", previous.get("generatedAt", generated_at)
            )
            print(f"Keeping previous stories for {topic['name']}", file=sys.stderr)
        else:
            updated_at = generated_at

        output_topics.append(
            {
                "id": topic["id"],
                "name": topic["name"],
                "updatedAt": updated_at,
                "stories": stories,
            }
        )

    if feeds_succeeded == 0 and not previous_topics:
        print(
            "Error: no feeds could be read and no previous news data exists.",
            file=sys.stderr,
        )
        return 1

    output = {
        "generatedAt": generated_at,
        "topics": output_topics,
        "sources": [
            {
                "topic": topic["name"],
                "name": source["name"],
                "url": source["site"],
                "feed": source["feed"],
            }
            for topic in config["topics"]
            for source in topic["sources"]
        ],
        "warnings": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with "
        f"{feeds_succeeded} feeds available."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
