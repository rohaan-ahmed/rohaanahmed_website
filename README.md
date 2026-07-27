# Rohaan Ahmed

Personal website built with vanilla HTML, CSS, and JavaScript and hosted on
GitHub Pages.

## Field Notes workflow

Field Notes live in `content/field-notes/` as Markdown files. Each file needs YAML front
matter with a title and date:

```markdown
---
title: A Note Title
date: 2026-07-26
summary: A short description used on the Field Notes page.
tags:
  - Artificial Intelligence
---

The article starts here.
```

Add, edit, or delete a Markdown file, then commit and push the change. GitHub
Actions rebuilds `data/field-notes.json` and the article pages in `field-notes/`.

On this computer, double-click `Sync Field Notes.cmd` after changing the
Markdown files. It mirrors the folder into the working Git checkout, commits the
changes, and pushes them so GitHub Actions can publish the generated pages.

To build locally:

```powershell
python -m pip install -r requirements.txt
python scripts/build_field_notes.py
```

## News workflow

News sources are configured in `news-sources.json`. The automated workflow reads
the feeds, removes duplicate stories within each topic, ignores stories older
than 10 days, balances the selection across sources, and keeps up to ten current
stories. Each refresh updates both `data/news.json` for the webpage and
`news.xml` for RSS readers and other websites.

GitHub Actions runs at 13:00, 16:00, 19:00, and 22:00 UTC. These correspond to
9 a.m., noon, 3 p.m., and 6 p.m. Toronto time while daylight saving time is in
effect; during standard time, they run one hour earlier locally.

To refresh locally:

```powershell
python -m pip install -r requirements.txt
python scripts/update_news.py
```

## Local preview

The content pages load JSON, so preview the site through a local web server:

```powershell
python -m http.server 8000
```

Then open `http://localhost:8000/news.html` or
`http://localhost:8000/field-notes.html`.
