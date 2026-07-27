from __future__ import annotations

import calendar
import difflib
import hashlib
import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import feedparser
import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "news-sources.json"
OUTPUT_PATH = ROOT / "data" / "news.json"
RSS_OUTPUT_PATH = ROOT / "news.xml"
MAX_STORIES = 10
MAX_STORY_AGE_DAYS = 10
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
EXCLUDED_TITLE_PATTERNS = (re.compile(r"\bpodcast\b", re.IGNORECASE),)
SITE_URL = "https://rohaanahmed.com"
ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"


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


def entry_date(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return None


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
        if any(pattern.search(title) for pattern in EXCLUDED_TITLE_PATTERNS):
            continue

        published = entry_date(entry)
        if published is None:
            continue
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


def parse_story_date(story: dict) -> datetime:
    return datetime.fromisoformat(story["publishedAt"].replace("Z", "+00:00"))


def select_stories(candidates: list[dict], generated_at: datetime) -> list[dict]:
    candidates.sort(key=parse_story_date, reverse=True)
    unique = []
    cutoff = generated_at - timedelta(days=MAX_STORY_AGE_DAYS)
    newest_allowed = generated_at + timedelta(days=1)

    for candidate in candidates:
        published = parse_story_date(candidate)
        if published < cutoff or published > newest_allowed:
            continue
        if not duplicate_story(candidate, unique):
            unique.append(candidate)

    active_sources = {story["source"] for story in unique}
    if not active_sources:
        return []

    source_cap = math.ceil(MAX_STORIES / len(active_sources))
    selected = []
    overflow = []
    source_counts = {source: 0 for source in active_sources}

    for story in unique:
        source = story["source"]
        if source_counts[source] < source_cap:
            selected.append(story)
            source_counts[source] += 1
        else:
            overflow.append(story)

    selected = sorted(selected, key=parse_story_date, reverse=True)[:MAX_STORIES]
    selected_urls = {
        (story["source"], canonical_url(story["url"])) for story in selected
    }
    if len(selected) < MAX_STORIES:
        for story in overflow:
            key = (story["source"], canonical_url(story["url"]))
            if key in selected_urls:
                continue
            selected.append(story)
            selected_urls.add(key)
            if len(selected) == MAX_STORIES:
                break

    return sorted(selected, key=parse_story_date, reverse=True)


def write_rss(output: dict, config: dict) -> None:
    ElementTree.register_namespace("atom", ATOM_NAMESPACE)
    rss = ElementTree.Element("rss", {"version": "2.0"})
    channel = ElementTree.SubElement(rss, "channel")
    ElementTree.SubElement(channel, "title").text = "Rohaan Ahmed - News"
    ElementTree.SubElement(channel, "link").text = f"{SITE_URL}/news.html"
    ElementTree.SubElement(channel, "description").text = (
        "An automatically curated list of news on topics of interest to me"
    )
    ElementTree.SubElement(channel, "language").text = "en-ca"
    generated_at = datetime.fromisoformat(
        output["generatedAt"].replace("Z", "+00:00")
    )
    ElementTree.SubElement(channel, "lastBuildDate").text = format_datetime(
        generated_at
    )
    ElementTree.SubElement(
        channel,
        f"{{{ATOM_NAMESPACE}}}link",
        {
            "href": f"{SITE_URL}/news.xml",
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    source_sites = {
        source["name"]: source["site"]
        for topic in config["topics"]
        for source in topic["sources"]
    }
    feed_stories = sorted(
        (
            (topic, story)
            for topic in output["topics"]
            for story in topic["stories"]
        ),
        key=lambda item: parse_story_date(item[1]),
        reverse=True,
    )

    for topic, story in feed_stories:
        item = ElementTree.SubElement(channel, "item")
        ElementTree.SubElement(item, "title").text = story["title"]
        ElementTree.SubElement(item, "link").text = story["url"]
        guid_value = hashlib.sha256(
            f"{topic['id']}:{canonical_url(story['url'])}".encode("utf-8")
        ).hexdigest()
        guid = ElementTree.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = guid_value
        ElementTree.SubElement(item, "pubDate").text = format_datetime(
            parse_story_date(story)
        )
        ElementTree.SubElement(item, "category").text = topic["name"]
        source = ElementTree.SubElement(
            item,
            "source",
            {"url": source_sites.get(story["source"], f"{SITE_URL}/news.html")},
        )
        source.text = story["source"]
        ElementTree.SubElement(item, "description").text = (
            f"{story['source']} | {topic['name']}"
        )

    tree = ElementTree.ElementTree(rss)
    ElementTree.indent(tree, space="  ")
    tree.write(RSS_OUTPUT_PATH, encoding="utf-8", xml_declaration=True)


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    previous = load_previous()
    previous_topics = {
        topic["id"]: topic for topic in previous.get("topics", []) if "id" in topic
    }
    generated_datetime = datetime.now(timezone.utc).replace(microsecond=0)
    generated_at = generated_datetime.isoformat()
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
        stories = select_stories(candidates, generated_datetime)

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
    write_rss(output, config)
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} and "
        f"{RSS_OUTPUT_PATH.relative_to(ROOT)} with "
        f"{feeds_succeeded} feeds available."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
