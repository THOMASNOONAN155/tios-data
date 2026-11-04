"""Self-test run by weekly.py. Each check returns (name, passed, detail)."""
from __future__ import annotations

import numpy as np
import openpyxl

from . import predictor
from .config import CURRENT, SEASONS, label
from .models import grid_markets, score_grid

SHEETS = ["Dashboard", "Power Rankings", "Ranking History", "Attack & Defence", "Expected Points & Luck",
          "Fixture Difficulty", "Season Projections", "Model vs Market", "Factor Tests", "About"]


def check_data(m, check_stats):
    res = []
    complete = [label(s) for s in SEASONS if s != CURRENT]
    counts = m.groupby("season").size()
    bad = [s for s in complete if counts.get(s, 0) != 380]
    res.append(("8+ complete seasons with 380 matches", len(complete) >= 8 and not bad, f"incomplete: {bad or 'none'}"))
    res.append(("no missing scores", bool(m[["hg", "ag"]].notna().all().all()), ""))
    recent = m[m["season"] >= "2019-20"]
    cov = {c: recent[c].notna().mean() for c in ["c_H", "c_over", "c_ahh", "hxg"]}
    res.append(("closing odds and xG coverage 2019-20+ >= 99%", all(v >= 0.99 for v in cov.values()),
                ", ".join(f"{k} {v:.1%}" for k, v in cov.items())))
    res.append(("scores agree across sources", check_stats.get("score_mismatches", 1) == 0,
                f"{check_stats.get('score_mismatches')} mismatches"))
    res.append(("closing odds agree across mirrors", check_stats.get("odds_mirror_mismatch", 1) == 0,
                f"{check_stats.get('odds_mirror_mismatch')} differing cells"))
    return res


def check_no_leakage(spec, m, F):
    """Predictions for a date must not change when every later result is scrambled."""
    d = m.loc[m["season"] == "2025-26", "date"].sort_values().iloc[150]
    target = m[m["date"] == d]
    fx = target.assign(hg=np.nan, ag=np.nan)
    p1 = predictor.fit_predict(spec, m, fx, d, F_fix=F)
    rng = np.random.default_rng(0)
    m2 = m.copy()
    later = m2["date"] >= d
    for c in ["hg", "ag"]:
        m2.loc[later, c] = rng.integers(0, 6, later.sum())
    for c in ["hxg", "axg", "mkt_lh", "mkt_la"]:
        m2.loc[later, c] = rng.uniform(0.2, 3.0, later.sum())
    p2 = predictor.fit_predict(spec, m2, fx, d, F_fix=F)
    diff = float(np.abs(p1[["lh", "la"]].to_numpy() - p2[["lh", "la"]].to_numpy()).max())
    return [("no look-ahead: scrambling future results leaves predictions unchanged", diff < 1e-12,
             f"max change {diff:.2e} ({d:%Y-%m-%d})")]


def check_reproduction(spec, rps_2526):
    ref = spec.get("selftest_reference", {}).get("rps")
    ok = ref is not None and abs(rps_2526 - ref) < 2e-4
    return [("walk-forward 2025-26 RPS reproduces backtest", ok, f"now {rps_2526:.5f} vs backtest {ref:.5f}"
             if ref else "no reference")]


def check_predictions(pred, outputs):
    g = score_grid(pred["lh"].values, pred["la"].values, pred["rho"].values, pred["dmult"].values)
    mk = grid_markets(g)
    sums_ok = np.allclose(g.sum((1, 2)), 1) and np.allclose(mk["pH"] + mk["pD"] + mk["pA"], 1)
    lam_ok = bool(((pred["lh"] > 0.05) & (pred["lh"] < 6) & (pred["la"] > 0.05) & (pred["la"] < 6)).all())
    out_ok = bool(outputs[["pH", "pD", "pA", "pOver25", "pBTTS"]].apply(lambda s: s.between(0, 1)).all().all())
    return [("scoreline grids and 1X2 sum to 1", bool(sums_ok), ""),
            ("expected goals in plausible range", lam_ok, f"{pred['lh'].min():.2f}-{pred['lh'].max():.2f}"),
            ("all match probabilities in [0, 1]", out_ok, "")]


def check_sims(t, n_teams=20):
    ok = abs(t["p_title"].sum() - 1) < 1e-9 and abs(t["p_relegation"].sum() - 3) < 1e-9 and abs(t["p_top4"].sum() - 4) < 1e-9
    return [("season simulation probabilities consistent", bool(ok and len(t) == n_teams),
             f"title {t['p_title'].sum():.3f}, top4 {t['p_top4'].sum():.3f}, relegation {t['p_relegation'].sum():.3f}")]


def check_workbook(path):
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        missing = [s for s in SHEETS if s not in wb.sheetnames]
        return [("Excel workbook opens with all sheets", not missing, f"missing: {missing or 'none'}")]
    except Exception as e:
        return [("Excel workbook opens with all sheets", False, str(e))]


def report(results):
    ok = all(r[1] for r in results)
    lines = [f"  [{'PASS' if r[1] else 'FAIL'}] {r[0]}" + (f" ({r[2]})" if r[2] else "") for r in results]
    return ok, lines
