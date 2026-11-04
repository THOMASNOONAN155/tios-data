#!/usr/bin/env python3
"""Full walk-forward model selection and evaluation (slow: ~30 minutes).

    python3 backtest.py          # tune, compare, test factors, evaluate, calibrate season sims
    python3 backtest.py --quick  # smoke test: no tuning, tiny simulation calibration
    python3 backtest.py --reuse-tuning  # skip stage 1 if cache/tuned_specs.json exists

Writes config/model_spec.json (used by weekly.py), reports/BACKTEST.md, reports/EXPERIMENTS.md and
appends every trial to reports/experiment_log.csv.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import numpy as np
import pandas as pd

from eplmodel import adjust, data, evaluate as ev, experiments as ex, features, models, predictor, simulate
from eplmodel.config import CACHE, CONFIG, LIVE, REPORTS, TEST_A, TEST_B, TUNE

PERIOD_ROWS = [("Tuning 2018-22", TUNE), ("Test A 2022-24", TEST_A), ("Test B 2024-26", TEST_B), ("Live 2026-27", LIVE)]


def fmt_table(df, floats=4):
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join(f"{v:.{floats}f}" if isinstance(v, (float, np.floating)) else str(v) for v in r) + " |")
    return "\n".join(out)


def full_metrics(p, m, name):
    rows = []
    for label, seasons in PERIOD_ROWS:
        idx = p.index[m.loc[p.index, "season"].isin(seasons)]
        if len(idx):
            r = ev.metrics(p.loc[idx], m.loc[idx])
            rows.append({"Period": label, "Forecaster": name, "Matches": r["n"], "RPS": r["RPS"], "LogLoss": r["LogLoss"],
                         "Brier": r["Brier"], "Correct%": r["Correct%"], "ExactScore%": r.get("ExactScore%", np.nan),
                         "GoalMAE": r.get("GoalMAE", np.nan), "OU2.5 LogLoss": r.get("OU_LogLoss", np.nan),
                         "BTTS LogLoss": r.get("BTTS_LogLoss", np.nan), "Draw% pred": r["DrawPred%"],
                         "Draw% actual": r["DrawActual%"]})
    return rows


def luck_vs_skill(m):
    """Year-to-year persistence (team level) of measures often called skill or luck."""
    rows = []
    for s, g in m[m["season"] >= "2019-20"].groupby("season"):
        for t in set(g["home"]):
            h, a = g[g["home"] == t], g[g["away"] == t]
            n = len(h) + len(a)
            rows.append({"season": s, "team": t,
                         "pens_won": (h["hpen"].sum() + a["apen"].sum()) / n if h["hpen"].notna().all() and a["apen"].notna().all() else np.nan,
                         "reds": (h["hr"].sum() + a["ar"].sum()) / n,
                         "opp_reds": (h["ar"].sum() + a["hr"].sum()) / n,
                         "finishing": ((h["hg"].sum() + a["ag"].sum()) - (h["hxg"].sum() + a["axg"].sum())) / n,
                         "gk_luck": ((h["axg"].sum() + a["hxg"].sum()) - (h["ag"].sum() + a["hg"].sum())) / n,
                         "xgd": ((h["hxg"] - h["axg"]).sum() + (a["axg"] - a["hxg"]).sum()) / n,
                         "gd": ((h["hg"] - h["ag"]).sum() + (a["ag"] - a["hg"]).sum()) / n})
    d = pd.DataFrame(rows)
    seasons = sorted(d["season"].unique())
    nxt = {s: seasons[i + 1] for i, s in enumerate(seasons[:-1])}
    d2 = d.assign(next=d["season"].map(nxt)).merge(d, left_on=["next", "team"], right_on=["season", "team"],
                                                   suffixes=("", "_next"))
    out = []
    for c, label in [("xgd", "xG difference per game"), ("gd", "Goal difference per game"),
                     ("finishing", "Finishing: goals minus xG per game"), ("gk_luck", "Goals prevented vs xG against"),
                     ("pens_won", "Penalties won per game"), ("reds", "Red cards received per game"),
                     ("opp_reds", "Opponent red cards per game")]:
        x = d2[[c, c + "_next"]].dropna()
        out.append({"Measure": label, "Team-seasons": len(x), "Correlation with next season": x.corr().iloc[0, 1]})
    return pd.DataFrame(out)


def sim_calibration(spec, m, seasons, sigmas, rounds=(1, 10, 20, 30), n_sims=20000):
    """Simulate past seasons from several checkpoints using only information available at each
    checkpoint (results after the checkpoint are blanked before features are rebuilt); score
    title / top-4 / relegation probabilities against what happened."""
    recs = []
    promoted = data.promoted_teams(m)
    for s in seasons:
        g = m[m["season"] == s]
        final = simulate.final_table(g, s).set_index("team")
        for rd in rounds:
            as_of = g.loc[g["gw"] >= rd, "date"].min()
            played, remaining = g[g["date"] < as_of], g[g["date"] >= as_of]
            fut = remaining.assign(hg=np.nan, ag=np.nan, hxg=np.nan, axg=np.nan, hr=np.nan, ar=np.nan,
                                   hc=np.nan, ac=np.nan, hpen=np.nan, apen=np.nan)
            Fc = None
            if spec.get("factor_params"):
                view = pd.concat([m[m["date"] < as_of], fut])
                Fc = adjust.prepare(features.build(view), view, promoted)
            pred = predictor.fit_predict(spec, m[m["date"] < as_of], fut, as_of, F_fix=Fc)
            for sg in sigmas:
                res = simulate.simulate(s, played, remaining, pred, n_sims=n_sims, sigma=sg)["table"].set_index("team")
                for t in res.index:
                    pos = final.loc[t, "pos"]
                    for ev_name, col, hit in [("title", "p_title", pos == 1), ("top4", "p_top4", pos <= 4),
                                              ("relegation", "p_relegation", pos >= 18)]:
                        recs.append({"season": s, "round": rd, "sigma": sg, "team": t, "event": ev_name,
                                     "p": res.loc[t, col], "y": float(hit), "exp_pts": res.loc[t, "exp_points"],
                                     "pts": final.loc[t, "pts"]})
    return pd.DataFrame(recs)


def main(quick=False, reuse_tuning=False):
    print("Loading data (cache must be populated: run weekly.py once, or data.fetch_all())")
    data.fetch_all(refresh=False)
    m = models.add_market_lambdas(data.build_matches())
    f = features.build(m)
    res = ex.run_all(m, f, quick=quick, reuse_tuning=reuse_tuning)
    F = res["F"]

    # final specification ---------------------------------------------------------------------
    spec = {"models": {n: res["specs"][n] for n in set(res["blend"]) | {"dixon_coles"}}, "blend": res["blend"],
            "rho_from": "dixon_coles", "factors": res["factors"]}
    base = ex.blend(res["preds"], res["blend"])
    final_pred = base
    if res["factors"]:
        names = [n for n in res["factors"] if n != "lineup_strength"]
        tune_idx = base.index[m.loc[base.index, "season"].isin(TUNE)]
        params_tune = adjust.fit(F.loc[tune_idx], base.loc[tune_idx], m.loc[tune_idx], adjust.merge_specs(names))
        final_pred = adjust.apply(F.loc[base.index], base, params_tune)
        # production coefficients: refit on all completed seasons (still only past information for live use)
        hist_idx = base.index[m.loc[base.index, "season"].isin(TUNE + TEST_A + TEST_B)]
        spec["factor_params"] = adjust.fit(F.loc[hist_idx], base.loc[hist_idx], m.loc[hist_idx], adjust.merge_specs(names))
        spec["factor_params_tune_only"] = params_tune
    # evaluation -------------------------------------------------------------------------------
    pf = ev.probs_from_pred(final_pred)
    mk = ex.market_pred(m)
    rows = full_metrics(pf, m, "Model (final)") + full_metrics(mk.loc[pf.index], m, "Closing market")
    for n in ["poisson", "dixon_coles", "xg", "xg_goals_mix", "market", "elo"]:
        rows += full_metrics(ev.probs_from_pred(res["preds"][n]), m, f"  {n}")
    acc = pd.DataFrame(rows)
    test_idx = pf.index[m.loc[pf.index, "season"].isin(TEST_A + TEST_B)]
    cal_model = ev.calibration(pf.loc[test_idx], m.loc[test_idx])
    cal_mkt = ev.calibration(mk.loc[test_idx], m.loc[test_idx])
    stage_rows = []
    st = pd.Series(ev.stage(m.loc[test_idx, "gw"]), index=test_idx)
    for sname in ["GW1-5", "GW6-12", "GW13-19", "GW20-29", "GW30-38"]:
        ii = st.index[st == sname]
        a, b = ev.metrics(pf.loc[ii], m.loc[ii]), ev.metrics(mk.loc[ii], m.loc[ii])
        stage_rows.append({"Stage": sname, "Matches": len(ii), "Model RPS": a["RPS"], "Market RPS": b["RPS"],
                           "Model LogLoss": a["LogLoss"], "Market LogLoss": b["LogLoss"], "Model correct%": a["Correct%"],
                           "Market correct%": b["Correct%"]})
    stage_df = pd.DataFrame(stage_rows)
    # draws
    draw_bins = pd.cut(pf.loc[test_idx, "pD"], [0, .2, .25, .3, .35, 1])
    draws = pd.DataFrame({"pD": pf.loc[test_idx, "pD"], "draw": (m.loc[test_idx, "hg"] == m.loc[test_idx, "ag"]).astype(float),
                          "bin": draw_bins}).groupby("bin", observed=True).agg(n=("draw", "size"), predicted=("pD", "mean"),
                                                                              actual=("draw", "mean")).reset_index()
    lvs = luck_vs_skill(m)
    lvs.to_csv(REPORTS / "luck_vs_skill.csv", index=False)
    # season simulation calibration: sigma chosen on tuning seasons, checked on test seasons
    print("Season-simulation calibration")
    sigmas = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    sim_seasons = ["2019-20", "2020-21", "2021-22"] + TEST_A + TEST_B
    if quick:
        sigmas, sim_seasons = [0.0, 0.1], ["2021-22", "2023-24"]
    calib = sim_calibration(spec, m, sim_seasons, sigmas, n_sims=2000 if quick else 20000)
    calib["brier"] = (calib["p"] - calib["y"]) ** 2
    sig_tab = calib.assign(period=np.where(calib["season"].isin(TUNE), "Tuning", "Test")).pivot_table(
        index="sigma", columns="period", values="brier", aggfunc="mean").reset_index()
    best_sigma = float(sig_tab.loc[sig_tab["Tuning"].idxmin(), "sigma"])
    spec["sim_sigma"] = best_sigma
    cs = calib[(calib["sigma"] == best_sigma) & ~calib["season"].isin(TUNE)]
    sim_bins = cs.assign(bin=pd.cut(cs["p"], [-0.001, 0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98, 1.0])).groupby(
        "bin", observed=True).agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean")).reset_index()
    sim_events = cs.pivot_table(index="event", columns="round", values="brier", aggfunc="mean")
    sim_events.columns = [f"from round {c}" for c in sim_events.columns]
    sim_events = sim_events.reset_index()
    t1 = cs[cs["event"] == "title"]
    pts_err = t1.assign(err=(t1["exp_pts"] - t1["pts"]).abs()).groupby("round")["err"].mean().reset_index()
    pts_err.columns = ["From round", "Points MAE"]

    # self-test reference: RPS of the final model on 2025-26 (re-computed by weekly.py self-test)
    ref_idx = pf.index[m.loc[pf.index, "season"] == "2025-26"]
    spec["selftest_reference"] = {"season": "2025-26", "rps": float(ev.rps(pf.loc[ref_idx, ["pH", "pD", "pA"]].to_numpy(),
                                                                              ev.outcome(m.loc[ref_idx])).mean())}
    CONFIG.joinpath("model_spec.json").write_text(json.dumps(spec, indent=2, default=float))
    acc.to_csv(REPORTS / "accuracy.csv", index=False)

    # reports ---------------------------------------------------------------------------------
    logdf = pd.DataFrame(ex.LOG)
    logdf.to_csv(REPORTS / "latest_tests.csv", index=False)
    logf = REPORTS / "experiment_log.csv"
    logdf.to_csv(logf, mode="a", header=not logf.exists(), index=False)
    ex_md = ["# Experiment log", "", "Every test run by `backtest.py`, in order. RPS = ranked probability score "
             "(lower is better); dRPS = change vs the current model (negative = better). Rule: a change is **kept** "
             "only if its gain is clearly bigger than noise on both Test A (2022-24) and Test B (2024-26): a paired "
             "bootstrap over match dates (2,000 resamples) must put the one-sided 95% upper bound of dRPS below zero "
             "in each period. Parameters and coefficients are fitted on the tuning seasons (2018-22) only. "
             "Full history across runs: `experiment_log.csv`.", "", fmt_table(logdf.fillna(""), 5)]
    (REPORTS / "EXPERIMENTS.md").write_text("\n".join(ex_md) + "\n")
    main_rows = acc[acc["Forecaster"].isin(["Model (final)", "Closing market"])]
    md = ["# Backtest results", "",
          "All numbers are walk-forward: every match is predicted from a model fitted only on matches played "
          "before its kickoff date. Tuning seasons 2018-19 to 2021-22; Test A 2022-23 and 2023-24; Test B "
          "2024-25 and 2025-26; Live = 2026-27 so far. Market = closing odds (Pinnacle, else Betfair Exchange, "
          "else market average) with the margin removed by the power method.", "",
          f"Final model: blend {json.dumps(res['blend'])}; factors kept: {res['factors'] or 'none'}.", "",
          "## Final model vs closing market", "", fmt_table(main_rows, 4), "",
          "## All models", "", fmt_table(acc, 4), "",
          "## Calibration on the test periods (home/draw/away pooled)", "", "Model:", "",
          fmt_table(cal_model, 3), "", "Market:", "", fmt_table(cal_mkt, 3), "",
          "## Draws (test periods)", "", fmt_table(draws, 3), "",
          "## Accuracy by stage of season (test periods)", "", fmt_table(stage_df, 4), "",
          "## Luck or skill? Year-to-year persistence (team level, 2019-20 onwards)", "",
          "A measure that is mostly luck shows little correlation from one season to the next.", "",
          fmt_table(lvs, 3), "",
          "## Season simulation calibration", "",
          f"Rating-uncertainty sigma chosen on tuning seasons: **{best_sigma}**. Mean Brier score of title/top-4/"
          "relegation probabilities by sigma:", "", fmt_table(sig_tab, 4), "",
          "Test-season reliability (predicted vs observed frequency, all checkpoints):", "", fmt_table(sim_bins, 3), "",
          "Brier by event and checkpoint round (test seasons):", "", fmt_table(sim_events, 4),
          "", "Mean absolute error of projected final points by checkpoint round (test seasons):", "",
          fmt_table(pts_err, 2), ""]
    (REPORTS / "BACKTEST.md").write_text("\n".join(md) + "\n")
    print(fmt_table(main_rows, 4))
    print(f"done in {res['elapsed'] / 60:.1f} min (+ evaluation)")


if __name__ == "__main__":
    main(quick="--quick" in sys.argv, reuse_tuning="--reuse-tuning" in sys.argv)
