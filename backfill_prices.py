#!/usr/bin/env python3
"""
TIOS one-off backfill — runs on a GitHub Actions runner (open internet). Pulls ~5y of daily
history for the 11 ETFs + the two stat benchmarks (AXJO, SPX) and APPENDS the missing dates to
data/prices.csv (same schema as fetch_prices.py). Skips (code,date) pairs already present, so it is
safe to re-run. Unadjusted Close (auto_adjust=False) to stay consistent with the daily feed —
"price-return basis" (ETF distribution ex-dates show as small one-day dips; negligible over 5y).

After this runs, compute_stats.py has >25 daily returns and emits real vol / beta /
correlation / max-drawdown instead of "accruing".

Deploy: trigger the 'TIOS backfill (one-off)' workflow from the Actions tab (workflow_dispatch).
"""
import csv, os, sys, datetime
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "prices.csv")
HEADER = ["series_code", "date", "value", "source_url", "fetched_at", "flag"]

# series_code -> yfinance symbol (the 11 ETFs + the two stat benchmarks compute_stats needs)
SERIES = {
    "VAS": "VAS.AX", "VHY": "VHY.AX", "IVV": "IVV.AX", "VGS": "VGS.AX", "ASIA": "ASIA.AX",
    "HEUR": "HEUR.AX", "EMKT": "EMKT.AX", "NDQ": "NDQ.AX", "GGUS": "GGUS.AX", "QAU": "QAU.AX",
    "CRYP": "CRYP.AX", "AXJO": "^AXJO", "SPX": "^GSPC",
}
PERIOD = "5y"

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def existing_pairs(path):
    seen = set()
    if os.path.exists(path):
        with open(path) as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0] != "series_code":
                    seen.add((row[0], row[1]))
    return seen

def ensure_header(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(HEADER)

def main():
    ensure_header(OUT)
    seen = existing_pairs(OUT)               # don't duplicate the live tail or earlier backfills
    rows, total, src_t = [], 0, now_iso()
    for code, sym in SERIES.items():
        try:
            df = yf.Ticker(sym).history(period=PERIOD, auto_adjust=False).dropna(subset=["Close"])
        except Exception as e:
            sys.stderr.write(f"  {code} {sym}: {e}\n"); continue
        n = 0
        for idx, r in df.iterrows():
            d = idx.date().isoformat()
            if (code, d) in seen:
                continue
            rows.append([code, d, round(float(r["Close"]), 4),
                         "https://finance.yahoo.com/quote/" + sym, src_t, "backfill"])
            n += 1
        total += n
        print(f"  {code:6} {sym:8} +{n} rows")
    with open(OUT, "a", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"\nAppended {total} backfill rows to {OUT}")
    if total == 0:
        print("Nothing new to append (already backfilled?).")

if __name__ == "__main__":
    main()
