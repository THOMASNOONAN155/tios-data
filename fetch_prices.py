#!/usr/bin/env python3
"""
TIOS daily price fetch — designed to run on a GitHub Actions runner (open internet).
Pulls EOD closes for the portfolio + indices + FX + commodities and APPENDS them to
data/prices.csv. Append-only and immutable by design (matches the TIOS ledger philosophy):
the downstream clean-view builder dedups by latest fetched_at, so re-runs just add rows.

Schema (matches observations_clean.csv so the main repo can merge it directly):
    series_code,date,value,source_url,fetched_at,flag
    flag = clean (fetched OK) | failed (no value — never invented)

Primary source: yfinance. Fallback: stooq CSV. Never writes a value it didn't get.
Run normally:   python fetch_prices.py
Self-test (no network, validates file I/O only):  python fetch_prices.py --selftest
"""
import csv, io, os, sys, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "prices.csv")
HEADER = ["series_code", "date", "value", "source_url", "fetched_at", "flag"]

# series_code -> (yfinance symbol, stooq symbol or None)
SERIES = {
    "VAS":  ("VAS.AX",  "vas.au"),
    "VHY":  ("VHY.AX",  "vhy.au"),
    "IVV":  ("IVV.AX",  "ivv.au"),
    "VGS":  ("VGS.AX",  "vgs.au"),
    "ASIA": ("ASIA.AX", "asia.au"),
    "HEUR": ("HEUR.AX", "heur.au"),
    "EMKT": ("EMKT.AX", "emkt.au"),
    "NDQ":  ("NDQ.AX",  "ndq.au"),
    "GGUS": ("GGUS.AX", "ggus.au"),
    "QAU":  ("QAU.AX",  "qau.au"),
    "CRYP": ("CRYP.AX", "cryp.au"),
    # benchmarks / read-acrosses
    "AXJO": ("^AXJO",   "^axjo"),
    "SPX":  ("^GSPC",   "^spx"),
    "IXIC": ("^IXIC",   None),
    # FX / rates / vol / commodities
    "AUDUSD": ("AUDUSD=X", "audusd"),
    "DXY":    ("DX-Y.NYB", None),
    "US10Y":  ("^TNX",     None),
    "VIX":    ("^VIX",     None),
    "GOLD":   ("GC=F",     None),
    "WTI":    ("CL=F",     None),
    "BRENT":  ("BZ=F",     None),
}

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def normalise(code, value):
    """Fix known quoting quirks so the number means what the dashboard expects."""
    if value is None:
        return None
    # Yahoo's ^TNX has historically been quoted x10 (e.g. 44.5 == 4.45%). Guard it.
    if code == "US10Y" and value > 20:
        value = value / 10.0
    return round(value, 4)

def fetch_yf(symbol):
    import yfinance as yf
    df = yf.Ticker(symbol).history(period="7d", auto_adjust=False)
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None
    last = df.iloc[-1]
    return df.index[-1].date().isoformat(), float(last["Close"]), \
        "https://finance.yahoo.com/quote/" + symbol

def fetch_stooq(symbol):
    url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
    raw = urllib.request.urlopen(url, timeout=25).read().decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        return None
    r = rows[0]
    close, date = r.get("Close"), r.get("Date")
    if close in (None, "", "N/D") or date in (None, "", "N/D"):
        return None
    return date, float(close), url

def fetch_one(code, yf_sym, stooq_sym):
    for fn, sym in ((fetch_yf, yf_sym), (fetch_stooq, stooq_sym)):
        if not sym:
            continue
        try:
            res = fn(sym)
            if res:
                date, value, src = res
                v = normalise(code, value)
                if v is not None:
                    return [code, date, v, src, now_iso(), "clean"]
        except Exception as e:
            sys.stderr.write(f"  {code} via {sym}: {e}\n")
    return [code, datetime.date.today().isoformat(), "", "", now_iso(), "failed"]

def ensure_header():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not os.path.exists(OUT) or os.path.getsize(OUT) == 0:
        with open(OUT, "w", newline="") as f:
            csv.writer(f).writerow(HEADER)

def append_rows(rows):
    ensure_header()
    with open(OUT, "a", newline="") as f:
        csv.writer(f).writerows(rows)

def selftest():
    """No network — validates the file is writable and the schema round-trips."""
    ensure_header()
    test = [["TEST", datetime.date.today().isoformat(), 1.23,
             "selftest", now_iso(), "clean"]]
    append_rows(test)
    with open(OUT) as f:
        last = list(csv.reader(f))[-1]
    assert last[0] == "TEST" and last[5] == "clean", "schema round-trip failed"
    print("selftest OK — wrote and read back:", last)
    print("Header:", HEADER)

def main():
    if "--selftest" in sys.argv:
        return selftest()
    rows, ok, fail = [], 0, 0
    for code, (yf_sym, stooq_sym) in SERIES.items():
        row = fetch_one(code, yf_sym, stooq_sym)
        rows.append(row)
        if row[5] == "clean":
            ok += 1
            print(f"  OK   {code:6} {row[1]}  {row[2]}")
        else:
            fail += 1
            print(f"  FAIL {code:6} (no value)")
    append_rows(rows)
    print(f"\nAppended {len(rows)} rows to {OUT}  ({ok} clean / {fail} failed)")
    if fail == len(rows):
        sys.exit(1)  # total failure -> fail the Action so you get notified

if __name__ == "__main__":
    main()
