# StormWatch – TODO: Nya källor och dataintegrationer

Baserat på mediasvep 2026-04-04. Prioriterat efter snabbhet att implementera vs nytta.

---

## BUGGAR – måste åtgärdas

### KRITISK: `NewsItem` saknar fältet `is_updated`
- **Fil:** `stormwatch/models.py` + `stormwatch/app.py:157,384`
- **Problem:** `app.py` anropar `dataclasses.replace(item, is_updated=is_updated)` och läser `item.is_updated`, men `NewsItem`-dataklassen har inget sådant fält. Kraschar med `TypeError` vid första nyhetsuppdatering.
- **Fix:** Lägg till `is_updated: bool = False` i `NewsItem`-dataklassen.

### KRITISK: `ai_analyzer.py` refererar till `gpt-5-mini` – modellen existerar inte
- **Fil:** `stormwatch/ai_analyzer.py:10`
- **Problem:** `_MODEL = "gpt-5-mini"` — denna modell finns inte i OpenAI:s API. Alla AI-analyser misslyckas tyst om `OPENAI_API_KEY` är satt.
- **Fix:** Byt till `"gpt-4o-mini"`.

### `history.py` sparar inte `wind_gust_dir_str` till databasen
- **Fil:** `stormwatch/history.py:27-35,39-55`
- **Problem:** Tabellschemat och INSERT saknar det nya fältet `wind_gust_dir_str` som lades till i `StationReading`. Historikdata för byvindriktning går förlorad.
- **Fix:** Lägg till kolumnen i `CREATE TABLE` och i INSERT-satsen.

### `ActivityLogWidget` är inte inkluderad i layouten
- **Fil:** `stormwatch/app.py:226-235`
- **Problem:** `ActivityLogWidget` importeras och används i `_log()`, men läggs aldrig till i `compose()`. Alla anrop till `query_one(ActivityLogWidget)` träffar `NoMatches`-except och loggposterna försvinner tyst. Widgeten existerar men är aldrig synlig/aktiv.
- **Fix:** Antingen lägg till `ActivityLogWidget` i `compose()` eller ta bort den och använd enbart `sub_title`.

### VMA-fetcher använder v2 – v3 är aktiv
- **Fil:** `stormwatch/fetchers/vma.py:13`
- **Problem:** `API_URL = "https://vmaapi.sr.se/api/v2/alerts/feed.json"` – SR:s VMA API är nu på v3. v2 kan returnera tomma svar eller felkoder.
- **Fix:** Testa `https://vmaapi.sr.se/api/v3/alerts/feed.json` och uppdatera om v3 fungerar.

### `BohuslaningenFetcher` och `StromstadsTidningFetcher` saknar datumextrahering
- **Filer:** `stormwatch/fetchers/bohuslaningen.py:82-91`, `stormwatch/fetchers/stromstadstidning.py:86-95`
- **Problem:** Alla artiklar från BL och ST får `published: None`. De hamnar alltid längst ner vid datumsortering och uppdateringsdetektering fungerar aldrig.
- **Fix:** Försök extrahera `<time datetime="...">` eller `<meta property="article:published_time">` ur HTML-sidan.

### SMHI-fetcher kan misslyckas tyst utan notifiering
- **Fil:** `stormwatch/fetchers/smhi.py:32-43`
- **Problem:** Om ingen av `CANDIDATE_URLS` svarar med 200 sätts `_working_url = None` och SMHI-varningar utelämnas helt utan att användaren informeras (förutom en logger.info). Under ett aktivt stormskeende är detta kritiskt.
- **Fix:** Logga en synlig notifiering i UI om SMHI-probing misslyckas efter start.

### `_wind_color` Beaufort-trösklar stämmer inte med `_beaufort()`
- **Fil:** `stormwatch/widgets/weather_panel.py:13-24`
- **Problem:** `_wind_color` markerar ≥24.5 m/s som "Orkan" (`bright_red`), men `_beaufort()` kallar 24.5 m/s för "Stark kuling" (Bf 9) – Orkan är ≥32.7. Färgerna ger missvisande intryck av extrem styrka för lägre vindstyrkor.
- **Fix:** Synkronisera `_wind_color`-trösklarna med Beaufort-definitionen: Storm (Bf 10) ≥28.5, Svår storm (Bf 11) ≥32.7, Orkan (Bf 12) ≥32.7.

### SR-flödets URL (`program/95`) är via det deprecated SR Open API
- **Fil:** `config.toml`
- **Problem:** `https://api.sr.se/api/rss/program/95` fungerar idag men SR:s öppna API är officiellt deprecerat. Risk för att det slutar fungera utan förvarning.
- **Fix:** Byt till `https://sverigesradio.se/rss/program/95` (direktlänk, ej via API-wrapper) eller övervaka flödet aktivt.

---

## PRIO 1 – Snabbvinn (inga API-nycklar, direkt relevant)

### Krisinformation.se
- **URL:** `https://api.krisinformation.se/v3/news`
- **Format:** JSON / CAP XML (`?format=xml`)
- **Interface:** REST GET, ingen auth
- **Filter:** `?counties=14,13` (Västra Götaland + Halland)
- **Nytta:** Aggregerar ALLA svenska myndigheters krisinfo – SMHI, Räddningstjänst, Polis, SOS Alarm i ett anrop
- **Implementation:** Ny fetcher `fetchers/krisinformation.py`, lägg under news-flödet

### SR VMA API (Viktigt meddelande till allmänheten)
- **URL:** `https://vmaapi.sr.se/api/v2/alerts/feed.json`
- **Format:** JSON / Atom RSS
- **Interface:** REST GET, ingen auth
- **Nytta:** Fångar storm-VMA i realtid innan de når radiokanaler
- **Implementation:** Ny fetcher `fetchers/vma.py`, hög score automatiskt

### SVT Väst – regional RSS (ersätter nuvarande nationella SVT)
- **RSS:** `https://www.svt.se/nyheter/lokalt/vast/rss`
- **Implementation:** Byt ut `https://www.svt.se/rss.xml` i config.toml mot regional feed

### MET Norway – Oceanforecast (havsvågor, gratis)
- **URL:** `https://api.met.no/weatherapi/oceanforecast/2.0/complete?lat=57.7&lon=11.9`
- **Format:** GeoJSON
- **Interface:** REST GET, kräver `User-Agent`-header
- **Data:** Våghöjd, vågperiod, havsström – Skagerrak/Kattegatt
- **Implementation:** Utöka `WeatherPanelWidget` med marin vädersektion

### Göteborgs Stad – Mynewsdesk pressmeddelandenfeed
- **RSS:** `https://www.mynewsdesk.com/se/goteborgsstad/pressreleases.rss`
- **Implementation:** Lägg till i `config.toml` under `[[feeds]]`

---

## PRIO 2 – Viktiga API:er (kräver registrering/nyckel)

### Trafikverket Open API
- **Registrering:** https://data.trafikverket.se/get-started (gratis API-nyckel)
- **Endpoint:** `POST https://api.trafikinfo.trafikverket.se/v2/data.json`
- **Relevanta objekt:**
  - `Situation` – trafikstörningar/vägsängningar pga storm
  - `RoadCondition` – is, översvämning, stormskador
  - `WeatherMeasurepoint` + `WeatherObservation` – vägväderstationer (vind, temp)
- **Filter:** Begränsa till länskod 14 (Västra Götaland)
- **Implementation:** Ny fetcher `fetchers/trafikverket.py`, visas i separat panel eller news-lista

### Västtrafik API
- **Registrering:** https://developer.vasttrafik.se/ (gratis)
- **Nytta:** Kollektivtrafikstörningar pga storm på västkusten
- **Implementation:** Enkelt RSS/REST-anrop mot störningsinfo

---

## PRIO 3 – Avancerade väderkällor

### SMHI Impact-Based Warnings (mer detaljerade än nuvarande)
- **URL:** `https://opendata-download-warnings.smhi.se/ibww/api/version/1/`
- **CAP XML:** `https://opendata-download-warnings.smhi.se/ibww/api/version/1/cap.xml`
- **Nytta:** Konsekvensbaserade varningar (ej bara meteorologiska), inkl. "risk för avbruten vägtrafik" osv.
- **Implementation:** Ersätt/komplettera nuvarande SMHI-fetcher

### SMHI Meteorologiska observationer (markstationer)
- **Pattern:** `https://opendata-download-metobs.smhi.se/api/version/1/parameter/{param}/station/{station}/period/latest-hour/data.json`
- **Nyckelparametrar:** 6 (vindhastighet), 3 (vindriktning), 21 (byvind)
- **Nytta:** Markstationer runt Göteborg som inte täcks av VIVA-bojar
- **Implementation:** Utöka `VivaFetcher` eller ny `SmhiObsFetcher`

### MET Norway – Locationforecast 2.0 (korskolla mot SMHI)
- **URL:** `https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=57.7&lon=11.9`
- **Format:** JSON, ingen nyckel (kräver `User-Agent`)
- **Nytta:** Oberoende prognosmodell – bra för att validera SMHI-data

### Open-Meteo Marine API (gratis, ingen nyckel)
- **URL:** `https://marine-api.open-meteo.com/v1/marine?latitude=57.7&longitude=11.9&hourly=wave_height,wind_wave_height,swell_wave_height`
- **Nytta:** 7-dagars timprognos för våghöjd, 5 km upplösning

---

## PRIO 4 – Skrapning (ingen öppen API)

### Räddningstjänsten Storgöteborg – larmlista
- **URL:** `https://www.rsgbg.se/Larm/larmlista/`
- **Interface:** HTML-tabell, paginerad, ingen RSS
- **Nytta:** Realtidslarm – stormrelaterade räddningsinsatser
- **Implementation:** Ny scraper `scrapers/rsgbg.py` med BeautifulSoup

### Elströmavbrott
Ingen öppen API för någon av dessa – kräver HTML-skrapning eller DevTools-analys av dold JSON:
- **Göteborg Energi:** `https://www.goteborgenergi.se/kundservice/avbrott/aktuella`
- **Ellevio:** `https://avbrottskarta.ellevio.se/` (kartan laddar troligen JSON-backend – inspektera network-requests)
- **Vattenfall:** `https://www.vattenfalleldistribution.se/stromavbrott/pagaende-stromavbrott/`
- **E.ON:** `https://www.eon.se/el/stromavbrott/pagaende`
- **Implementation:** Gemensam `OutageScraper`, aggregera i ny widget eller notifieringar

---

## PRIO 5 – Social media / realtidsbevakning

### X / Twitter-konton att bevaka
| Konto | Handle | Typ |
|---|---|---|
| Räddningstjänsten Storgöteborg | @rsgbg | Live larm |
| MSB | @MSBse | Nationell kris |
| SMHI | @SMHIväder | Vädervarningar |
| Göteborgs Stad | @GoteborgStad | Stadsinfo |
| Kustbevakningen | @kustbevakningen | Marin SAR |

### Hashtags
- `#StormenDave`, `#Dave`, `#Bohuslän`, `#Göteborg` + `#storm`/`#oväder`, `#SMHI` + `#varning`

### Interface-alternativ
- **Twitter/X API v2:** Kräver betald nyckel (Basic tier ~$100/mån) – ej prioriterat
- **Nitter-instanser:** Skrapa RSS från öppna Nitter-servrar om tillgängliga
- **Bluesky AT Protocol:** `https://bsky.app/profile/{handle}/rss` – gratis RSS per konto
- **Facebook:** Ingen öppen API, kräver scraping eller manuell bevakning

---

## Lokala nyhetsmedier utan RSS (kräver skrapning)

- **Lysekilsposten:** https://www.lysekilsposten.se/ – täcker Lysekil/Sotenäs
- **Strömstads Tidning:** https://www.stromstadstidning.se/ – norra Bohuslän
- **Länsstyrelsen Västra Götaland:** https://www.lansstyrelsen.se/vastra-gotaland/om-oss/nyheter-och-press.html (evakueringsbeslut, översvämningsorder)

---

## Maritima datakällor

### AIS – fartygspositioner
- **AISHub:** https://www.aishub.net/ – gratis vid bidrag av AIS-mottagare; JSON/XML/CSV
- **MarineTraffic API:** Kommersiell, betalplaner
- **Nytta:** Spåra fartyg som söker skydd, hamnstängningar

### Sjöfartsverket AAA API
- **GitHub:** https://github.com/Sjofartsverket/AAA
- **Auth:** JWT
- **Data:** Fartygsankomster/avgångar, lotsar – relevant för hamnstängningar under storm

### Kustbevakningen
- **Nyheter RSS:** Följ RSS-länk på https://www.kustbevakningen.se/nyheter/
- **Nytta:** SAR-operationer, maritima incidenter under storm
