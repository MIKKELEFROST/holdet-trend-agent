#!/usr/bin/env python3
"""
Holdet trend-agent — spotter spillere der er ved at blive populære, FØR prisen stiger.

Idé: Holdet hæver en spillers pris EFTER hver runde, bl.a. ud fra nettokøb. Mellem runderne
er prisen ~frossen, men efterspørgslen (popularitet + handelstendens) bygger sig op. Måler vi
ofte, kan vi se efterspørgslen accelerere FØR den næste prisjustering — og købe der.

Hver kørsel:
  1) henter live data (pris, popularitet, handelstendens) fra game-616 API'et,
  2) gemmer et snapshot i history.jsonl (tidsserie der bygges op over tid),
  3) beregner Δpopularitet over ~6 og ~24 timer ud fra historikken,
  4) scorer KØB-kandidater og skriver reports/latest.md,
  5) selv-validerer: når en VM-runde er afgjort, tjekker den om forrige rundes forudsigelser steg.

Lokalt test uden netværk:
  AGENT_OFFLINE_DIR=/tmp/holdet python3 agent.py      (players.json, standings.json, round1.json …)
"""
import csv, json, os, re, sys, time, unicodedata, urllib.error, urllib.request
from datetime import datetime, timezone

GAME = 616
API = "https://nexus-app-fantasy.holdet.dk/api/games/%d" % GAME
HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "history.jsonl")
PRED = os.path.join(HERE, "predictions.jsonl")
STATIC_CSV = os.path.join(HERE, "players_static.csv")
REPORTS = os.path.join(HERE, "reports")
OFFLINE = os.environ.get("AGENT_OFFLINE_DIR")

# ---- tunables ----
MAX_ROUNDS   = 12
HISTORY_KEEP = 480           # behold seneste N snapshots (~20 dage ved timedrift)
PRUNE_MARGIN = 48            # prune først når vi er så meget over (sjældnere, atomisk rewrite)
TOP_N        = 25
PRED_TRACK   = 15
SNAP_TOL     = 0.4           # et "24t-snapshot" må højst være 40% fra 24t (ellers None)
W = dict(trend=0.30, dpop24=0.30, dpop6=0.15, fix=0.10, lag=0.15, pop_pen=0.20)


# ---------- helpers ----------
def norm(s):
    s = s or ""
    s = re.sub(r'["“”‘’\'].*?["“”‘’\']', " ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_iso(s):
    return datetime.fromisoformat(s)


def _ts(h):
    return parse_iso(h["ts"]).timestamp()


def _http(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "holdet-trend-agent"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last if last else RuntimeError("fetch failed")


def get_json(name):
    if OFFLINE:
        path = os.path.join(OFFLINE, name + ".json")
        return json.load(open(path)) if os.path.exists(path) else None
    if name == "players":
        url = API + "/players"
    elif name == "standings":
        url = API + "/standings"
    elif name.startswith("round"):
        url = API + "/rounds/" + name[5:] + "/players"
    else:
        return None
    return _http(url)


def latest_round():
    """Højeste runde-nummer der faktisk har spillerdata; robust mod enkelte huller/fejl."""
    best = None
    for n in range(1, MAX_ROUNDS + 1):
        try:
            d = get_json("round%d" % n)
        except Exception:
            d = None  # transient fejl: spring over, fortsæt med at probe
        if isinstance(d, dict) and d.get("items"):
            best = (n, d)
    return best


def fmt_eur(v):
    return "€" + "{:,.0f}".format(v).replace(",", ".") if isinstance(v, (int, float)) else "–"


def signed(v):
    if not isinstance(v, (int, float)):
        return "–"
    s = "+" if v > 0 else ("−" if v < 0 else "")
    return s + "{:,.0f}".format(abs(round(v))).replace(",", ".")


def kfmt(v):
    if not isinstance(v, (int, float)):
        return "–"
    s = "+" if v > 0 else ("−" if v < 0 else "")
    return s + "{:,.0f}".format(round(abs(v) / 1000)).replace(",", ".") + "k"


# ---------- static data (kampprogram, seedning, markedsværdi) ----------
def load_static():
    st, rang_by_land, rows = {}, {}, []
    date_re = re.compile(r"\s+\d{1,2}/\d{1,2}$")
    with open(STATIC_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            rows.append(r)
    for r in rows:
        if r.get("Land") and r.get("Rang"):
            try:
                rang_by_land[r["Land"]] = int(r["Rang"])
            except ValueError:
                pass

    def ease(rg):  # rang 1 (stærkeste modstander)=0 … rang 48 (svageste)=1
        return 0.5 if rg is None else min(1.0, max(0.0, (rg - 1) / 47.0))

    for r in rows:
        fixtures = []
        for k in ("Runde 1", "Runde 2", "Runde 3"):
            v = (r.get(k) or "").strip()
            if v:
                opp = date_re.sub("", v)
                fixtures.append({"opp": opp, "date": v[len(opp):].strip()})
        eases = [ease(rang_by_land.get(fx["opp"])) for fx in fixtures]
        mv = None
        try:
            mv = int(r["Markedsværdi (EUR)"]) if r.get("Markedsværdi (EUR)") else None
        except ValueError:
            pass
        st[norm(r["Navn"])] = {
            "land": r.get("Land"), "mv": mv,
            "fixEase": sum(eases) / len(eases) if eases else 0.5,
            "nextOpp": fixtures[0]["opp"] if fixtures else None,
        }
    return st


# ---------- snapshot ----------
def build_snapshot():
    try:
        players = get_json("players")
    except Exception as e:
        print(f"FEJL: kunne ikke hente players ({e})", file=sys.stderr)
        return None, None
    if not isinstance(players, dict) or not isinstance(players.get("items"), list) or not players["items"]:
        print("FEJL: uventet players-payload", file=sys.stderr)
        return None, None
    emb = players.get("_embedded") or {}
    persons = emb.get("persons") or {}
    positions = emb.get("positions") or {}

    lr = latest_round()
    trend, pchg, rnd = {}, {}, None
    if lr:
        rnd, rd = lr
        for it in rd.get("items", []):
            pid = str(it.get("personId"))
            trend[pid] = it.get("trend")
            pchg[pid] = it.get("priceChange")

    snap = {}
    for it in players["items"]:
        pid = str(it.get("personId"))
        p = persons.get(pid, {})
        name = ((p.get("firstName") or "") + " " + (p.get("lastName") or "")).strip()
        snap[pid] = {
            "name": name,
            "pos": (positions.get(str(it.get("positionId")), {}) or {}).get("title"),
            "price": it.get("price"),
            "pop": it.get("popularity"),
            "out": bool(it.get("isOut")),
            "trend": trend.get(pid),
            "pchg": pchg.get(pid),
        }
    return snap, rnd


def append_history(snap, rnd, ts):
    line = {"ts": ts, "round": rnd,
            "p": {pid: [v["price"], round((v["pop"] or 0) * 1e6), v["trend"]] for pid, v in snap.items()}}
    with open(HIST, "a") as f:
        f.write(json.dumps(line, separators=(",", ":")) + "\n")
    lines = [l for l in open(HIST).read().splitlines() if l.strip()]
    if len(lines) > HISTORY_KEEP + PRUNE_MARGIN:        # sjælden, atomisk prune
        tmp = HIST + ".tmp"
        with open(tmp, "w") as f:
            f.write("\n".join(lines[-HISTORY_KEEP:]) + "\n")
        os.replace(tmp, HIST)                            # atomisk rename


def load_history():
    if not os.path.exists(HIST):
        return []
    out = []
    for ln in open(HIST):
        ln = ln.strip()
        if not ln:
            continue
        try:
            h = json.loads(ln)
            parse_iso(h["ts"])                           # validér timestamp
            if isinstance(h.get("p"), dict):
                out.append(h)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass                                         # spring beskadiget linje over
    out.sort(key=lambda h: h["ts"])
    return out


def snap_at(history, hours_ago, now_dt, tol=SNAP_TOL):
    if not history:
        return None
    target = now_dt.timestamp() - hours_ago * 3600
    best = min(history, key=lambda h: abs(_ts(h) - target))
    age = (now_dt.timestamp() - _ts(best)) / 3600
    if abs(age - hours_ago) > hours_ago * tol:           # for langt fra det ønskede vindue
        return None
    return best


# ---------- scoring ----------
def score(snap, hist, static, ts):
    now = parse_iso(ts)
    past24 = snap_at(hist, 24, now)
    past6 = snap_at(hist, 6, now)

    def pv(ps, pid, idx):
        if not ps:
            return None
        rec = ps["p"].get(pid)
        return rec[idx] if rec else None

    rows = []
    for pid, v in snap.items():
        if v["out"] or v["price"] is None:
            continue
        pop, price, trend = v["pop"] or 0, v["price"], v["trend"] or 0
        dpop24 = dpop6 = dprice24 = None
        if past24:
            pp = pv(past24, pid, 1)
            if pp is not None:
                dpop24 = pop - pp / 1e6
            pr = pv(past24, pid, 0)
            if pr is not None and price is not None:
                dprice24 = price - pr
        if past6:
            pp = pv(past6, pid, 1)
            if pp is not None:
                dpop6 = pop - pp / 1e6
        s = static.get(norm(v["name"]), {})
        rows.append({"pid": pid, "name": v["name"], "pos": v["pos"], "land": s.get("land"),
                     "price": price, "pop": pop, "trend": trend, "pchg": v["pchg"],
                     "dpop24": dpop24, "dpop6": dpop6, "dprice24": dprice24,
                     "fixEase": s.get("fixEase", 0.5), "nextOpp": s.get("nextOpp"), "mv": s.get("mv")})

    def maxpos(transform):
        vals = [transform(r) for r in rows]
        vals = [x for x in vals if isinstance(x, (int, float)) and x > 0]
        return max(vals) if vals else 1.0

    numok = lambda x: x if isinstance(x, (int, float)) else 0
    mt = maxpos(lambda r: numok(r["trend"]))
    md24 = maxpos(lambda r: numok(r["dpop24"]))
    md6 = maxpos(lambda r: numok(r["dpop6"]))
    # prisstigning som andel af pris (pris justeres pr. runde; mellem runder ~0)
    mpr = maxpos(lambda r: (r["dprice24"] / r["price"]) if (isinstance(r["dprice24"], (int, float)) and r["price"]) else 0)
    mpop = max([r["pop"] for r in rows] or [1.0]) or 1.0

    for r in rows:
        s_tr = r["trend"] / mt
        s_dp = (max(0, r["dpop24"]) / md24) if isinstance(r["dpop24"], (int, float)) else 0
        s_dp6 = (max(0, r["dpop6"]) / md6) if isinstance(r["dpop6"], (int, float)) else 0
        s_fix = r["fixEase"]
        # headroom: popularitet er steget, men prisen er IKKE fulgt med endnu.
        # Kun reelt når vi både har Δpop og Δpris (ellers 0 — ingen ufortjent headroom ved koldstart).
        if isinstance(r["dpop24"], (int, float)) and isinstance(r["dprice24"], (int, float)) and r["price"]:
            s_pr = max(0, r["dprice24"] / r["price"]) / mpr
            s_lag = max(0.0, s_dp - s_pr)
        else:
            s_lag = 0.0
        pen = r["pop"] / mpop
        r["sig"] = {"trend": s_tr, "dpop24": s_dp, "dpop6": s_dp6, "fix": s_fix, "lag": s_lag, "pop_pen": pen}
        r["score"] = 100 * (W["trend"] * s_tr + W["dpop24"] * s_dp + W["dpop6"] * s_dp6
                            + W["fix"] * s_fix + W["lag"] * s_lag - W["pop_pen"] * pen)
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows, {"span": round((now.timestamp() - _ts(hist[0])) / 3600, 1) if hist else 0,
                  "have24": bool(past24), "have6": bool(past6)}


def why(r):
    g, t = r["sig"], []
    if g["trend"] >= 0.45: t.append("høj efterspørgsel")
    if g["dpop24"] >= 0.4: t.append("popularitet stiger")
    if g["dpop6"] >= 0.5: t.append("accelererer")
    if g["lag"] >= 0.1: t.append("pris ikke fulgt med")
    if g["fix"] >= 0.66: t.append("let program")
    if r["pop"] < 0.05: t.append("under radaren")
    return ", ".join(t) or "—"


# ---------- selv-validering (rundebaseret: priser justeres pr. runde) ----------
def validate(snap, rnd_now):
    cur = {pid: v["price"] for pid, v in snap.items()}
    rose = tot = 0
    chgs = []
    if rnd_now is not None and os.path.exists(PRED):
        for ln in open(PRED):
            ln = ln.strip()
            if not ln:
                continue
            try:
                pr = json.loads(ln)
                pr_round = pr.get("round")
                items = pr["items"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            if pr_round is None or pr_round != rnd_now - 1:   # vurdér forrige rundes forudsigelser
                continue
            for it in items:
                cp = cur.get(it.get("pid"))
                if cp is not None and it.get("price"):
                    tot += 1
                    d = cp - it["price"]
                    chgs.append(d)
                    if d > 0:
                        rose += 1
    return {"n": tot, "rose": rose,
            "hit": (rose / tot) if tot else None,
            "avg": (sum(chgs) / len(chgs)) if chgs else None}


def append_prediction(rows, ts, rnd):
    items = [{"pid": r["pid"], "name": r["name"], "price": r["price"]} for r in rows[:PRED_TRACK]]
    with open(PRED, "a") as f:
        f.write(json.dumps({"ts": ts, "round": rnd, "items": items}, ensure_ascii=False, separators=(",", ":")) + "\n")


# ---------- rapport ----------
def write_report(rows, meta, val, ts, rnd):
    os.makedirs(REPORTS, exist_ok=True)
    dt = parse_iso(ts)
    L = []
    L.append("# Trend-agent — køb-kandidater")
    L.append("")
    L.append(f"**Kørt:** {dt.strftime('%Y-%m-%d %H:%M UTC')}  ·  **Seneste spillede runde:** {rnd if rnd else '–'}  ·  "
             f"**Historik-span:** {meta['span']} t")
    L.append("")
    if not meta["have24"]:
        L.append("> ⏳ **Opvarmer:** acceleration-signaler (Δ over 6/24 t) kræver et par dages historik. "
                 "Indtil da rangeres efter efterspørgsel (tendens), kampprogram og lav popularitet.")
        L.append("")
    if val["n"]:
        hp = f"{val['hit']*100:.0f}%" if val["hit"] is not None else "–"
        L.append(f"**Selv-validering** (forrige rundes forudsigelser, målt efter runden blev afgjort): "
                 f"{val['rose']}/{val['n']} steg = **{hp}** · gns. ændring {signed(val['avg'])} €")
        L.append("")
    else:
        L.append("_Selv-validering afventer at næste VM-runde afgøres (priser justeres pr. runde)._")
        L.append("")
    L.append("## Top køb-kandidater")
    L.append("")
    L.append("| # | Spiller | Pos | Land | Pris | Tendens | Δpop 24t | Δpris 24t | Næste | Score | Hvorfor |")
    L.append("|---|---------|-----|------|------|---------|----------|-----------|-------|-------|---------|")
    for i, r in enumerate(rows[:TOP_N], 1):
        dpop = f"{r['dpop24']*100:+.2f} pp" if isinstance(r["dpop24"], (int, float)) else "–"
        L.append(f"| {i} | **{r['name']}** | {r['pos'] or '–'} | {r['land'] or '–'} | "
                 f"{fmt_eur(r['price'])} | {'{:,.0f}'.format(r['trend']).replace(',','.')} | {dpop} | "
                 f"{kfmt(r['dprice24'])} | {r['nextOpp'] or '–'} | **{r['score']:.0f}** | {why(r)} |")
    L.append("")
    early = [r for r in rows if r["sig"]["dpop6"] >= 0.5 and r["sig"]["lag"] >= 0.2][:8]
    if early:
        L.append("## 🚀 Tidlige bevægelser (popularitet stiger hurtigt, pris ikke fulgt med)")
        L.append("")
        for r in early:
            L.append(f"- **{r['name']}** ({r['pos']}, {r['land']}) — tendens "
                     f"{'{:,.0f}'.format(r['trend']).replace(',','.')}, Δpop6 {r['dpop6']*100:+.2f} pp, "
                     f"pris {fmt_eur(r['price'])}")
        L.append("")
    diff = [r for r in rows if r["pop"] < 0.05 and r["sig"]["trend"] >= 0.3][:8]
    if diff:
        L.append("## 💎 Under radaren (efterspurgt, men få har ham)")
        L.append("")
        for r in diff:
            L.append(f"- **{r['name']}** ({r['pos']}, {r['land']}) — pop {r['pop']*100:.1f}%, "
                     f"tendens {'{:,.0f}'.format(r['trend']).replace(',','.')}, {fmt_eur(r['price'])}")
        L.append("")
    L.append("---")
    L.append("")
    L.append("### Sådan scorer agenten")
    L.append("Score = vægtet sum af **tendens** (køb lige nu, leading), **Δpopularitet** 24 t og 6 t "
             "(popularitet på vej op), **headroom** (popularitet steget, men pris ikke fulgt med), og "
             "**let kampprogram** — minus straf for allerede høj popularitet. Vægte i `agent.py` (`W`). "
             "Priser justeres pr. runde, så selv-valideringen måles rundevis. Kun spilbare spillere medtages.")
    L.append("")
    L.append("> Forudsigelser er sandsynlige, ikke sikre. Agenten måler efterspørgsels-momentum, "
             "ikke kampbegivenheder (mål/assist findes ikke i API'et).")
    body = "\n".join(L) + "\n"
    tmp = os.path.join(REPORTS, "latest.md.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, os.path.join(REPORTS, "latest.md"))
    with open(os.path.join(REPORTS, dt.strftime("%Y%m%dT%H%M") + "Z.md"), "w", encoding="utf-8") as f:
        f.write(body)


def main():
    try:
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        static = load_static()
        snap, rnd = build_snapshot()
        if snap is None or len(snap) < 500:
            print(f"AFBRUDT: utilstrækkelig data (snap={None if snap is None else len(snap)})", file=sys.stderr)
            return 1
        hist = load_history()                 # FØR vi tilføjer dagens snapshot (ingen lookahead)
        rows, meta = score(snap, hist, static, ts)
        val = validate(snap, rnd)             # nuværende priser vs. forrige rundes forudsigelser
        append_history(snap, rnd, ts)
        append_prediction(rows, ts, rnd)
        write_report(rows, meta, val, ts, rnd)
        print(f"OK · {len(snap)} spillere · runde {rnd} · span {meta['span']}t · "
              f"top: {rows[0]['name']} ({rows[0]['score']:.0f}) · validering n={val['n']}")
        return 0
    except Exception as e:
        import traceback
        print("UVENTET FEJL:", e, file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
