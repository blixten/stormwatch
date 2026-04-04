# StormWatch

StormWatch är ett terminalbaserat övervakningsverktyg för väder, vatten och nyhetsläget kring stormhändelser på svenska västkusten.

Applikationen kombinerar:
- **Väderdata** från VIVA-stationer (vind, byvind, vattenstånd, temperatur)
- **Nyhetsflöden** från RSS-källor
- **Myndighetsvarningar** från SMHI, Krisinformation.se och VMA
- **Historik** i lokal SQLite-databas
- **Artikelhämtning** av fulltext (när det går)
- Projektet är byggt med **Python + Textual** (TUI i terminalen).
- Körning sker lokalt och lagrar data i mappen `data/`.
- Fokus är robust drift: fel i en källa ska inte stoppa resten av appen.
- Datakällor (RSS, SMHI, Krisinformation, VIVA) kräver **inga API-nycklar**.
- Det **AI-baserade analysläget** kräver en API-nyckel till OpenAI (se nedan).

## Analyslägen

StormWatch har två lägen för att bedöma nyhetsartiklars relevans:

### 1. Nyckelordsbaserad analys (alltid aktiv)

Modulen `stormwatch/classifier.py` poängsätter varje artikel automatiskt med
ett **relevansscore 0–10** baserat på regelbaserad nyckelordsmatchning.
Poängen beräknas lokalt utan nätverksanrop och kräver ingen API-nyckel.
Rubriken väger dubbelt mot brödtexten. En artikel måste innehålla minst ett
storm- eller väderspecifikt kärnord för att få poäng alls (förhindrar falska
positiva från enbart ortnamn).

Poängfärger:
- `▲` röd – score ≥ 7 (hög relevans)
- `◆` gul – score 4–6 (medel relevans)
- `·` grå – score 0–3 (låg/ingen relevans)

### 2. AI-baserad analys med OpenAI GPT (valfri)

Modulen `stormwatch/ai_analyzer.py` skickar artikelns rubrik, sammanfattning
och eventuell fulltext till **OpenAI GPT-5-mini** och får tillbaka ett
relevansscore 0–10 samt en kort motivering på svenska. Detta läge aktiveras
automatiskt när miljövariabeln `OPENAI_API_KEY` är satt; annars används
enbart nyckelordsanalysen.

AI-analysen körs när du öppnar en artikels fulltext (tangent `Enter`) och
visas i artikelpanelen bredvid det nyckelordsbaserade scoret.

#### Aktivera AI-analys

Sätt din OpenAI-nyckel som miljövariabel innan du startar appen:

```bash
export OPENAI_API_KEY="sk-..."
python main.py
```

Eller för en enskild körning:

```bash
OPENAI_API_KEY="sk-..." python main.py
```

> **Obs:** Utan `OPENAI_API_KEY` fungerar appen fullt ut med enbart
> nyckelordsanalys. AI-läget är ett frivilligt tillägg.
>
> Paketet `openai` måste vara installerat (`pip install openai` eller
> inkluderat via `requirements.txt`) för att AI-läget ska kunna aktiveras.

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
- `stormwatch/classifier.py`: nyckelordsbaserad relevanspoäng 0–10
- `stormwatch/ai_analyzer.py`: AI-baserad relevansbedömning via OpenAI GPT
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
- SOS Alarm (Mynewsdesk RSS)
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

### Linux / Mac
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows
```bash
python -m venv .venv
source .venv/Scripts/activate
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
