# Trend-agent — køb-kandidater

**Kørt:** 2026-06-18 00:00 UTC  ·  **Seneste spillede runde:** 1  ·  **Historik-span:** 0 t

> ⏳ **Opvarmer:** acceleration-signaler (Δ over 6/24 t) kræver et par dages historik. Indtil da rangeres efter efterspørgsel (tendens), kampprogram og lav popularitet.

_Selv-validering afventer at næste VM-runde afgøres (priser justeres pr. runde)._

## Top køb-kandidater

| # | Spiller | Pos | Land | Pris | Tendens | Δpop 24t | Δpris 24t | Næste | Score | Hvorfor |
|---|---------|-----|------|------|---------|----------|-----------|-------|-------|---------|
| 1 | **Kai Havertz** | Angreb | Tyskland | €5.877.000 | 46.691 | – | – | Curaçao | **15** | høj efterspørgsel |
| 2 | **Nathaniel Brown** | Forsvar | Tyskland | €2.809.000 | 41.563 | – | – | Curaçao | **14** | høj efterspørgsel |
| 3 | **Mikel Oyarzabal** | Angreb | Spanien | €7.522.000 | 29.476 | – | – | Kap Verde | **13** | høj efterspørgsel, let program |
| 4 | **Bruno Fernandes** | Midtbane | Portugal | €7.014.000 | 25.603 | – | – | Congo DR | **12** | høj efterspørgsel |
| 5 | **Gregor Kobel** | Keeper | Schweiz | €4.029.000 | 19.163 | – | – | Qatar | **11** | let program |
| 6 | **Dani Olmo** | Midtbane | Spanien | €5.012.000 | 20.330 | – | – | Kap Verde | **11** | let program |
| 7 | **Erling Haaland** | Angreb | Norge | €8.907.000 | 30.676 | – | – | Irak | **11** | høj efterspørgsel |
| 8 | **Nathan Ngoy** | Forsvar | Belgien | €2.014.000 | 9.898 | – | – | Egypten | **11** | let program |
| 9 | **Thibaut Courtois** | Keeper | Belgien | €4.529.000 | 9.529 | – | – | Egypten | **10** | let program |
| 10 | **Nuno Mendes** | Forsvar | Portugal | €4.514.000 | 20.058 | – | – | Congo DR | **10** | — |
| 11 | **Youri Tielemans** | Midtbane | Belgien | €3.514.000 | 8.224 | – | – | Egypten | **10** | let program |
| 12 | **Michael Olise** | Angreb | Frankrig | €7.167.000 | 26.735 | – | – | Senegal | **10** | høj efterspørgsel |
| 13 | **Antonio Nusa** | Midtbane | Norge | €3.544.000 | 27.979 | – | – | Irak | **10** | høj efterspørgsel |
| 14 | **Florian Wirtz** | Midtbane | Tyskland | €7.654.000 | 20.958 | – | – | Curaçao | **10** | — |
| 15 | **Antonee Robinson** | Forsvar | USA | €2.064.000 | 19.358 | – | – | Paraguay | **10** | — |
| 16 | **Julian Alvarez** | Angreb | Argentina | €6.052.000 | 14.881 | – | – | Algeriet | **10** | — |
| 17 | **Brian Gutierrez** | Midtbane | Mexico | €2.522.000 | 12.326 | – | – | Sydafrika | **10** | let program |
| 18 | **Jules Kounde** | Forsvar | Frankrig | €3.554.000 | 23.821 | – | – | Senegal | **10** | høj efterspørgsel |
| 19 | **Ousmane Dembele** | Angreb | Frankrig | €5.542.000 | 24.223 | – | – | Senegal | **10** | høj efterspørgsel |
| 20 | **Fabian Ruiz** | Midtbane | Spanien | €4.522.000 | 13.239 | – | – | Kap Verde | **10** | let program |
| 21 | **Jamal Musiala** | Midtbane | Tyskland | €6.714.000 | 19.722 | – | – | Curaçao | **9** | — |
| 22 | **Lamine Yamal** | Angreb | Spanien | €9.012.000 | 13.574 | – | – | Kap Verde | **9** | let program |
| 23 | **Marc Cucurella** | Forsvar | Spanien | €4.572.000 | 12.254 | – | – | Kap Verde | **9** | let program |
| 24 | **Pedri** | Midtbane | Spanien | €6.002.000 | 12.788 | – | – | Kap Verde | **9** | let program |
| 25 | **Ferran Torres** | Angreb | Spanien | €5.022.000 | 11.451 | – | – | Kap Verde | **9** | let program |

---

### Sådan scorer agenten
Score = vægtet sum af **tendens** (køb lige nu, leading), **Δpopularitet** 24 t og 6 t (popularitet på vej op), **headroom** (popularitet steget, men pris ikke fulgt med), og **let kampprogram** — minus straf for allerede høj popularitet. Vægte i `agent.py` (`W`). Priser justeres pr. runde, så selv-valideringen måles rundevis. Kun spilbare spillere medtages.

> Forudsigelser er sandsynlige, ikke sikre. Agenten måler efterspørgsels-momentum, ikke kampbegivenheder (mål/assist findes ikke i API'et).
