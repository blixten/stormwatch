# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python main.py
```

Set `OPENAI_API_KEY` to enable on-demand GPT-4o-mini article analysis.

There is no build step, no test suite, and no linter configuration.

## Architecture

**Entry point:** `main.py` → sets Windows asyncio policy → instantiates `StormWatchApp`.

**Core app:** `stormwatch/app.py` — single `StormWatchApp(App)` that owns all state, schedules periodic refreshes (weather every 120s, news every 300s), coordinates fetchers, and routes Textual messages to widgets.

**Data flow:**
- Background I/O runs in `@work(exclusive=True)` Textual workers — never touches widgets directly.
- Workers post typed messages (`WeatherUpdated`, `NewsUpdated`, `ArticleTextReady`, `AiAnalysisReady`).
- `app.on_*` handlers receive messages and call widget methods on the main thread.
- `NewsListWidget` posts `ArticleHighlighted` / `ArticleSelected` back to the app.

**Fetchers** (`stormwatch/fetchers/`): one module per source — VIVA (wind/water/temp), SMHI warnings, Krisinformation, VMA, and HTML scrapers for regional newspapers (Bohuslänningen, Strömstads Tidning, P4 Väst). Additional sources run through the generic `RssFetcher`: Polisen (VGR + Halland), SVT Halland, SR P4 Göteborg, Kustbevakningen. All use `asyncio.gather(..., return_exceptions=True)`; optional sources silently fail.

**News pipeline:**
1. All fetchers run concurrently → items deduplicated by UID, then by normalized title for regional sources.
2. `ArticleClassifier` scores each item 0–10 via keyword matching; VMA items are hardcoded to score 9.
3. `Archiver` appends items with score ≥ 4 to `data/storm_dave_articles.jsonl` (append-only JSONL).
4. On user selection: `ArticleScraper` fetches full text → `AiAnalyzer` calls OpenAI → archiver updates the record.

**Persistence:**
- `data/history.db` — SQLite weather readings per station (see `stormwatch/history.py`).
- `data/storm_dave_articles.jsonl` — append-only; multiple records per UID (initial + fulltext + AI update).

**Styling:** all Textual layout/CSS lives in `stormwatch.tcss`.

**Configuration:** `config.toml` — refresh intervals, VIVA station IDs, RSS feed list, per-source enable flags.

## Key Conventions

- Data objects are `@dataclass(frozen=True)`; mutate with `dataclasses.replace()`.
- SQL field names in `history.py` are validated against `ALLOWED_HISTORY_FIELDS` / `_ALLOWED_COLUMN_NAMES` (injection prevention).
- `ArticleScraper` returns error strings rather than raising; callers display the string as-is.
- `config.toml` is parsed with `tomllib` (Python 3.11+) falling back to `tomli`.

## Known Issues

- SR P4 Väst (`fetchers/sr_p4vast.py`) scrapes a React SPA — may yield 0 articles if SR doesn't server-render the article list in the initial HTML.
- Regional HTML scrapers (Bohuslänningen, Strömstads Tidning) have no guaranteed `published` date; they try `time[datetime]` and `article:published_time` meta tag but may come up empty.
