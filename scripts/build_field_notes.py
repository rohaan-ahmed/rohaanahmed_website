from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import markdown
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "content" / "field-notes"
OUTPUT_DIR = ROOT / "field-notes"
INDEX_PATH = ROOT / "data" / "field-notes.json"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_post(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError("missing YAML front matter")

    try:
        _, front_matter, body = raw.split("---\n", 2)
    except ValueError as error:
        raise ValueError("front matter must end with ---") from error

    metadata = yaml.safe_load(front_matter) or {}
    missing = [key for key in ("title", "date") if not metadata.get(key)]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    slug = metadata.get("slug") or path.stem
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(f"invalid slug: {slug}")

    post_date = metadata["date"]
    if isinstance(post_date, (date, datetime)):
        post_date = post_date.isoformat()[:10]
    else:
        post_date = str(post_date)
        date.fromisoformat(post_date)

    summary = str(metadata.get("summary", "")).strip()
    if not summary:
        plain_body = re.sub(r"[#*_>`\[\]()!-]", " ", body)
        summary = re.sub(r"\s+", " ", plain_body).strip()[:220].rstrip()

    metadata.update(
        {
            "slug": slug,
            "date": post_date,
            "summary": summary,
            "tags": [str(tag) for tag in metadata.get("tags", [])],
            "sample": bool(metadata.get("sample", False)),
        }
    )
    return metadata, body.strip()


def article_page(metadata: dict, article_html: str) -> str:
    title = html.escape(metadata["title"])
    summary = html.escape(metadata["summary"])
    post_date = html.escape(metadata["date"])
    display_date = html.escape(
        date.fromisoformat(metadata["date"])
        .strftime("%b %d, %Y")
        .replace(" 0", " ")
    )
    tags = "".join(
        f'<span class="tag">{html.escape(tag)}</span>'
        for tag in metadata["tags"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{summary}">
    <title>{title} | My Field Notes | Rohaan Ahmed</title>
    <link rel="stylesheet" href="../styles.css?v=content-v4">
    <link rel="stylesheet" href="../content.css?v=content-v4">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Black+Ops+One&family=Share+Tech+Mono&family=Sora:wght@400;600;700;800&family=Work+Sans:wght@400;500;600&display=swap" rel="stylesheet">
</head>
<body class="content-page article-page">
    <header class="content-navbar">
        <div class="content-nav-inner">
            <a class="content-brand" href="../index.html" aria-label="Rohaan Ahmed home">RA</a>
            <nav class="content-nav-links" aria-label="Content">
                <a href="../news.html">My News</a>
                <a class="active" href="../field-notes.html">My Field Notes</a>
            </nav>
        </div>
    </header>
    <main class="content-main">
        <article class="article-shell">
            <a class="back-link" href="../field-notes.html">&larr; All My Field Notes</a>
            <header class="article-header">
                <div class="content-kicker">My Field Notes</div>
                <h1>{title}</h1>
                <p class="article-summary">{summary}</p>
                <time datetime="{post_date}">{display_date}</time>
                <div class="article-tags">{tags}</div>
            </header>
            <div class="article-body">
                {article_html}
            </div>
        </article>
    </main>
    <footer class="footer content-footer">
        <div class="container">
            <p class="footer-text">&copy; <span id="current-year"></span> Rohaan Ahmed. All rights reserved.</p>
        </div>
    </footer>
    <button class="theme-toggle" id="theme-toggle" aria-label="Toggle Tactical Theme" aria-pressed="false">
        <span class="theme-toggle-text">Tactical Theme</span>
    </button>
    <script src="../content.js?v=content-v4"></script>
</body>
</html>
"""


def main() -> int:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = []

    for path in sorted(CONTENT_DIR.glob("*.md")):
        try:
            metadata, body = parse_post(path)
        except Exception as error:
            raise ValueError(f"{path.relative_to(ROOT)}: {error}") from error

        rendered = markdown.markdown(
            body,
            extensions=["fenced_code", "tables", "sane_lists"],
            output_format="html5",
        )
        output_path = OUTPUT_DIR / f"{metadata['slug']}.html"
        output_path.write_text(article_page(metadata, rendered), encoding="utf-8")
        posts.append(
            {
                "title": metadata["title"],
                "date": metadata["date"],
                "summary": metadata["summary"],
                "url": f"field-notes/{metadata['slug']}.html",
                "tags": metadata["tags"],
                "sample": metadata["sample"],
            }
        )

    expected_files = {post["url"].split("/")[-1] for post in posts}
    for old_page in OUTPUT_DIR.glob("*.html"):
        if old_page.name not in expected_files:
            old_page.unlink()

    posts.sort(key=lambda post: (post["date"], post["title"]), reverse=True)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(
            {
                "generatedAt": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "posts": posts,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(posts)} Field Notes post(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
