"""Cross-source data checks: scores, odds, red cards and xG compared between independent sources."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from .config import CACHE, REPORTS


def _pair(m, other, max_days=3):
    j = m.reset_index().merge(other, on=["home", "away"], suffixes=("", "_o"))
    j = j[(j["date"] - j["date_o"]).abs().dt.days <= max_days]
    return j.drop_duplicates("index")


def run(m: pd.DataFrame) -> tuple[list[str], dict]:
    lines, stats = [], {}

    def section(t):
        lines.extend(["", f"## {t}", ""])

    # 1. scores: football-data vs official FPL fixtures vs openfootball
    section("Scores")
    lines.append("| Season | football-data matches | vs FPL (official PL) | mismatches | vs openfootball | mismatches |")
    lines.append("|---|---|---|---|---|---|")
    fx = data.load_fpl_fixtures()
    fx = fx[fx["finished"]].rename(columns={"date": "date_o", "hg": "hg_o", "ag": "ag_o"})
    of = data.load_openfootball_results().rename(columns={"date": "date_o", "hg": "hg_o", "ag": "ag_o"})
    total_mis, examples = 0, []
    for s, g in m.groupby("season"):
        row = [s, str(len(g))]
        for other in (fx, of):
            j = _pair(g, other[other["season"] == s].drop(columns="season"))
            bad = j[(j["hg"] != j["hg_o"]) | (j["ag"] != j["ag_o"])]
            total_mis += len(bad)
            examples += [f"{r.season} {r.home} v {r.away} ({r.date:%Y-%m-%d}): football-data {r.hg}-{r.ag}, "
                         f"other {int(r.hg_o)}-{int(r.ag_o)}" for r in bad.itertuples()]
            row += [str(len(j)), str(len(bad))]
        lines.append("| " + " | ".join(row) + " |")
    stats["score_mismatches"] = total_mis
    if examples:
        lines += ["", "Mismatches:"] + [f"- {e}" for e in examples[:30]]

    # 2. odds: primary mirror vs second independent mirror of football-data; Bet365 vs xgabora
    section("Odds")
    m2 = data.load_football_data("fd_mirror2")
    if len(m2):
        j = m.merge(m2, on=["season", "home", "away"], suffixes=("", "_2"))
        cols = ["c_H", "c_D", "c_A", "c_over", "c_under", "c_ahline", "c_ahh", "c_aha"]
        diff = {c: int((~np.isclose(j[c], j[c + "_2"], equal_nan=True)).sum()) for c in cols}
        lines.append(f"Closing odds, primary mirror vs second mirror ({len(j)} matches, "
                     f"{', '.join(sorted(j['season'].unique()))}): cells differing = {diff}")
        stats["odds_mirror_mismatch"] = sum(diff.values())
    try:
        x = pd.read_csv(CACHE / "xgabora_matches.csv", low_memory=False)
        x = x[x["Division"] == "E0"]
        x = pd.DataFrame({"home": x["HomeTeam"].map(data.team), "away": x["AwayTeam"].map(data.team),
                          "date_o": pd.to_datetime(x["MatchDate"]), "hg_o": x["FTHome"], "ag_o": x["FTAway"],
                          "b365_H_o": x["OddHome"], "elo_h": x["HomeElo"], "elo_a": x["AwayElo"]})
        j = _pair(m, x)
        # the compilation's "OddHome" is Bet365 in some seasons and the market average in others:
        # count a match as consistent if it equals either pre-match price in our primary file
        avg = pd.concat([pd.read_csv(CACHE / "fd" / f, encoding="utf-8-sig", usecols=lambda c: c in (
            "HomeTeam", "AwayTeam", "AvgH", "BbAvH")).assign(season=f[:4]) for f in sorted(
            p.name for p in (CACHE / "fd").glob("*_E0.csv"))], ignore_index=True)
        avg["avgh"] = avg.get("AvgH").fillna(avg.get("BbAvH")) if "BbAvH" in avg else avg["AvgH"]
        avg = avg.assign(home=avg["HomeTeam"].map(data.team), away=avg["AwayTeam"].map(data.team))
        avg["season"] = "20" + avg["season"].str[:2] + "-" + avg["season"].str[2:]
        j = j.merge(avg[["season", "home", "away", "avgh"]], on=["season", "home", "away"], how="left")
        ok = np.isclose(j["b365_H"], j["b365_H_o"], atol=0.011) | np.isclose(j["avgh"], j["b365_H_o"], atol=0.011)
        bad_odds = j[~ok]
        bad_sc = j[(j["hg"] != j["hg_o"]) | (j["ag"] != j["ag_o"])]
        lines.append(f"Bet365 pre-match home odds vs xgabora compilation: {len(j)} matched, "
                     f"{len(bad_odds)} match neither our Bet365 nor our market-average pre-match price (to 0.01); "
                     f"scores differ in {len(bad_sc)}.")
        stats["odds_xgabora_mismatch"] = len(bad_odds)
        for r in bad_odds.head(10).itertuples():
            lines.append(f"- {r.season} {r.home} v {r.away}: {r.b365_H} vs {r.b365_H_o}")
    except FileNotFoundError:
        lines.append("xgabora file missing; Bet365 cross-check skipped.")
    lines.append("Note: no second *independent* publisher of closing odds is reachable, so closing odds can only "
                 "be checked mirror-against-mirror (integrity of the copy), not against a different bookmaker feed.")

    # 3. red cards: football-data vs FPL player rows
    section("Red cards")
    p = data.load_fpl_players()
    rc = p.groupby(["season", "fixture", "was_home"])["red"].sum().unstack("was_home").reset_index()
    rc.columns = ["season", "fixture", "ar_o", "hr_o"]
    j = m.merge(rc, on=["season", "fixture"])
    bad = j[(j["hr"] != j["hr_o"]) | (j["ar"] != j["ar_o"])]
    lines.append(f"{len(j)} matches compared (FPL counts players only; football-data counts players too). "
                 f"Mismatching matches: {len(bad)} ({len(bad) / max(len(j), 1):.1%}).")
    stats["red_mismatch_rate"] = len(bad) / max(len(j), 1)

    # 4. xG providers
    section("xG providers")
    o = m.dropna(subset=["us_hxg", "opta_hxg"])
    a, b = np.r_[o["us_hxg"], o["us_axg"]], np.r_[o["opta_hxg"], o["opta_axg"]]
    lines.append(f"Understat vs Opta (FPL) team-match xG, {len(o)} matches: correlation {np.corrcoef(a, b)[0, 1]:.3f}, "
                 f"mean {a.mean():.3f} vs {b.mean():.3f} (Understat runs higher).")
    f = m.dropna(subset=["fd_hxg", "opta_hxg"])
    if len(f):
        a, b = np.r_[f["fd_hxg"], f["fd_axg"]], np.r_[f["opta_hxg"], f["opta_axg"]]
        lines.append(f"football-data xG vs Opta (FPL), {len(f)} matches of 2026-27: correlation "
                     f"{np.corrcoef(a, b)[0, 1]:.3f} (same underlying provider).")
    lines.append("xG source used per season: " + ", ".join(
        f"{s}: {dict(g['xg_src'].value_counts())}" for s, g in m.groupby("season") if g["xg_src"].ne("").any()))
    return lines, stats


def write_report(m: pd.DataFrame) -> dict:
    lines, stats = run(m)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "DATA_CHECKS.md").write_text("# Data cross-checks\n\nGenerated by `weekly.py`." + "\n".join(lines) + "\n")
    return stats
