#!/usr/bin/env python3
"""Weekly routine: refresh data, self-test, predict the next gameweek, update the season view.

    python3 weekly.py            # full refresh (re-downloads everything not already cached)
    python3 weekly.py --offline  # use cached data only

Outputs: output/EPL_Model.xlsx, output/weekly_report.md, output/predictions.csv
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import numpy as np
import pandas as pd

from eplmodel import (adjust, checks, data, evaluate as ev, excel, features, models, predictor, report, season,
                      selftest, simulate)
from eplmodel.config import CURRENT, N_SIMS, OUTPUT, label


def upcoming_fixtures(m: pd.DataFrame) -> pd.DataFrame:
    """Current-season fixtures (official FPL schedule) not yet in the results file."""
    s = label(CURRENT)
    fx = data.load_fpl_fixtures()
    fx = fx[fx["season"] == s]
    done = set(zip(m.loc[m["season"] == s, "home"], m.loc[m["season"] == s, "away"]))
    fx = fx[[(h, a) not in done for h, a in zip(fx["home"], fx["away"])]].copy()
    last = m["date"].max()
    fx["date"] = fx["date"].fillna(fx["date"].max() if fx["date"].notna().any() else last)
    out = pd.DataFrame({"season": s, "date": fx["date"], "home": fx["home"], "away": fx["away"],
                        "hg": np.nan, "ag": np.nan, "fixture": fx["fixture"], "fpl_gw": fx["gw"],
                        "kickoff_utc": fx["kickoff"],
                        "kickoff": fx["kickoff"].dt.tz_convert("Europe/London").dt.strftime("%a %d %b %H:%M")})
    out = out.sort_values(["kickoff_utc", "home"])
    out.index = pd.RangeIndex(m.index.max() + 1, m.index.max() + 1 + len(out))
    return out


def live_walk_forward(spec, m, F, seasons):
    """Walk-forward predictions of the production model for the given seasons (as in the backtest)."""
    out = []
    params = spec.get("factor_params_tune_only")
    sp = dict(spec, factor_params=params)
    for d, te in m[m["season"].isin(seasons)].groupby("date"):
        out.append(predictor.fit_predict(sp, m, te, d, F_fix=F))
    return pd.concat(out)


def main(offline=False):
    t0 = time.time()
    season_label = label(CURRENT)
    print("1/6 Refreshing data" + (" (offline)" if offline else ""))
    data.fetch_all(refresh=not offline)
    m = models.add_market_lambdas(data.build_matches())
    check_stats = checks.write_report(m)
    fx = upcoming_fixtures(m)
    allm = pd.concat([m, fx]).sort_values(["date", "home"])
    allm["gw"] = data.season_round(allm)
    m["gw"] = allm.loc[m.index, "gw"]
    fx["gw"] = allm.loc[fx.index, "gw"]
    print(f"    {len(m)} matches to {m['date'].max():%d %b %Y}; {len(fx)} fixtures remaining")

    print("2/6 Building features")
    promoted = data.promoted_teams(allm)
    F = adjust.prepare(features.build(allm), allm, promoted)
    spec = predictor.load_spec()

    print("3/6 Predicting")
    next_gw = int(fx.groupby("fpl_gw").size().loc[lambda s: s >= 5].index.min())
    gw_fx = fx[fx["fpl_gw"] == next_gw]
    as_of = fx["date"].min()
    pred = predictor.fit_predict(spec, m, fx, as_of, F_fix=F)
    out = predictor.match_outputs(pred.loc[gw_fx.index])

    print(f"4/6 Season view ({N_SIMS:,} simulations)")
    played = m[m["season"] == season_label]
    sims = simulate.simulate(season_label, played, fx, pred, sigma=spec.get("sim_sigma", 0.05))
    pr = season.power_rankings(spec, m, season_label, fx)
    luck = season.luck_table(m, season_label)
    sos = season.schedule_strength(pr["now"], pr["pairs"], m, season_label, fx)
    fdiff = season.fixture_difficulty(fx.join(pred))

    print("5/6 Self-test")
    wf = live_walk_forward(spec, m, F, ["2025-26", season_label])
    pw = ev.probs_from_pred(wf)
    idx_ref = pw.index[m.loc[pw.index, "season"] == "2025-26"]
    rps_ref = ev.rps(pw.loc[idx_ref, ["pH", "pD", "pA"]].to_numpy(), ev.outcome(m.loc[idx_ref])).mean()
    live_idx = pw.index[m.loc[pw.index, "season"] == season_label]
    results = (selftest.check_data(m, check_stats) + selftest.check_no_leakage(spec, m, F)
               + selftest.check_reproduction(spec, rps_ref) + selftest.check_predictions(pred, out)
               + selftest.check_sims(sims["table"]))

    print("6/6 Writing outputs")
    OUTPUT.mkdir(exist_ok=True)
    ctx = report.build_context(season_label, next_gw, gw_fx, out, pr, luck, sos, fdiff, sims, m, pw.loc[live_idx],
                               spec, check_stats)
    xlsx = OUTPUT / "EPL_Model.xlsx"
    excel.build(str(xlsx), ctx)
    results += selftest.check_workbook(xlsx)
    ok, lines = selftest.report(results)
    report.write_markdown(OUTPUT / "weekly_report.md", ctx, lines, ok)
    report.write_predictions_csv(OUTPUT / "predictions.csv", gw_fx, out)

    print()
    print(report.console_table(ctx))
    print()
    print("\n".join(lines))
    print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED")
    print(f"Done in {time.time() - t0:.0f}s -> {xlsx.relative_to(OUTPUT.parent)}, output/weekly_report.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(offline="--offline" in sys.argv))
