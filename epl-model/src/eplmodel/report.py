"""Assemble the weekly outputs: workbook context, Markdown report, predictions CSV, console table."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import evaluate as ev
from .config import N_SIMS, REPORTS
from .predictor import compact_grid


def _pct(x):
    return f"{x:.0%}"


def build_context(season, gw, gw_fx, out, pr, luck, sos, fdiff, sims, m, live_probs, spec, check_stats):
    md = pd.DataFrame({
        "Kickoff (UK)": gw_fx["kickoff"].values, "Home": gw_fx["home"].values, "Away": gw_fx["away"].values,
        "xG H": out["xg_h"].values, "xG A": out["xg_a"].values, "Most likely": out["ml_score"].values,
        "Score %": out["ml_pct"].values, "Home %": out["pH"].values, "Draw %": out["pD"].values,
        "Away %": out["pA"].values, "Over 2.5 %": out["pOver25"].values, "BTTS %": out["pBTTS"].values,
        "Top 5 scores": out["top5"].values})
    grids = [(f"{h} v {a}", g) for h, a, g in zip(gw_fx["home"], gw_fx["away"], out["grid"])]
    now = pr["now"]
    rankings = pd.DataFrame({
        "Rank": now["rank"].values, "Move": now["movement"].fillna(0).values, "Team": now.index,
        "Net rating": now["net"].values, "Attack (xG for)": now["attack"].values,
        "Defence (xG against)": now["defence"].values, "xPts/game": now["xpts_per_game"].values,
        "xGD/game (actual)": now["xgd_pg"].values, "GD/game": now["gd_pg"].values, "Played": now["played"].values})
    hist = pr["history"].loc[now.index]
    lk = luck.reset_index().rename(columns={"index": "Team"})
    lk = pd.DataFrame({"Team": lk["Team"], "Played": lk["played"], "Points": lk["points"], "xPts (from xG)": lk["xpts"],
                       "Luck (pts)": lk["luck_points"], "Goals for": lk["gf"], "xG for": lk["xgf"],
                       "Goals against": lk["ga"], "xG against": lk["xga"], "Finishing (G-xG)": lk["finishing"],
                       "Goalkeeping (xGA-GA)": lk["goalkeeping"]})
    fd = fdiff.join(sos)
    fdo = pd.DataFrame({"Team": fd.index})
    for k in range(1, 6):
        fdo[f"Opp {k}"] = fd.get(f"fx{k}", pd.Series(dtype=object)).values
        fdo[f"xPts {k}"] = fd.get(f"xp{k}", pd.Series(dtype=float)).values
    fdo["xPts next 5"] = fd["xpts_next"].values
    fdo["SoS played"] = fd["sos_played"].values
    fdo["SoS played rank"] = fd["sos_played_rank"].astype(float).values
    fdo["SoS remaining"] = fd["sos_remaining"].values
    fdo["SoS remaining rank"] = fd["sos_remaining_rank"].astype(float).values
    t = sims["table"]
    sp = pd.DataFrame({"Team": t["team"], "Points now": t["points_now"], "Projected pts": t["exp_points"],
                       "Low (10%)": t["p10_points"], "High (90%)": t["p90_points"], "Projected GD": t["exp_gd"],
                       "Avg position": t["exp_position"], "Title": t["p_title"], "Top 4": t["p_top4"],
                       "Top 5": t["p_top5"], "Top 7": t["p_top7"], "Relegation": t["p_relegation"]})
    acc_file = REPORTS / "accuracy.csv"
    acc = pd.read_csv(acc_file) if acc_file.exists() else pd.DataFrame()
    if len(acc):
        acc = acc[acc["Forecaster"].isin(["Model (final)", "Closing market"])][
            ["Period", "Forecaster", "Matches", "RPS", "LogLoss", "Brier", "Correct%", "ExactScore%", "GoalMAE",
             "OU2.5 LogLoss", "Draw% pred", "Draw% actual"]]
    live = None
    if len(live_probs):
        lm = m.loc[live_probs.index]
        a = ev.metrics(live_probs, lm)
        mk = lm[["mH", "mD", "mA"]].rename(columns={"mH": "pH", "mD": "pD", "mA": "pA"})
        b = ev.metrics(mk, lm)
        live = pd.DataFrame([{"Forecaster": "Model", "Matches": a["n"], "RPS": a["RPS"], "LogLoss": a["LogLoss"],
                              "Correct%": a["Correct%"]},
                             {"Forecaster": "Closing market", "Matches": b["n"], "RPS": b["RPS"], "LogLoss": b["LogLoss"],
                              "Correct%": b["Correct%"]}])
    dates = gw_fx["date"]
    ctx = {"season": season, "gw": gw, "gw_dates": f"{dates.min():%a %d %b} – {dates.max():%a %d %b %Y}",
           "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "data_to": f"{m['date'].max():%d %b %Y}",
           "matches": md, "grids": grids, "rankings": rankings, "history": hist, "luck": lk, "fixtures": fdo,
           "sims": sp, "accuracy": acc, "live": live, "n_sims": N_SIMS, "spec": spec, "positions": sims["positions"]}
    ctx["about"] = about_lines(ctx, check_stats)
    return ctx


def about_lines(ctx, check_stats):
    spec = ctx["spec"]
    acc = ctx["accuracy"]
    verdict = ""
    if len(acc):
        test = acc[acc["Period"].str.startswith("Test")]
        mod, mkt = test[test["Forecaster"] == "Model (final)"]["RPS"].mean(), test[test["Forecaster"] == "Closing market"]["RPS"].mean()
        verdict = (f"Over the two test periods the model's RPS is {mod:.4f} against {mkt:.4f} for the closing market: "
                   + ("the model does NOT beat the bookmakers' closing odds." if mod >= mkt else "the model beats the closing odds."))
    return [
        "## What this is",
        f"Predictions for Premier League {ctx['season']} gameweek {ctx['gw']} and a season view, regenerated by "
        "`python3 weekly.py`. Every number comes from real published data; nothing is estimated by hand.",
        "## Honest verdict",
        verdict or "Run backtest.py to produce the accuracy comparison.",
        "The closing market is the best public forecast available; the model's value is transparency (xG, ratings, "
        "scorelines, season odds), not an edge over the bookmakers.",
        "## Model",
        f"Blend of {', '.join(f'{k} ({v:.0%})' for k, v in spec['blend'].items())} expected goals; Dixon-Coles "
        "low-score correction; factors kept after out-of-sample testing: "
        f"{', '.join(spec.get('factors') or []) or 'none'}. Ratings decay over time (half-lives tuned on 2018-22).",
        "## Sheets",
        "Dashboard: this gameweek's matches — expected goals (xG H/A), most likely score and its probability, home/draw/away, "
        "over 2.5 goals, both teams to score, top-5 scorelines, and full 0-6+ scoreline grids.",
        "Power Rankings: teams ordered by net rating = expected goal difference per game against an average schedule; "
        "Move = places gained since last week.",
        "Ranking History: rank before each gameweek. Attack & Defence: ratings and scatter chart.",
        "Expected Points & Luck: points earned vs expected points from each match's xG; finishing and goalkeeping over/under-performance.",
        "Fixture Difficulty: next five opponents with the model's expected points (green = easier) and strength of schedule.",
        f"Season Projections: {ctx['n_sims']:,} simulations of the remaining fixtures with rating uncertainty.",
        "Model vs Market: walk-forward accuracy against margin-free closing odds.",
        "## Data sources",
        "football-data.co.uk results, match stats and closing odds (1X2, over/under 2.5, Asian handicap; Pinnacle, Betfair "
        "Exchange and market average), via the GitHub mirror ValentinMartine/football_predictions when the site is unreachable.",
        "Understat xG (2019-25) and official Fantasy Premier League data (Opta xG, minutes, starts, fixtures) via vaastav/Fantasy-Premier-League.",
        "openfootball (results cross-check and UEFA fixtures), xgabora/Club-Football-Match-Data (odds cross-check), "
        "rohanhs568/next_manager_sacked (manager spells).",
        f"Cross-checks this run: score mismatches {check_stats.get('score_mismatches')}, closing-odds mirror differences "
        f"{check_stats.get('odds_mirror_mismatch')}, red-card mismatch rate {check_stats.get('red_mismatch_rate', 0):.1%}.",
        "## Limitations",
        "No lineups or injuries for upcoming games (player data lags); no domestic cup fixtures; UEFA fixture coverage is "
        "partial and absent for 2026-27; manager data ends Aug 2026; xG providers differ by season (Understat vs Opta).",
    ]


def write_markdown(path, ctx, test_lines, ok):
    L = [f"# Premier League {ctx['season']} — Gameweek {ctx['gw']}", "",
         f"{ctx['gw_dates']} · generated {ctx['generated']} · results to {ctx['data_to']} · "
         f"self-test {'PASSED' if ok else 'FAILED'}", "", "## Matches", "",
         "| Kickoff | Match | xG | Most likely | H / D / A | Over 2.5 | BTTS | Top 5 scores |", "|---|---|---|---|---|---|---|---|"]
    for r in ctx["matches"].itertuples(index=False):
        L.append(f"| {r[0]} | {r[1]} v {r[2]} | {r[3]:.2f} – {r[4]:.2f} | {r[5]} ({r[6]:.0%}) | "
                 f"{r[7]:.0%} / {r[8]:.0%} / {r[9]:.0%} | {r[10]:.0%} | {r[11]:.0%} | {r[12]} |")
    L += ["", "## Power rankings", "", "| # | Move | Team | Net | Attack | Defence | xGD/game |", "|---|---|---|---|---|---|---|"]
    for r in ctx["rankings"].itertuples(index=False):
        mv = "–" if r[1] == 0 else (f"▲{int(r[1])}" if r[1] > 0 else f"▼{int(-r[1])}")
        L.append(f"| {r[0]} | {mv} | {r[2]} | {r[3]:+.2f} | {r[4]:.2f} | {r[5]:.2f} | {r[7]:+.2f} |")
    L += ["", f"## Season odds ({ctx['n_sims']:,} simulations)", "",
          "| Team | Pts now | Projected | Title | Top 4 | Top 5 | Relegation |", "|---|---|---|---|---|---|---|"]
    for r in ctx["sims"].itertuples(index=False):
        L.append(f"| {r[0]} | {int(r[1])} | {r[2]:.1f} | {r[7]:.1%} | {r[8]:.1%} | {r[9]:.1%} | {r[11]:.1%} |")
    L += ["", "## Luck (actual points minus expected points from xG)", "", "| Team | Pts | xPts | Luck |", "|---|---|---|---|"]
    for r in ctx["luck"].itertuples(index=False):
        L.append(f"| {r[0]} | {int(r[2])} | {r[3]:.1f} | {r[4]:+.1f} |")
    if ctx["live"] is not None:
        L += ["", "## Accuracy this season (walk-forward)", "", "| Forecaster | Matches | RPS | Log loss | Correct |", "|---|---|---|---|---|"]
        for r in ctx["live"].itertuples(index=False):
            L.append(f"| {r[0]} | {r[1]} | {r[2]:.4f} | {r[3]:.4f} | {r[4]:.0f}% |")
    L += ["", "## Self-test", "", "```", *test_lines, "```", ""]
    path.write_text("\n".join(L) + "\n")


def write_predictions_csv(path, gw_fx, out):
    rows = []
    for (idx, f), (_, o) in zip(gw_fx.iterrows(), out.iterrows()):
        r = {"kickoff_uk": f["kickoff"], "home": f["home"], "away": f["away"], "xg_home": round(o["xg_h"], 3),
             "xg_away": round(o["xg_a"], 3), "p_home": round(o["pH"], 4), "p_draw": round(o["pD"], 4),
             "p_away": round(o["pA"], 4), "p_over25": round(o["pOver25"], 4), "p_btts": round(o["pBTTS"], 4),
             "most_likely": o["ml_score"], "most_likely_pct": round(o["ml_pct"], 4), "top5": o["top5"]}
        cg = compact_grid(o["grid"])
        for i in range(7):
            for j in range(7):
                r[f"{'6+' if i == 6 else i}-{'6+' if j == 6 else j}"] = round(cg[i, j], 5)
        rows.append(r)
    pd.DataFrame(rows).to_csv(path, index=False)


def console_table(ctx):
    L = [f"Gameweek {ctx['gw']} ({ctx['gw_dates']})",
         f"{'Match':<34}{'xG':>11}  {'Likely':>9}  {'H':>4} {'D':>4} {'A':>4}  {'O2.5':>5} {'BTTS':>5}"]
    for r in ctx["matches"].itertuples(index=False):
        L.append(f"{r[1] + ' v ' + r[2]:<34}{r[3]:>5.2f}-{r[4]:<5.2f}  {r[5]:>4} {r[6]:>3.0%}  {r[7]:>4.0%} {r[8]:>4.0%} "
                 f"{r[9]:>4.0%}  {r[10]:>5.0%} {r[11]:>5.0%}")
    return "\n".join(L)
