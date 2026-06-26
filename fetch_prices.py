#!/usr/bin/env python3
"""
TIOS daily fetch — runs on a GitHub Actions runner (open internet). Pulls EOD market data and
APPENDS to data/prices.csv (append-only; schema matches observations_clean.csv). Never invents a
value it didn't get; failures are flagged 'failed'.

Sources: yfinance (prices/indices/FX/commodities), stooq (fallback), FRED (keyless CSV) for the
macro the price feeds lack — US rates, the 2s10s curve, the high-yield credit spread, iron ore.

Run:  python fetch_prices.py            # real fetch (needs internet; runs on the Action)
      python fetch_prices.py --selftest # validates the CSV write path only (no network)
"""
import csv, io, os, sys, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "prices.csv")
HEADER = ["series_code", "date", "value", "source_url", "fetched_at", "flag"]

# series_code -> (yfinance symbol, stooq symbol or None)
SERIES = {
    "VAS": ("VAS.AX","vas.au"), "VHY": ("VHY.AX","vhy.au"), "IVV": ("IVV.AX","ivv.au"),
    "VGS": ("VGS.AX","vgs.au"), "ASIA": ("ASIA.AX","asia.au"), "HEUR": ("HEUR.AX","heur.au"),
    "EMKT": ("EMKT.AX","emkt.au"), "NDQ": ("NDQ.AX","ndq.au"), "GGUS": ("GGUS.AX","ggus.au"),
    "QAU": ("QAU.AX","qau.au"), "CRYP": ("CRYP.AX","cryp.au"),
    "AXJO": ("^AXJO","^axjo"), "SPX": ("^GSPC","^spx"), "IXIC": ("^IXIC",None),
    "AUDUSD": ("AUDUSD=X","audusd"), "DXY": ("DX-Y.NYB",None), "VIX": ("^VIX",None),
    "GOLD": ("GC=F",None), "WTI": ("CL=F",None), "BRENT": ("BZ=F",None),
}
# series_code -> FRED series id (fetched via keyless fredgraph.csv) — macro the price feeds lack
FRED = {
    "US10Y": "DGS10",          # US 10-year Treasury yield (%)
    "US02Y": "DGS2",           # US 2-year Treasury yield (%)
    "CURVE_2S10S": "T10Y2Y",   # 10y minus 2y spread (%)
    "HY_OAS": "BAMLH0A0HYM2",  # ICE BofA US High Yield option-adjusted spread (%)
    "IRON_ORE": "PIORECRUSDM", # iron ore price (USD/tonne, monthly)
}

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def normalise(code, value):
    if value is None: return None
    if code == "US10Y" and value > 20:  # guard the old Yahoo x10 quirk; FRED is already %
        value /= 10.0
    return round(value, 4)

def fetch_yf(symbol):
    import yfinance as yf
    df = yf.Ticker(symbol).history(period="7d", auto_adjust=False)
    if df is None or df.empty: return None
    df = df.dropna(subset=["Close"])
    if df.empty: return None
    return df.index[-1].date().isoformat(), float(df.iloc[-1]["Close"]), "https://finance.yahoo.com/quote/" + symbol

def fetch_stooq(symbol):
    url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
    rows = list(csv.DictReader(io.StringIO(urllib.request.urlopen(url, timeout=25).read().decode("utf-8","replace"))))
    if not rows: return None
    r = rows[0]
    if r.get("Close") in (None,"","N/D") or r.get("Date") in (None,"","N/D"): return None
    return r["Date"], float(r["Close"]), url

def fetch_fred(fred_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    rows = list(csv.reader(io.StringIO(urllib.request.urlopen(url, timeout=25).read().decode("utf-8","replace"))))[1:]
    for row in reversed(rows):
        if len(row) >= 2 and row[1] not in (".","","N/D"):
            try: return row[0], float(row[1]), url
            except ValueError: pass
    return None

def fetch_market(code, yf_sym, stooq_sym):
    for fn, sym in ((fetch_yf, yf_sym), (fetch_stooq, stooq_sym)):
        if not sym: continue
        try:
            res = fn(sym)
            if res:
                d, v, src = res; v = normalise(code, v)
                if v is not None: return [code, d, v, src, now_iso(), "clean"]
        except Exception as e:
            sys.stderr.write(f"  {code} via {sym}: {e}\n")
    return [code, datetime.date.today().isoformat(), "", "", now_iso(), "failed"]

def fetch_macro(code, fred_id):
    try:
        res = fetch_fred(fred_id)
        if res:
            d, v, src = res; v = normalise(code, v)
            if v is not None: return [code, d, v, src, now_iso(), "clean"]
    except Exception as e:
        sys.stderr.write(f"  {code} via FRED {fred_id}: {e}\n")
    return [code, datetime.date.today().isoformat(), "", "", now_iso(), "failed"]

def ensure_header():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not os.path.exists(OUT) or os.path.getsize(OUT) == 0:
        with open(OUT, "w", newline="") as f: csv.writer(f).writerow(HEADER)

def append_rows(rows):
    ensure_header()
    with open(OUT, "a", newline="") as f: csv.writer(f).writerows(rows)

def selftest():
    ensure_header()
    test = [["TEST", datetime.date.today().isoformat(), 1.23, "selftest", now_iso(), "clean"]]
    append_rows(test)
    last = list(csv.reader(open(OUT)))[-1]
    assert last[0] == "TEST" and last[5] == "clean", "schema round-trip failed"
    print("selftest OK:", last)

def main():
    if "--selftest" in sys.argv: return selftest()
    rows, ok, fail = [], 0, 0
    for code, (yf_sym, stooq_sym) in SERIES.items():
        r = fetch_market(code, yf_sym, stooq_sym); rows.append(r)
        ok, fail = (ok+1, fail) if r[5]=="clean" else (ok, fail+1)
        print(("  OK   " if r[5]=="clean" else "  FAIL ") + f"{code:7} {r[1]} {r[2]}")
    for code, fred_id in FRED.items():
        r = fetch_macro(code, fred_id); rows.append(r)
        ok, fail = (ok+1, fail) if r[5]=="clean" else (ok, fail+1)
        print(("  OK   " if r[5]=="clean" else "  FAIL ") + f"{code:11} {r[1]} {r[2]} (FRED)")
    append_rows(rows)
    print(f"\nAppended {len(rows)} rows ({ok} clean / {fail} failed)")
    if fail == len(rows): sys.exit(1)   # total failure -> fail the Action so GitHub emails you

if __name__ == "__main__":
    main()
