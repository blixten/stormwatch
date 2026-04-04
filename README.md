# StormWatch

StormWatch är ett terminalbaserat övervakningsverktyg för väder, vatten och nyhetsläget kring stormhändelser på svenska västkusten.

Applikationen kombinerar:
- **Väderdata** från VIVA-stationer (vind, byvind, vattenstånd, temperatur)
- **Nyhetsflöden** från RSS-källor
- **Myndighetsvarningar** från SMHI, Krisinformation.se och VMA
- **Historik** i lokal SQLite-databas
- **Artikelhämtning** av fulltext (när det går)

## Vad kollegor behöver veta

- Projektet är byggt med **Python + Textual** (TUI i terminalen).
- Körning sker lokalt och lagrar data i mappen `data/`.
- Det finns **inga krav på API-nycklar** för de källor som nu är aktiverade.
- Fokus är robust drift: fel i en källa ska inte stoppa resten av appen.

## Arkitektur i korthet

- `main.py`: startpunkt
- `stormwatch/app.py`: huvudapp, schemaläggning, state, actions
- `stormwatch/fetchers/`: datainsamling per källa
  - `rss.py`
  - `smhi.py`
  - `viva.py`
  - `krisinformation.py`
  - `vma.py`
- `stormwatch/widgets/`: UI-paneler (nyheter, väder, artikel, historik)
- `stormwatch/classifier.py`: relevanspoäng 0–10
- `stormwatch/scraper.py`: hämtar artikeltext från webbsidor
- `stormwatch/history.py`: SQLite-lagring och enkel grafvisning
- `stormwatch/archiver.py`: arkiverar relevanta artiklar till JSONL

## Datakällor (nuvarande)

### Nyheter / alerts
- GP RSS
- Bohusläningen RSS
- Sveriges Radio RSS (valfri)
- P4 Väst RSS (valfri)
- SVT Väst RSS (regional)
- Aftonbladet RSS (valfri)
- Expressen RSS (valfri)
- Göteborgs Stad (Mynewsdesk RSS)
- Krisinformation.se API (`counties=14,13`)
- SR VMA API
- SMHI varnings-API (autodetektering av fungerande endpoint)

### Väder
- Sjöfartsverkets VIVA API för stationer i `config.toml`

## Konfiguration

All konfiguration ligger i `config.toml`.

Viktiga delar:
- `[app]`: refresh-intervall och max antal nyheter
- `[[stations]]`: VIVA-stationer
- `[[feeds]]`: RSS-källor
- `[smhi]`: aktivering + länsfilter
- `[krisinformation]`: aktivering + länsfilter
- `[vma]`: aktivering

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Starta appen

```bash
python main.py
```

## Tangenter i appen

- `↑/k` och `↓/j`: navigera i nyhetslistan
- `Enter`: hämta fulltext för vald artikel
- `r`: uppdatera nyheter
- `R`: uppdatera väder
- `f`: växla filter (hög relevans)
- `s`: växla sortering (score/tid)
- `o`: öppna vald artikel i webbläsare
- `h`: visa/dölj historikpanel
- `q` / `Ctrl+C`: avsluta

## Lagrad data

- `data/history.db`: väderhistorik (SQLite)
- `data/storm_dave_articles.jsonl`: arkiverade artiklar med högre relevans

## Begränsningar att känna till

- Vissa nyhetskällor kan ha betalvägg, då blir fulltext begränsad.
- Externa API:er och RSS-källor kan ändra format över tid.
- VMA- och Krisinformation-parsern är defensiv, men kan behöva justeras vid schemaändringar.

## Förslag för nästa steg

- Lägg till MET Norway Oceanforecast i väderpanelen (marin sektion).
- Lägg till Trafikverket när API-nyckel finns.
- Lägg till enklare enhetstester för parserfunktioner i fetchers.
