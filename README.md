# TIOS data pipeline — free, always-on daily prices

This is the **external runtime** half of the system (see `../CAPABILITY-CEILING.md`).
A free GitHub Actions cron pulls EOD market data every day — even when your laptop and
the Claude app are closed — and commits it to this repo. The main TIOS app then reads
that file and does the analysis. This is what unblocks a real daily history + genuine
statistics for $0.

## What it fetches (EOD close, appended daily to `data/prices.csv`)
- **Your 11 holdings:** VAS, VHY, IVV, VGS, ASIA, HEUR, EMKT, NDQ, GGUS, QAU, CRYP
- **Benchmarks:** AXJO (ASX 200), SPX (S&P 500), IXIC (Nasdaq Comp.)
- **FX / rates / vol / commodities:** AUD/USD, DXY, US 10-yr, VIX, gold, WTI, Brent

Schema matches `observations_clean.csv` (`series_code,date,value,source_url,fetched_at,flag`)
so the main repo can merge it directly. Append-only and immutable; failures are flagged
`failed`, never invented. Source: yfinance, with a stooq fallback.

## Setup (one-time, ~5 minutes)
1. **Create a new repo** on GitHub — **Public** is recommended: it gives *unlimited*
   Actions minutes and lets the TIOS app read the file over the plain `raw` URL.
   ⚠️ **Privacy:** this repo holds **market prices only — NO personal holdings, units,
   cost or balances.** Keep all of that in the local "Shares Management" folder. (If you
   prefer Private: Actions still work on the free 2,000 min/month, but the app can't read
   the raw URL without a token — you'd sync via `git pull` instead.)
2. Copy the contents of this `tios-data-pipeline/` folder into the new repo and push.
3. On GitHub: **Settings → Actions → General → Workflow permissions → "Read and write"** (so the job can commit).
4. **Actions tab → "TIOS daily prices" → Run workflow** to test it now. Check `data/prices.csv` filled in.
5. It then runs itself daily at 07:30 UTC (after the ASX close).

## How the TIOS app reads it back
Once the repo exists, give the assistant the raw URL of the file, e.g.:
`https://raw.githubusercontent.com/<you>/<repo>/main/data/prices.csv`
(tested: the app's runtime can reach `raw.githubusercontent.com`). The daily in-app task
will fetch it, merge into `observations.csv`, and refresh the dashboard's live layer — no
app-open dependency for the *fetching* (the cron does that), only for the *analysis*.
Save that URL in `../data/pipeline-source.txt` and the task will pick it up.

## Honest caveats
- **EOD only**, not intraday/real-time (fine for a 20–40-yr accumulator).
- **yfinance/stooq are unofficial and can break.** The job fails loudly (and emails you)
  if *every* ticker fails; per-ticker failures are flagged and the last good value stands.
- **Sanity-check on first run:** confirm DXY, US 10-yr (the script auto-corrects Yahoo's
  occasional ×10 quirk → ~4.45) and the commodities read sensibly; adjust symbols if a
  provider renames one.
- Some Betashares tickers can be thin on yfinance — if one keeps failing, the stooq
  fallback (`*.au`) usually covers it; otherwise it stays on its last value, flagged.

## Test locally without network
`python fetch_prices.py --selftest`  → validates the CSV write/read path only.
`python fetch_prices.py`             → real fetch (needs internet; runs on the Action).
