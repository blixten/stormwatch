"""StormWatch – huvudapplikation."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Optional

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, Header, Label
from textual.containers import Horizontal, Vertical
from textual._work_decorator import work

from stormwatch.archiver import Archiver
from stormwatch.classifier import ArticleClassifier
from stormwatch.fetchers.krisinformation import KrisinformationFetcher
from stormwatch.fetchers.rss import RssFetcher
from stormwatch.fetchers.smhi import SmhiFetcher
from stormwatch.fetchers.vma import VmaFetcher
from stormwatch.fetchers.viva import VivaFetcher
from stormwatch.history import WeatherHistory
from stormwatch.models import AppState, NewsItem, StationReading
from stormwatch.scraper import ArticleScraper
from stormwatch.widgets.article_panel import ArticlePanelWidget
from stormwatch.widgets.history_panel import HistoryPanelWidget
from stormwatch.widgets.news_list import NewsListWidget
from stormwatch.widgets.weather_panel import WeatherPanelWidget

logger = logging.getLogger(__name__)

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


def _load_config(path: str = "config.toml") -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        logger.error("config.toml saknas")
        return _default_config()
    except Exception as exc:
        logger.error("Fel vid inläsning av config: %s", exc)
        return _default_config()


def _default_config() -> dict:
    return {
        "app": {"news_refresh_seconds": 300, "weather_refresh_seconds": 120},
        "stations": [
            {"id": 114, "label": "Vinga"},
            {"id": 70, "label": "Mitholmarna"},
            {"id": 99, "label": "Göteborg (Karet)"},
        ],
        "feeds": [
            {"url": "https://www.gp.se/rss", "source": "GP", "optional": False},
            {"url": "https://www.bohuslaningen.se/rss", "source": "BL", "optional": False},
            {"url": "https://www.svt.se/nyheter/lokalt/vast/rss", "source": "SVT", "optional": True},
            {"url": "https://www.mynewsdesk.com/se/goteborgsstad/pressreleases.rss", "source": "GOT", "optional": True},
        ],
        "smhi": {"enabled": True, "counties": [14, 13]},
        "krisinformation": {"enabled": True, "counties": [14, 13]},
        "vma": {"enabled": True},
        "classifier": {"keywords": {}},
    }


def _build_news_items(
    raw: list[dict], classifier: ArticleClassifier
) -> list[NewsItem]:
    seen: set[str] = set()
    items: list[NewsItem] = []
    for entry in raw:
        uid = entry["uid"]
        if uid in seen:
            continue
        seen.add(uid)
        items.append(NewsItem(
            uid=uid,
            source=entry["source"],
            title=entry["title"],
            url=entry["url"],
            summary=entry.get("summary", ""),
            published=entry.get("published"),
            score=classifier.score(entry["title"], entry.get("summary", "")),
        ))
    return items


def _sort_news(items: list[NewsItem], by_score: bool, high_only: bool) -> list[NewsItem]:
    filtered = [i for i in items if i.score >= 7] if high_only else items
    if by_score:
        return sorted(filtered, key=lambda i: (-(i.score), -(i.published.timestamp() if i.published else 0)))
    return sorted(filtered, key=lambda i: -(i.published.timestamp() if i.published else 0))


# ─── Meddelanden ────────────────────────────────────────────────────────────

class WeatherUpdated(Message):
    def __init__(self, readings: list[StationReading]) -> None:
        self.readings = readings
        super().__init__()

class NewsUpdated(Message):
    def __init__(self, news: list[NewsItem]) -> None:
        self.news = news
        super().__init__()

class ArticleTextReady(Message):
    def __init__(self, item: NewsItem, text: str) -> None:
        self.item = item
        self.text = text
        super().__init__()


# ─── Huvudapp ────────────────────────────────────────────────────────────────

class StormWatchApp(App):
    CSS_PATH = str(__import__("pathlib").Path(__file__).parent.parent / "stormwatch.tcss")
    TITLE = "StormWatch"
    SUB_TITLE = "Stormen Dave – svenska västkusten"

    BINDINGS = [
        Binding("up,k",        "cursor_up",       "Upp",          show=False),
        Binding("down,j",      "cursor_down",      "Ner",          show=False),
        Binding("enter",       "open_article",     "Hämta artikel"),
        Binding("r",           "refresh_news",     "Uppdatera nyheter"),
        Binding("R",           "refresh_weather",  "Uppdatera väder"),
        Binding("f",           "filter_toggle",    "Filtrera hög relevans"),
        Binding("s",           "sort_toggle",      "Sortering"),
        Binding("o",           "open_browser",     "Öppna i webbläsare"),
        Binding("h",           "history_toggle",   "Historik/Graf"),
        Binding("q,ctrl+c",    "quit",             "Avsluta"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._state = AppState()
        self._config: dict = {}
        self._http: Optional[httpx.AsyncClient] = None
        self._classifier: Optional[ArticleClassifier] = None
        self._smhi = SmhiFetcher()
        self._archiver = Archiver()
        self._history = WeatherHistory()
        self._pending_article: Optional[NewsItem] = None
        self._known_high_uids: set[str] = set()
        self._history_visible: bool = False

    # ─── Layout ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-layout"):
            yield NewsListWidget(id="news-panel")
            with Vertical(id="right-panel"):
                yield WeatherPanelWidget(id="weather-panel")
                yield Label("", id="right-divider")
                yield ArticlePanelWidget(id="article-panel")
                yield HistoryPanelWidget(id="history-panel")
        yield Footer()

    # ─── Initiering ──────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        self._config = _load_config()
        # Använd inbyggda standardnyckelord (config-override stöds ej ännu)
        self._classifier = ArticleClassifier()

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=8.0),
            follow_redirects=True,
            headers={"User-Agent": "StormWatch/1.0"},
        )

        # Sond SMHI i bakgrunden
        smhi_cfg = self._config.get("smhi", {})
        if smhi_cfg.get("enabled", True):
            self._smhi_counties = smhi_cfg.get("counties", [14, 13])
            self._do_probe_smhi()

        # Hämta data direkt vid start
        self.refresh_weather()
        self.refresh_news()

        # Schemalägg periodisk uppdatering
        app_cfg = self._config.get("app", {})
        self.set_interval(app_cfg.get("weather_refresh_seconds", 120), self.refresh_weather)
        self.set_interval(app_cfg.get("news_refresh_seconds", 300), self.refresh_news)

    async def on_unmount(self) -> None:
        if self._http:
            await self._http.aclose()
        self._history.close()

    @work(name="smhi_probe")
    async def _do_probe_smhi(self) -> None:
        if self._http:
            await self._smhi.probe(
                getattr(self, "_smhi_counties", [14, 13]), self._http
            )

    # ─── Bakgrundsarbetare ───────────────────────────────────────────────────

    @work(exclusive=True, name="weather_refresh")
    async def refresh_weather(self) -> None:
        stations = self._config.get("stations", [])
        if not stations or not self._http:
            return
        fetcher = VivaFetcher()
        readings = await fetcher.fetch_all(stations, self._http)
        self.post_message(WeatherUpdated(readings))

    @work(exclusive=True, name="news_refresh")
    async def refresh_news(self) -> None:
        feeds = self._config.get("feeds", [])
        smhi_cfg = self._config.get("smhi", {})
        kris_cfg = self._config.get("krisinformation", {})
        vma_cfg = self._config.get("vma", {})
        if not self._http or not self._classifier:
            return

        rss_fetcher = RssFetcher()
        raw = await rss_fetcher.fetch_all(feeds, self._http)

        if smhi_cfg.get("enabled", True) and self._smhi._working_url:
            smhi_raw = await self._smhi.fetch_warnings(
                smhi_cfg.get("counties", [14, 13]), self._http
            )
            raw.extend(smhi_raw)

        if kris_cfg.get("enabled", True):
            kris_fetcher = KrisinformationFetcher()
            kris_raw = await kris_fetcher.fetch_news(
                kris_cfg.get("counties", [14, 13]), self._http
            )
            raw.extend(kris_raw)

        if vma_cfg.get("enabled", True):
            vma_fetcher = VmaFetcher()
            vma_raw = await vma_fetcher.fetch_alerts(self._http)
            raw.extend(vma_raw)

        items = _build_news_items(raw, self._classifier)
        items = _sort_news(items, self._state.sort_by_score, self._state.filter_high_only)
        self._state.news = items

        saved = self._archiver.save_items(items)
        if saved:
            logger.info("Arkiverade %d nya artiklar", saved)

        max_items = self._config.get("app", {}).get("max_news_items", 80)
        self.post_message(NewsUpdated(items[:max_items]))

    @work(exclusive=True, name="article_scrape")
    async def _scrape_article(self, item: NewsItem) -> None:
        if not self._http:
            return
        self._pending_article = item
        panel = self.query_one(ArticlePanelWidget)
        panel.show_loading(item)
        scraper = ArticleScraper()
        text = await scraper.fetch_text(item.url, self._http)
        self.post_message(ArticleTextReady(item, text))

    # ─── Meddelandehanterare ─────────────────────────────────────────────────

    def on_weather_updated(self, msg: WeatherUpdated) -> None:
        self._state.readings = msg.readings
        self._state.last_weather_refresh = datetime.now()
        self._history.save(msg.readings)
        self.query_one(WeatherPanelWidget).refresh_display(msg.readings)
        if self._history_visible:
            self.query_one(HistoryPanelWidget).refresh_display(self._history)

    def on_news_updated(self, msg: NewsUpdated) -> None:
        self._state.last_news_refresh = datetime.now()

        new_high = [
            i for i in msg.news
            if i.score >= 7 and i.uid not in self._known_high_uids
        ]
        if new_high:
            titles = ", ".join(f'"{i.title[:40]}"' for i in new_high[:2])
            suffix = f" (+{len(new_high) - 2} till)" if len(new_high) > 2 else ""
            self.notify(
                f"{titles}{suffix}",
                title=f"⚡ {len(new_high)} ny/nya högrelevant(a)",
                severity="warning",
                timeout=10,
            )
        self._known_high_uids.update(i.uid for i in msg.news if i.score >= 7)

        self.query_one(NewsListWidget).refresh_news(msg.news, new_count=len(new_high))

    def on_article_text_ready(self, msg: ArticleTextReady) -> None:
        panel = self.query_one(ArticlePanelWidget)
        panel.show_article(msg.item, msg.text)
        self._archiver.update_fulltext(msg.item, msg.text)

    def on_news_list_widget_article_highlighted(
        self, msg: NewsListWidget.ArticleHighlighted
    ) -> None:
        self.query_one(ArticlePanelWidget).show_summary(msg.item)

    def on_news_list_widget_article_selected(
        self, msg: NewsListWidget.ArticleSelected
    ) -> None:
        self._scrape_article(msg.item)

    # ─── Tangentbordsbindningar ───────────────────────────────────────────────

    def action_cursor_up(self) -> None:
        self.query_one(NewsListWidget).move_up()

    def action_cursor_down(self) -> None:
        self.query_one(NewsListWidget).move_down()

    def action_open_article(self) -> None:
        lv = self.query_one("#news-list")
        lv.action_select_cursor()

    def action_refresh_news(self) -> None:
        self.refresh_news()

    def action_refresh_weather(self) -> None:
        self.refresh_weather()

    def action_filter_toggle(self) -> None:
        self._state.filter_high_only = not self._state.filter_high_only
        items = _sort_news(
            self._state.news,
            self._state.sort_by_score,
            self._state.filter_high_only,
        )
        max_items = self._config.get("app", {}).get("max_news_items", 80)
        self.query_one(NewsListWidget).refresh_news(items[:max_items])
        status = "FILTRERAT (hög relevans)" if self._state.filter_high_only else "alla nyheter"
        self.notify(f"Visar {status}", timeout=2)

    def action_sort_toggle(self) -> None:
        self._state.sort_by_score = not self._state.sort_by_score
        items = _sort_news(
            self._state.news,
            self._state.sort_by_score,
            self._state.filter_high_only,
        )
        max_items = self._config.get("app", {}).get("max_news_items", 80)
        self.query_one(NewsListWidget).refresh_news(items[:max_items])
        mode = "score" if self._state.sort_by_score else "tid"
        self.notify(f"Sorterat efter {mode}", timeout=2)

    def action_history_toggle(self) -> None:
        self._history_visible = not self._history_visible
        article = self.query_one(ArticlePanelWidget)
        history = self.query_one(HistoryPanelWidget)
        if self._history_visible:
            article.add_class("hidden")
            history.add_class("visible")
            history.refresh_display(self._history)
        else:
            article.remove_class("hidden")
            history.remove_class("visible")

    def action_open_browser(self) -> None:
        import webbrowser
        from stormwatch.widgets.news_list import NewsRow
        lv = self.query_one("#news-list")
        item = lv.highlighted_child
        if item and isinstance(item, NewsRow):
            webbrowser.open(item.item.url)
