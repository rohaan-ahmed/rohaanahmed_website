from __future__ import annotations

import calendar
import difflib
import hashlib
import html
import json
import re
import sys
from collections import defaultdict
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
MAX_STORIES = 15
BULLETIN_STORIES = 10
AI_BULLETIN_STORIES = 2
MAX_STORY_AGE_DAYS = 10
SOURCE_PRIORITY_BONUS_HOURS = 18
DISPLAY_TOPIC_ORDER = [
    "artificial-intelligence",
    "canadian-space",
    "international-space",
    "canadian-defence",
    "international-defence-technology",
    "robotics",
]
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
TOPIC_NAMESPACE = "https://rohaanahmed.com/ns/news/1.0"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_url(url: str) -> str:
    parts = urlsplit(html.unescape(url.strip()))
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


TLDR_SECTION_PATTERN = re.compile(r"<section>(.*?)</section>", re.DOTALL)
TLDR_HEADER_PATTERN = re.compile(
    r"<header>.*?<h3[^>]*>(.*?)</h3>.*?</header>", re.DOTALL
)
TLDR_ARTICLE_PATTERN = re.compile(
    r"<article[^>]*>.*?<a[^>]*href=\"([^\"]+)\"[^>]*>.*?<h3>(.*?)</h3>.*?</a>.*?</article>",
    re.DOTALL,
)
TLDR_ALLOWED_SECTIONS = {
    "Headlines & Launches",
    "Deep Dives & Analysis",
    "Engineering & Research",
}
RUNDOWN_SECTION_PATTERN = re.compile(
    r"<div class=\"section\"[^>]*>(.*?)</div>", re.DOTALL
)
RUNDOWN_H6_PATTERN = re.compile(r"<h6[^>]*>(.*?)</h6>", re.DOTALL)
RUNDOWN_H4_LINK_PATTERN = re.compile(
    r"<h4[^>]*>.*?<a[^>]*href=\"([^\"]+)\"[^>]*>.*?<span[^>]*>?(.*?)</span>.*?</a>.*?</h4>",
    re.DOTALL,
)
RUNDOWN_H4_LINK_FALLBACK_PATTERN = re.compile(
    r"<h4[^>]*>.*?<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>.*?</h4>",
    re.DOTALL,
)
RUNDOWN_SKIPPED_SECTION_LABELS = {
    "AI TRAINING",
    "COMMUNITY",
}
RUNDOWN_SKIPPED_SECTION_PREFIXES = (
    "PRESENTED BY ",
    "TOGETHER WITH ",
)


def clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def fetch_tldr_ai_stories(source: dict, entry: dict, published: datetime) -> list[dict]:
    response = requests.get(entry["link"], headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    page = response.text
    stories = []

    for section_html in TLDR_SECTION_PATTERN.findall(page):
        header_match = TLDR_HEADER_PATTERN.search(section_html)
        if not header_match:
            continue
        section_name = clean_html_text(header_match.group(1))
        if section_name not in TLDR_ALLOWED_SECTIONS:
            continue

        for url, raw_title in TLDR_ARTICLE_PATTERN.findall(section_html):
            title = clean_html_text(raw_title)
            if not title or title == ")" or "(Sponsor)" in title:
                continue
            if url.startswith("mailto:"):
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


def is_external_news_url(url: str) -> bool:
    normalized = canonical_url(url)
    host = urlsplit(normalized).netloc
    return (
        host != ""
        and "therundown.ai" not in host
        and "rundown.ai" not in host
        and host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
        and not normalized.startswith("mailto:")
    )


def fetch_rundown_ai_stories(source: dict, entry: dict, published: datetime) -> list[dict]:
    content_blocks = entry.get("content", [])
    if not content_blocks:
        return []

    page = "\n".join(block.get("value", "") for block in content_blocks if block.get("value"))
    stories = []

    for section_html in RUNDOWN_SECTION_PATTERN.findall(page):
        header_match = RUNDOWN_H6_PATTERN.search(section_html)
        section_label = clean_html_text(header_match.group(1)) if header_match else ""
        if (
            section_label in RUNDOWN_SKIPPED_SECTION_LABELS
            or section_label.startswith(RUNDOWN_SKIPPED_SECTION_PREFIXES)
        ):
            continue

        article_match = (
            RUNDOWN_H4_LINK_PATTERN.search(section_html)
            or RUNDOWN_H4_LINK_FALLBACK_PATTERN.search(section_html)
        )
        if article_match:
            url = article_match.group(1)
            title = clean_html_text(article_match.group(2))
            if (
                title
                and len(title_tokens(title)) >= 3
                and is_external_news_url(url)
            ):
                stories.append(
                    {
                        "title": title,
                        "url": canonical_url(url),
                        "publishedAt": published.replace(microsecond=0).isoformat(),
                        "source": source["name"],
                    }
                )

    unique = []
    for story in stories:
        if not duplicate_story(story, unique):
            unique.append(story)
    return unique


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

        if source["name"] == "TLDR AI":
            extracted = fetch_tldr_ai_stories(source, entry, published)
            if extracted:
                stories.extend(extracted)
                continue

        if source["name"] == "The Rundown AI":
            extracted = fetch_rundown_ai_stories(source, entry, published)
            if extracted:
                stories.extend(extracted)
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


def source_weight(source_name: str, source_weights: dict[str, float]) -> float:
    try:
        return max(0.1, float(source_weights.get(source_name, 1.0)))
    except (TypeError, ValueError):
        return 1.0


def story_priority_score(
    story: dict, source_weights: dict[str, float]
) -> tuple[float, float, float]:
    published = parse_story_date(story)
    weight = source_weight(story["source"], source_weights)
    weighted_timestamp = published.timestamp() + (
        max(0.0, weight - 1.0) * SOURCE_PRIORITY_BONUS_HOURS * 3600
    )
    return (weighted_timestamp, published.timestamp(), weight)


def select_stories(
    candidates: list[dict], generated_at: datetime, topic_sources: list[dict]
) -> list[dict]:
    source_weights = {
        source["name"]: source.get("weight", 1.0) for source in topic_sources
    }
    candidates.sort(
        key=lambda story: story_priority_score(story, source_weights), reverse=True
    )
    unique = []
    cutoff = generated_at - timedelta(days=MAX_STORY_AGE_DAYS)
    newest_allowed = generated_at + timedelta(days=1)

    for candidate in candidates:
        published = parse_story_date(candidate)
        if published < cutoff or published > newest_allowed:
            continue
        if not duplicate_story(candidate, unique):
            unique.append(candidate)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for story in unique:
        grouped[story["source"]].append(story)

    active_sources = [source for source, stories in grouped.items() if stories]
    if not active_sources:
        return []

    for source in grouped:
        grouped[source].sort(
            key=lambda story: story_priority_score(story, source_weights),
            reverse=True,
        )

    allocations = {source: 0 for source in active_sources}

    if len(active_sources) >= MAX_STORIES:
        ranked_sources = sorted(
            active_sources,
            key=lambda source: (
                source_weight(source, source_weights),
                story_priority_score(grouped[source][0], source_weights),
            ),
            reverse=True,
        )
        for source in ranked_sources[:MAX_STORIES]:
            allocations[source] = 1
    else:
        for source in active_sources:
            allocations[source] = 1

        remaining_slots = MAX_STORIES - len(active_sources)
        while remaining_slots > 0:
            candidates_for_slot = [
                source
                for source in active_sources
                if allocations[source] < len(grouped[source])
            ]
            if not candidates_for_slot:
                break

            next_source = max(
                candidates_for_slot,
                key=lambda source: (
                    source_weight(source, source_weights)
                    / (allocations[source] + 1),
                    story_priority_score(
                        grouped[source][allocations[source]], source_weights
                    ),
                ),
            )
            allocations[next_source] += 1
            remaining_slots -= 1

    selected = []
    for source, count in allocations.items():
        selected.extend(grouped[source][:count])

    return sorted(
        selected,
        key=lambda story: story_priority_score(story, source_weights),
        reverse=True,
    )


def story_key(topic_id: str, story: dict) -> str:
    return hashlib.sha256(
        f"{topic_id}:{canonical_url(story['url'])}".encode("utf-8")
    ).hexdigest()


def build_bulletin(output_topics: list[dict], config: dict, generated_at: str) -> dict:
    topic_order = {topic_id: index for index, topic_id in enumerate(DISPLAY_TOPIC_ORDER)}
    ordered_topics = sorted(
        output_topics,
        key=lambda topic: topic_order.get(topic["id"], len(topic_order)),
    )
    source_weights_by_topic = {
        topic["id"]: {
            source["name"]: source.get("weight", 1.0)
            for source in topic["sources"]
        }
        for topic in config["topics"]
    }
    selected = []
    selected_keys = set()

    for topic in ordered_topics:
        if not topic["stories"]:
            continue
        lead_count = (
            AI_BULLETIN_STORIES
            if topic["id"] == "artificial-intelligence"
            else 1
        )
        for story in topic["stories"][:lead_count]:
            key = story_key(topic["id"], story)
            selected_keys.add(key)
            selected.append(
                {
                    **story,
                    "topicId": topic["id"],
                    "topicName": topic["name"],
                    "bulletinRole": "lead",
                }
            )

    remaining = []
    for topic in ordered_topics:
        weights = source_weights_by_topic.get(topic["id"], {})
        lead_count = (
            AI_BULLETIN_STORIES
            if topic["id"] == "artificial-intelligence"
            else 1
        )
        for story in topic["stories"][lead_count:]:
            key = story_key(topic["id"], story)
            if key in selected_keys:
                continue
            remaining.append(
                (
                    story_priority_score(story, weights),
                    {
                        **story,
                        "topicId": topic["id"],
                        "topicName": topic["name"],
                        "bulletinRole": "noteworthy",
                    },
                )
            )

    remaining.sort(key=lambda item: item[0], reverse=True)
    for _, story in remaining:
        if len(selected) >= BULLETIN_STORIES:
            break
        selected_keys.add(story_key(story["topicId"], story))
        selected.append(story)

    return {
        "updatedAt": generated_at,
        "stories": selected[:BULLETIN_STORIES],
    }


def write_rss(output: dict, config: dict) -> None:
    ElementTree.register_namespace("atom", ATOM_NAMESPACE)
    ElementTree.register_namespace("ra", TOPIC_NAMESPACE)
    rss = ElementTree.Element("rss", {"version": "2.0"})
    channel = ElementTree.SubElement(rss, "channel")
    ElementTree.SubElement(channel, "title").text = "Rohaan Ahmed - My News"
    ElementTree.SubElement(channel, "link").text = f"{SITE_URL}/news.html"
    ElementTree.SubElement(channel, "description").text = (
        "An automatically curated news feed built around my areas of interest"
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

    topic_lookup = {topic["id"]: topic for topic in output["topics"]}
    bulletin_lookup = {
        story_key(story["topicId"], story): index
        for index, story in enumerate(output.get("bulletin", {}).get("stories", []), start=1)
    }

    source_sites = {
        source["name"]: source["site"]
        for topic in config["topics"]
        for source in topic["sources"]
    }
    for topic_index, configured_topic in enumerate(config["topics"], start=1):
        topic = topic_lookup.get(configured_topic["id"])
        if not topic:
            continue

        topic_updated_at = datetime.fromisoformat(
            topic["updatedAt"].replace("Z", "+00:00")
        )
        topic_marker = ElementTree.SubElement(channel, "item")
        marker_guid = ElementTree.SubElement(
            topic_marker, "guid", {"isPermaLink": "false"}
        )
        marker_guid.text = hashlib.sha256(
            f"topic:{topic['id']}:{topic['updatedAt']}".encode("utf-8")
        ).hexdigest()
        ElementTree.SubElement(topic_marker, "title").text = (
            f"{topic['name']} ({len(topic['stories'])} stories)"
        )
        ElementTree.SubElement(topic_marker, "link").text = (
            f"{SITE_URL}/news.html#topic-{topic['id']}"
        )
        ElementTree.SubElement(topic_marker, "pubDate").text = format_datetime(
            topic_updated_at
        )
        ElementTree.SubElement(topic_marker, "category").text = topic["name"]
        ElementTree.SubElement(topic_marker, "description").text = (
            f"Topic: {topic['name']}\n"
            f"Updated: {topic['updatedAt']}\n"
            f"Stories: {len(topic['stories'])}"
        )
        ElementTree.SubElement(
            topic_marker, f"{{{TOPIC_NAMESPACE}}}topicId"
        ).text = topic["id"]
        ElementTree.SubElement(
            topic_marker, f"{{{TOPIC_NAMESPACE}}}topicName"
        ).text = topic["name"]
        ElementTree.SubElement(
            topic_marker, f"{{{TOPIC_NAMESPACE}}}topicPosition"
        ).text = str(topic_index)
        ElementTree.SubElement(
            topic_marker, f"{{{TOPIC_NAMESPACE}}}kind"
        ).text = "topic"

        for story_index, story in enumerate(topic["stories"], start=1):
            item = ElementTree.SubElement(channel, "item")
            ElementTree.SubElement(item, "title").text = story["title"]
            ElementTree.SubElement(item, "link").text = story["url"]
            guid_value = hashlib.sha256(
                f"{topic['id']}:{canonical_url(story['url'])}".encode("utf-8")
            ).hexdigest()
            guid = ElementTree.SubElement(item, "guid", {"isPermaLink": "false"})
            guid.text = guid_value
            published = parse_story_date(story)
            ElementTree.SubElement(item, "pubDate").text = format_datetime(
                published
            )
            ElementTree.SubElement(item, "category").text = topic["name"]
            bulletin_position = bulletin_lookup.get(story_key(topic["id"], story))
            if bulletin_position:
                ElementTree.SubElement(item, "category").text = "Bulletin"
            source = ElementTree.SubElement(
                item,
                "source",
                {"url": source_sites.get(story["source"], f"{SITE_URL}/news.html")},
            )
            source.text = story["source"]
            ElementTree.SubElement(item, "description").text = (
                f"Topic: {topic['name']}\n"
                f"Source: {story['source']}\n"
                f"Published: {story['publishedAt']}\n"
                f"Headline: {story['title']}"
            )
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}topicId"
            ).text = topic["id"]
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}topicName"
            ).text = topic["name"]
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}topicPosition"
            ).text = str(topic_index)
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}storyPosition"
            ).text = str(story_index)
            if bulletin_position:
                ElementTree.SubElement(
                    item, f"{{{TOPIC_NAMESPACE}}}bulletinPosition"
                ).text = str(bulletin_position)
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}publishedAt"
            ).text = story["publishedAt"]
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}sourceName"
            ).text = story["source"]
            ElementTree.SubElement(
                item, f"{{{TOPIC_NAMESPACE}}}kind"
            ).text = "story"

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
        stories = select_stories(candidates, generated_datetime, topic["sources"])

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
        "bulletin": build_bulletin(output_topics, config, generated_at),
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
