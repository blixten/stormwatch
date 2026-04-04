"""StormWatch – huvudapplikation."""
from __future__ import annotations

import logging
import re
import sys
import unicodedata
from dataclasses import replace
from datetime import datetime
from typing import Optional

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Footer, Header, Label
from textual.containers import Horizontal, Vertical
from textual._work_decorator import work

from stormwatch.archiver import Archiver
from stormwatch.ai_analyzer import AiAnalyzer
from stormwatch.classifier import ArticleClassifier
from stormwatch.fetchers.bohuslaningen import BohuslaningenFetcher
from stormwatch.fetchers.krisinformation import KrisinformationFetcher
from stormwatch.fetchers.rss import RssFetcher
from stormwatch.fetchers.smhi import SmhiFetcher
from stormwatch.fetchers.stromstadstidning import StromstadsTidningFetcher
from stormwatch.fetchers.vma import VmaFetcher
from stormwatch.fetchers.viva import VivaFetcher
from stormwatch.history import WeatherHistory
from stormwatch.models import AppState, NewsItem, StationReading
from stormwatch.scraper import ArticleScraper
from stormwatch.widgets.activity_log import ActivityLogWidget
from stormwatch.widgets.article_panel import ArticlePanelWidget
from stormwatch.widgets.history_panel import HistoryPanelWidget
from stormwatch.widgets.news_list import NewsListWidget
from stormwatch.widgets.weather_panel import WeatherPanelWidget

logger = logging.getLogger(__name__)
VMA_PRIORITY_SCORE = 9

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
            {"url": "https://www.svt.se/nyheter/lokalt/vast/rss", "source": "SVT", "optional": True},
            {"url": "https://www.mynewsdesk.com/se/goteborgsstad/pressreleases.rss", "source": "GOT", "optional": True},
            {"url": "https://www.mynewsdesk.com/se/sos_alarm/pressreleases.rss", "source": "SOS", "optional": True},
        ],
        "smhi": {"enabled": True, "counties": [14, 13]},
        "krisinformation": {"enabled": True, "counties": [14, 13]},
        "vma": {"enabled": True},
        "bohuslaningen": {"enabled": True},
        "classifier": {"keywords": {}},
    }


# Lokala/regionala källor med överlappande bevakning (GP, Bohuslänningen, Strömstads Tidning).
# Artiklar med identisk normaliserad titel deduplificeras inbördes eftersom dessa tidningar
# ofta publicerar samma TT-telegram eller täcker exakt samma lokala händelse.
_REGIONAL_SOURCES: frozenset[str] = frozenset({"GP", "BL", "ST"})


def _normalize_title(title: str) -> str:
    """Normaliserar titel för dubblettdetektering (GP/BL/ST)."""
    t = title.lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_news_items(
    raw: list[dict], classifier: ArticleClassifier
) -> list[NewsItem]:
    seen_uids: set[str] = set()
    seen_regional_titles: set[str] = set()
    items: list[NewsItem] = []
    for entry in raw:
        uid = entry["uid"]
        if uid in seen_uids:
            continue
        seen_uids.add(uid)

        # Dedupliceringskontroll för regionala källor (GP/BL/ST)
        source = entry.get("source", "")
        if source in _REGIONAL_SOURCES:
            norm = _normalize_title(entry.get("title", ""))
            if norm and norm in seen_regional_titles:
                continue
            if norm:
                seen_regional_titles.add(norm)

        if entry.get("source") == "VMA":
            score = VMA_PRIORITY_SCORE
        else:
            score = classifier.score(entry["title"], entry.get("summary", ""))

        items.append(NewsItem(
            uid=uid,
            source=entry["source"],
            title=entry["title"],
            url=entry["url"],
            summary=entry.get("summary", ""),
            published=entry.get("published"),
            score=score,
        ))
    return items


def _sort_news(items: list[NewsItem], by_score: bool, high_only: bool) -> list[NewsItem]:
    filtered = [i for i in items if i.score >= 7] if high_only else items
    if by_score:
        return sorted(filtered, key=lambda i: (-(i.score), -(i.published.timestamp() if i.published else 0)))
    return sorted(filtered, key=lambda i: -(i.published.timestamp() if i.published else 0))


def _mark_updated_items(
    items: list[NewsItem],
    known_published: dict[str, Optional[datetime]],
) -> list[NewsItem]:
    """Markerar artiklar vars publiceringsdatum ändrats sedan förra hämtningen."""
    result: list[NewsItem] = []
    for item in items:
        prev = known_published.get(item.uid)
        is_updated = (
            prev is not None
            and item.published is not None
            and item.published > prev
        )
        result.append(replace(item, is_updated=is_updated) if is_updated else item)
    return result


# ─── Meddelanden ────────────────────────────────────────────────────────────

class WeatherUpdated(Message):
    def __init__(self, readings: list[StationReading]) -> None:
        self.readings = readings
        super().__init__()

class NewsUpdated(Message):
    def __init__(self, news: list[NewsItem], updated_count: int = 0) -> None:
        self.news = news
        self.updated_count = updated_count
        super().__init__()

class ArticleTextReady(Message):
    def __init__(self, item: NewsItem, text: str) -> None:
        self.item = item
        self.text = text
        super().__init__()

class AiAnalysisReady(Message):
    def __init__(self, item: NewsItem, ai_score: Optional[int], ai_analysis: Optional[str]) -> None:
        self.item = item
        self.ai_score = ai_score
        self.ai_analysis = ai_analysis
        super().__init__()


# ─── Huvudapp ────────────────────────────────────────────────────────────────

class StormWatchApp(App):
    CSS_PATH = str(__import__("pathlib").Path(__file__).parent.parent / "stormwatch.tcss")
    TITLE = "StormWatch"
    SUB_TITLE = "Stormen Dave – svenska västkusten"
    _DEFAULT_SUBTITLE = "Stormen Dave – svenska västkusten"

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
        self._ai_analyzer: Optional[AiAnalyzer] = None
        self._smhi = SmhiFetcher()
        self._archiver = Archiver()
        self._history = WeatherHistory()
        self._pending_article: Optional[NewsItem] = None
        self._known_high_uids: set[str] = set()
        self._known_published: dict[str, Optional[datetime]] = {}
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

    def _log(self, text: str) -> None:
        """Uppdaterar titelraden och lägger till en post i aktivitetsloggen."""
        self.sub_title = text
        try:
            self.query_one(ActivityLogWidget).add_entry(text)
        except NoMatches:
            pass

    def _restore_subtitle(self) -> None:
        """Återställer titelradens undertext till standardvärdet."""
        self.sub_title = self._DEFAULT_SUBTITLE

    async def on_mount(self) -> None:
        self._config = _load_config()
        # Använd inbyggda standardnyckelord (config-override stöds ej ännu)
        self._classifier = ArticleClassifier()

        # Initiera AI-analysator om API-nyckel finns
        self._ai_analyzer = AiAnalyzer()
        if self._ai_analyzer.is_available():
            logger.info("OpenAI GPT-analys aktiverad")
        else:
            logger.info("OpenAI GPT-analys inaktiverad (OPENAI_API_KEY saknas)")

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
        self._log("Söker SMHI API-URL…")
        if self._http:
            await self._smhi.probe(
                getattr(self, "_smhi_counties", [14, 13]), self._http
            )
        self._log("SMHI API redo")

    # ─── Bakgrundsarbetare ───────────────────────────────────────────────────

    @work(exclusive=True, name="weather_refresh")
    async def refresh_weather(self) -> None:
        all_stations = self._config.get("stations", [])
        # Filtrera bort stationer med enabled=false
        stations = [s for s in all_stations if s.get("enabled", True)]
        if not stations or not self._http:
            return
        self._log(f"Hämtar väder för {len(stations)} station(er)…")
        fetcher = VivaFetcher()
        readings = await fetcher.fetch_all(stations, self._http)
        self._log(f"Väder uppdaterat – {len(readings)} stationer")
        self.post_message(WeatherUpdated(readings))
        self._restore_subtitle()

    @work(exclusive=True, name="news_refresh")
    async def refresh_news(self) -> None:
        feeds = self._config.get("feeds", [])
        smhi_cfg = self._config.get("smhi", {})
        kris_cfg = self._config.get("krisinformation", {})
        vma_cfg = self._config.get("vma", {})
        bl_cfg = self._config.get("bohuslaningen", {})
        st_cfg = self._config.get("stromstadstidning", {})
        if not self._http or not self._classifier:
            return

        self._log("Hämtar RSS-flöden…")
        rss_fetcher = RssFetcher()
        raw = await rss_fetcher.fetch_all(feeds, self._http)
        self._log(f"RSS: {len(raw)} artiklar hämtade")

        if smhi_cfg.get("enabled", True) and self._smhi._working_url:
            self._log("Hämtar SMHI-varningar…")
            smhi_raw = await self._smhi.fetch_warnings(
                smhi_cfg.get("counties", [14, 13]), self._http
            )
            raw.extend(smhi_raw)
            self._log(f"SMHI: {len(smhi_raw)} varning(ar)")

        if kris_cfg.get("enabled", True):
            self._log("Hämtar krisinformation…")
            kris_fetcher = KrisinformationFetcher()
            kris_raw = await kris_fetcher.fetch_news(
                kris_cfg.get("counties", [14, 13]), self._http
            )
            raw.extend(kris_raw)
            self._log(f"Krisinformation: {len(kris_raw)} poster")

        if vma_cfg.get("enabled", True):
            self._log("Kontrollerar VMA-larm…")
            vma_fetcher = VmaFetcher()
            vma_raw = await vma_fetcher.fetch_alerts(self._http)
            raw.extend(vma_raw)
            self._log(f"VMA: {len(vma_raw)} larm")

        if bl_cfg.get("enabled", True):
            self._log("Hämtar Bohuslänningen…")
            bl_fetcher = BohuslaningenFetcher()
            bl_raw = await bl_fetcher.fetch_news(self._http)
            raw.extend(bl_raw)
            self._log(f"BL: {len(bl_raw)} artiklar")

        if st_cfg.get("enabled", True):
            self._log("Hämtar Strömstads Tidning…")
            st_fetcher = StromstadsTidningFetcher()
            st_raw = await st_fetcher.fetch_news(self._http)
            raw.extend(st_raw)
            self._log(f"ST: {len(st_raw)} artiklar")

        self._log(f"Klassificerar {len(raw)} artiklar…")
        items = _build_news_items(raw, self._classifier)
        items = _mark_updated_items(items, self._known_published)

        # Uppdatera kända publiceringsdatum
        for item in items:
            if item.published is not None:
                self._known_published[item.uid] = item.published

        items = _sort_news(items, self._state.sort_by_score, self._state.filter_high_only)
        self._state.news = items

        saved = self._archiver.save_items(items)
        if saved:
            logger.info("Arkiverade %d nya artiklar", saved)

        updated_count = sum(1 for i in items if i.is_updated)
        max_items = self._config.get("app", {}).get("max_news_items", 80)
        self._log(f"Nyhetslistan uppdaterad – {len(items)} artiklar")
        self.post_message(NewsUpdated(items[:max_items], updated_count=updated_count))
        self._restore_subtitle()

    @work(exclusive=True, name="article_scrape")
    async def _scrape_article(self, item: NewsItem) -> None:
        if not self._http:
            return
        self._pending_article = item
        panel = self.query_one(ArticlePanelWidget)
        panel.show_loading(item)
        self._log(f"Hämtar fulltext: {item.title[:50]}…")
        scraper = ArticleScraper()
        text = await scraper.fetch_text(item.url, self._http)
        self._log("Fulltext hämtad")
        self.post_message(ArticleTextReady(item, text))

        # AI-relevansbedömning om tillgänglig
        if self._ai_analyzer and self._ai_analyzer.is_available():
            self._log("Analyserar artikel med AI…")
            ai_score, ai_analysis = await self._ai_analyzer.analyze(
                item.title, item.summary, text
            )
            self._log(
                f"AI-analys klar – relevans {ai_score}/10"
                if ai_score is not None
                else "AI-analys klar"
            )
            self.post_message(AiAnalysisReady(item, ai_score, ai_analysis))

        self._restore_subtitle()

    # ─── Meddelandehanterare ─────────────────────────────────────────────────

    def on_weather_updated(self, msg: WeatherUpdated) -> None:
        self._state.readings = msg.readings
        self._state.last_weather_refresh = datetime.now()
        self._history.save(msg.readings)
        self.query_one(WeatherPanelWidget).refresh_display(msg.readings, self._history)
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

        self.query_one(NewsListWidget).refresh_news(
            msg.news,
            new_count=len(new_high),
            updated_count=msg.updated_count,
        )

    def on_article_text_ready(self, msg: ArticleTextReady) -> None:
        panel = self.query_one(ArticlePanelWidget)
        panel.show_article(msg.item, msg.text)
        self._archiver.update_fulltext(msg.item, msg.text)

    def on_ai_analysis_ready(self, msg: AiAnalysisReady) -> None:
        panel = self.query_one(ArticlePanelWidget)
        panel.show_ai_analysis(msg.item, msg.ai_score, msg.ai_analysis)
        self._archiver.update_ai_analysis(msg.item, msg.ai_score, msg.ai_analysis)

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
