from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests


ROOT = Path(__file__).resolve().parents[1]
MEDIUM_FEED_URL = "https://medium.com/feed/@space.sapper"
IMPORT_DIR = ROOT / "content" / "medium-field-notes"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "h4",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
VOID_TAGS = {"br", "hr", "img"}
ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"alt", "src", "width", "height"},
}


def clean_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(("source", "sk", "gi", "tracking"))
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "medium-note"


def medium_id(entry: dict) -> str:
    guid = entry.get("id") or entry.get("guid") or entry.get("link", "")
    match = re.search(r"([a-f0-9]{12,})", guid)
    if match:
        return match.group(1)
    return slugify(guid)


def parsed_date(entry: dict) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).date().isoformat()
    return datetime.now(timezone.utc).date().isoformat()


class MediumSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.paragraphs: list[str] = []
        self._paragraph_text: list[str] = []
        self._in_paragraph = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}

        if tag == "img" and (
            "medium.com/_/stat" in attr_map.get("src", "")
            or attr_map.get("width") == "1"
            and attr_map.get("height") == "1"
        ):
            return

        if self._skip_depth:
            self._skip_depth += 1
            return

        if tag not in ALLOWED_TAGS:
            return

        if tag == "p":
            self._in_paragraph = True
            self._paragraph_text = []

        rendered_attrs = []
        for name in ALLOWED_ATTRS.get(tag, set()):
            value = attr_map.get(name)
            if not value:
                continue
            if name in {"href", "src"}:
                if value.startswith(("javascript:", "data:")):
                    continue
                value = clean_url(value)
            rendered_attrs.append(f' {name}="{html.escape(value, quote=True)}"')

        if tag == "a":
            rendered_attrs.append(' rel="noopener noreferrer"')

        if tag == "img":
            rendered_attrs.append(' loading="lazy"')
            rendered_attrs.append(' decoding="async"')

        suffix = " /" if tag in VOID_TAGS else ""
        self.output.append(f"<{tag}{''.join(rendered_attrs)}{suffix}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_depth:
            self._skip_depth -= 1
            return

        if tag == "p" and self._in_paragraph:
            paragraph = re.sub(r"\s+", " ", "".join(self._paragraph_text)).strip()
            if paragraph:
                self.paragraphs.append(paragraph)
            self._in_paragraph = False
            self._paragraph_text = []

        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.output.append(html.escape(data))
        if self._in_paragraph:
            self._paragraph_text.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&#{name};"))


def sanitize_medium_html(raw_html: str) -> tuple[str, list[str]]:
    parser = MediumSanitizer()
    parser.feed(raw_html)
    parser.close()
    return "".join(parser.output).strip(), parser.paragraphs


def derive_summary(paragraphs: list[str]) -> str:
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        if lowered.startswith("disclaimer"):
            continue
        if len(paragraph) < 40:
            continue
        return paragraph[:260].rsplit(" ", 1)[0].rstrip(".,;:") + "."
    return "Imported from Medium."


def load_existing() -> dict[str, dict]:
    imports: dict[str, dict] = {}
    if not IMPORT_DIR.exists():
        return imports
    for path in IMPORT_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        item_id = item.get("id") or path.stem
        imports[item_id] = item
    return imports


def main() -> int:
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    imports = load_existing()
    response = requests.get(MEDIUM_FEED_URL, timeout=30)
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    if feed.bozo:
        raise ValueError(f"Medium feed could not be parsed: {feed.bozo_exception}")

    updated_count = 0
    for entry in feed.entries:
        item_id = medium_id(entry)
        title = str(entry.get("title", "")).strip()
        if not title:
            continue

        content_blocks = entry.get("content") or []
        raw_content = content_blocks[0].get("value", "") if content_blocks else ""
        article_html, paragraphs = sanitize_medium_html(raw_content)
        slug = slugify(title)
        if not SLUG_PATTERN.fullmatch(slug):
            slug = item_id

        item = {
            "id": item_id,
            "title": title,
            "slug": slug,
            "date": parsed_date(entry),
            "updated": str(entry.get("updated", "") or entry.get("published", "")),
            "summary": derive_summary(paragraphs),
            "tags": [tag.term for tag in entry.get("tags", []) if getattr(tag, "term", "")],
            "source": "Medium",
            "sourceUrl": clean_url(str(entry.get("link", ""))),
            "articleHtml": article_html,
        }

        previous = imports.get(item_id)
        previous_core = {
            key: value for key, value in (previous or {}).items() if key != "importedAt"
        }
        if previous_core == item:
            continue

        item["importedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        updated_count += 1
        imports[item_id] = item
        (IMPORT_DIR / f"{item_id}.json").write_text(
            json.dumps(item, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(f"Imported or refreshed {updated_count} Medium Field Notes item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
