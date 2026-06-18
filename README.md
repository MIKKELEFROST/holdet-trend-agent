# Holdet trend-agent (privat)

Spotter spillere der er ved at blive **populære/efterspurgte**, så man kan købe dem **før** prisen stiger.

Holdet hæver en spillers pris efter hver runde bl.a. ud fra nettokøb. Måler man ofte, kan man se
**efterspørgslen accelerere** (popularitet + handelstendens stiger) *før* prisen har indhentet det — og købe der.

## Hvordan den virker

[`agent.py`](agent.py) kører hver time (GitHub Action) og:
1. henter live data (pris, popularitet, `trend`=handelstendens) fra game-616 API'et,
2. gemmer et snapshot i [`history.jsonl`](history.jsonl) — tidsserien der bygges op over tid,
3. beregner Δpopularitet / Δpris over 6 og 24 timer ud fra historikken,
4. **scorer køb-kandidater** og skriver en rapport,
5. **selv-validerer**: tjekker om tidligere forudsigelser faktisk steg → hit-rate i rapporten.

👉 **Læs seneste rapport:** [`reports/latest.md`](reports/latest.md) (opdateres hver time).

## Score

```
score = 0.30·tendens        (hvor meget spilleren købes lige nu — leading)
      + 0.30·Δpop 24t        (popularitet på vej op)
      + 0.15·Δpop 6t         (accelererer netop nu)
      + 0.15·headroom        (efterspørgsel > realiseret prisstigning = pris ikke fulgt med)
      + 0.10·let kampprogram (svag modstander → sandsynlig præstation)
      − 0.20·popularitet     (straf: "alle har ham allerede" = mindre upside)
```

Vægtene står i `W` øverst i `agent.py` og kan justeres. Kun spilbare spillere medtages.

## Vigtigt / forbehold

- **Opvarmning:** acceleration-signalerne (Δ) kræver et par dages historik. De første kørsler rangerer
  efter efterspørgsel (tendens), kampprogram og lav popularitet.
- Forudsigelser er **sandsynlige, ikke sikre**. Holdets prismodel blander præstation og købs/salgspres;
  agenten måler efterspørgsels-momentum, ikke kampbegivenheder (mål/assist findes ikke i API'et).
- `predictions.jsonl` + selv-valideringen viser agentens reelle træfsikkerhed over tid.

## Kør lokalt

```bash
python3 agent.py                       # kræver netværk
# eller offline med cachet data:
AGENT_OFFLINE_DIR=/tmp/holdet python3 agent.py   # players.json, standings.json, round1.json …
```

`players_static.csv` leverer kampprogram, seedning og markedsværdi (de findes ikke i API'et).
