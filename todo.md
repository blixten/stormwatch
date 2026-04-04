# StormWatch – TODO: Nya källor och dataintegrationer

Baserat på mediasvep 2026-04-04. Prioriterat efter snabbhet att implementera vs nytta.

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
