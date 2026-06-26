#!/usr/bin/env python3
"""
TIOS statistics engine — runs in the GitHub Actions cron (no Claude). Reads the accumulated
data/prices.csv history and writes data/stats.json: per-ETF return / annualised volatility /
max drawdown / beta, plus the cross-ETF correlation matrix. GATED: a statistic is only emitted
once there are >= MIN_DAYS daily returns — otherwise it reports "accruing", never fabricated.
Robust to missing days (returns are aligned PAIRWISE by date, not by a global intersection).

Run:  python compute_stats.py
Self-test (no files needed):  python compute_stats.py --selftest
"""
import csv, json, os, sys, math, datetime
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES = os.path.join(HERE, "data", "prices.csv")
OUT = os.path.join(HERE, "data", "stats.json")
ETFS = ["VAS","VHY","IVV","VGS","ASIA","HEUR","EMKT","NDQ","GGUS","QAU","CRYP"]
BENCHMARKS = {"AXJO": "AXJO", "SPX": "SPX"}
MIN_DAYS = 25          # minimum daily returns before vol/beta/correlation are trusted
TRADING = 252

def load_prices(path=PRICES):
    px = defaultdict(dict)
    with open(path) as f:
        for row in csv.reader(f):
            if len(row) < 3 or row[0] == "series_code":
                continue
            try:
                px[row[0]][row[1]] = float(row[2])
            except ValueError:
                pass
    return px

def series(px, code):
    return sorted(px.get(code, {}).items())

def ret_by_date(s):
    """{date: daily_return} from consecutive sorted (date,value) pairs."""
    out = {}
    for i in range(1, len(s)):
        prev = s[i-1][1]
        if prev:
            out[s[i][0]] = s[i][1] / prev - 1
    return out

def stdev(xs):
    n = len(xs)
    if n < 2: return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))

def max_drawdown(vals):
    peak = vals[0]; mdd = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak: mdd = min(mdd, v / peak - 1)
    return mdd

def pct_over(vals, n):
    return vals[-1] / vals[-1-n] - 1 if len(vals) > n else None

def pair_align(ra, rb):
    """Two {date:ret} dicts -> aligned (list_a, list_b) on common dates."""
    ds = sorted(set(ra) & set(rb))
    return [ra[d] for d in ds], [rb[d] for d in ds]

def beta(ra, rb):
    a, b = pair_align(ra, rb)
    n = len(a)
    if n < 2: return None
    mb = sum(b)/n; ma = sum(a)/n
    varb = sum((x-mb)**2 for x in b)/(n-1)
    if not varb: return None
    cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n))/(n-1)
    return cov/varb

def corr(ra, rb):
    a, b = pair_align(ra, rb)
    n = len(a)
    if n < 2: return None
    sa, sb = stdev(a), stdev(b)
    if not sa or not sb: return None
    ma, mb = sum(a)/n, sum(b)/n
    cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n))/(n-1)
    return cov/(sa*sb)

def compute(px):
    rets = {c: ret_by_date(series(px, c)) for c in ETFS + list(BENCHMARKS.values())}
    stats = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "min_days": MIN_DAYS, "etfs": {}, "correlation": None,
    }
    max_n = 0
    for c in ETFS:
        s = series(px, c); vals = [v for _, v in s]
        r = list(rets[c].values()); n = len(r); max_n = max(max_n, n)
        rec = {"as_of": s[-1][0] if s else None, "last": s[-1][1] if s else None,
               "ret_1w": pct_over(vals, 5), "ret_1m": pct_over(vals, 21),
               "ret_all": (vals[-1]/vals[0]-1) if len(vals) > 1 else None, "n_days": n}
        if n >= MIN_DAYS:
            sd = stdev(r)
            rec["ann_vol"] = sd*math.sqrt(TRADING) if sd else None
            rec["max_drawdown"] = max_drawdown(vals)
            for bname, bcode in BENCHMARKS.items():
                rec[f"beta_{bname.lower()}"] = beta(rets[c], rets[bcode])
        stats["etfs"][c] = rec
    stats["n_days"] = max_n
    stats["ready"] = max_n >= MIN_DAYS
    if max_n >= MIN_DAYS:
        cm = {a: {b: (round(corr(rets[a], rets[b]), 2) if corr(rets[a], rets[b]) is not None else None)
                  for b in ETFS} for a in ETFS}
        stats["correlation"] = cm
    stats["note"] = ("Live as of the dates shown. Vol/beta/correlation gated until "
                     f"{MIN_DAYS}+ daily returns accrue (currently {max_n}). Price-return basis; "
                     "deterministic, computed in the GitHub cron — no LLM.")
    return stats

def write(stats, path=OUT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(stats, f, indent=1)

def selftest():
    import random; random.seed(1)
    px = defaultdict(dict)
    for c, base in {"VAS":100,"IVV":70,"AXJO":8000,"SPX":7000}.items():
        v = base
        for i in range(40):
            d = (datetime.date(2026,6,1)+datetime.timedelta(days=i)).isoformat()
            v *= (1 + random.uniform(-0.01, 0.011)); px[c][d] = round(v, 3)
    s = compute(px)
    assert s["ready"], "should be ready with 40 days"
    assert s["etfs"]["VAS"]["ann_vol"] is not None, "vol should compute"
    assert s["correlation"]["VAS"]["IVV"] is not None, "VAS-IVV corr should compute"
    print("selftest OK — ready:", s["ready"], "n_days:", s["n_days"],
          "| VAS vol:", round(s["etfs"]["VAS"]["ann_vol"]*100,1), "%",
          "| VAS beta_spx:", round(s["etfs"]["VAS"]["beta_spx"],2),
          "| VAS-IVV corr:", s["correlation"]["VAS"]["IVV"])

def main():
    if "--selftest" in sys.argv:
        return selftest()
    px = load_prices()
    stats = compute(px)
    write(stats)
    print(f"Wrote {OUT}: ready={stats['ready']} n_days={stats['n_days']}")

if __name__ == "__main__":
    main()
