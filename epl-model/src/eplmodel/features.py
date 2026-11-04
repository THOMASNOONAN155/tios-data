"""Pre-kickoff match features for the factor tests. Every feature uses only information that was
available before kickoff (fixture lists, earlier results, managers already appointed, lineups that
are announced before kickoff)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from .config import CONFIG


def _side_frame(m):
    """Long format: one row per team per EPL match."""
    h = pd.DataFrame({"idx": m.index, "date": m["date"], "team": m["home"], "home": 1})
    a = pd.DataFrame({"idx": m.index, "date": m["date"], "team": m["away"], "home": 0})
    return pd.concat([h, a], ignore_index=True)


def rest_and_congestion(m: pd.DataFrame, euro: pd.DataFrame) -> pd.DataFrame:
    """Days since each side's previous match (Premier League or UEFA), and whether it has a UEFA match
    within 3 days before or 4 days after (fixture lists are published in advance)."""
    s = _side_frame(m)
    allm = pd.concat([s[["team", "date"]], euro[["team", "date"]]]).drop_duplicates().sort_values("date")
    out = {}
    for t, g in s.groupby("team"):
        dates = np.sort(allm.loc[allm["team"] == t, "date"].to_numpy())
        ed = np.sort(euro.loc[euro["team"] == t, "date"].to_numpy()) if len(euro) else np.array([], "datetime64[ns]")
        d = g["date"].to_numpy()
        pos = np.searchsorted(dates, d, side="left")
        prev = np.where(pos > 0, dates[np.maximum(pos - 1, 0)], np.datetime64("NaT"))
        rest = (d - prev) / np.timedelta64(1, "D")
        if len(ed):
            pe = np.searchsorted(ed, d, side="left")
            prev_e = np.where(pe > 0, ed[np.maximum(pe - 1, 0)], np.datetime64("NaT"))
            next_e = np.where(np.searchsorted(ed, d, side="right") < len(ed),
                              ed[np.minimum(np.searchsorted(ed, d, side="right"), len(ed) - 1)], np.datetime64("NaT"))
            e_before = ((d - prev_e) / np.timedelta64(1, "D")) <= 3
            e_after = ((next_e - d) / np.timedelta64(1, "D")) <= 4
        else:
            e_before = e_after = np.zeros(len(d), bool)
        for i, idx in enumerate(g["idx"]):
            out[(idx, g["home"].iloc[i])] = (rest[i], bool(e_before[i]), bool(e_after[i]))
    f = pd.DataFrame(index=m.index)
    for side, flag in (("h", 1), ("a", 0)):
        vals = [out[(i, flag)] for i in m.index]
        r = np.array([v[0] for v in vals], float)
        f[f"rest_{side}"] = np.clip(np.nan_to_num(r, nan=14), 2, 14)
        f[f"euro_before_{side}"] = [v[1] for v in vals]
        f[f"euro_after_{side}"] = [v[2] for v in vals]
    f["short_rest_h"] = (f["rest_h"] <= 3).astype(float)
    f["short_rest_a"] = (f["rest_a"] <= 3).astype(float)
    f["rest_diff"] = np.clip(f["rest_h"] - f["rest_a"], -5, 5)
    return f


def manager_features(m: pd.DataFrame, mgr: pd.DataFrame) -> pd.DataFrame:
    """Days the current manager (incl. caretakers) had been in post; flags a change in the last 60 days."""
    f = pd.DataFrame(index=m.index)
    mgr = mgr.sort_values("start")
    first_spell = mgr.groupby("team")["start"].transform("min")
    mgr = mgr.assign(is_first=mgr["start"] == first_spell)
    for side, col in (("h", "home"), ("a", "away")):
        days = np.full(len(m), np.nan)
        new = np.zeros(len(m))
        for t, g in m.groupby(col):
            sp = mgr[mgr["team"] == t]
            if sp.empty:
                continue
            starts = sp["start"].to_numpy()
            pos = np.searchsorted(starts, g["date"].to_numpy(), side="right") - 1
            ok = pos >= 0
            ii = m.index.get_indexer(g.index)
            dd = (g["date"].to_numpy() - starts[np.maximum(pos, 0)]) / np.timedelta64(1, "D")
            # the spell must still be running on the match date (dataset ends Aug 2026)
            ends = sp["end"].to_numpy()[np.maximum(pos, 0)]
            ok &= g["date"].to_numpy() <= ends + np.timedelta64(1, "D")
            days[ii[ok]] = dd[ok]
            new[ii[ok]] = ((dd <= 60) & ~sp["is_first"].to_numpy()[np.maximum(pos, 0)])[ok]
        f[f"mgr_days_{side}"] = days
        f[f"new_mgr_{side}"] = new
    return f


def derby_flags(m: pd.DataFrame) -> pd.Series:
    d = pd.read_csv(CONFIG / "derbies.csv")
    pairs = {frozenset(p) for p in zip(d["team_a"], d["team_b"])}
    london = set(pd.read_csv(CONFIG / "london_clubs.csv")["team"])
    return pd.Series([float(frozenset((h, a)) in pairs or (h in london and a in london))
                      for h, a in zip(m["home"], m["away"])], index=m.index)


def table_state(m: pd.DataFrame) -> pd.DataFrame:
    """Pre-match league position, points and what is still mathematically at stake for each side."""
    adj = pd.read_csv(CONFIG / "points_adjustments.csv")
    f = pd.DataFrame(index=m.index, columns=["pos_h", "pos_a", "ntp_h", "ntp_a", "stake_h", "stake_a"], dtype=float)
    for s, g in m.groupby("season"):
        teams = sorted(set(g["home"]) | set(g["away"]))
        pts = dict.fromkeys(teams, 0)
        gd = dict.fromkeys(teams, 0)
        played = dict.fromkeys(teams, 0)
        for d, day in g.groupby("date", sort=True):
            # deductions are applied from the season's start (announcement dates vary; small effect)
            table = {t: pts[t] + adj.loc[(adj["season"] == s) & (adj["team"] == t), "points"].sum() for t in teams}
            order = sorted(teams, key=lambda t: (-table[t], -gd[t]))
            rank = {t: i + 1 for i, t in enumerate(order)}
            P = np.array([table[t] for t in order], float)
            R = np.array([38 - played[t] for t in order], float)
            for idx, row in day.iterrows():
                for side, t in (("h", row["home"]), ("a", row["away"])):
                    p, r = table[t], 38 - played[t]
                    title_alive = p + 3 * r >= P[0]
                    europe_alive = p + 3 * r >= P[6]
                    # safe: cannot be caught by the club in 18th even if it wins all its games
                    safe = p > P[17] + 3 * R[17] if rank[t] <= 17 else False
                    doomed = p + 3 * r < P[16]
                    ntp = (not title_alive and not europe_alive and safe) or doomed
                    f.at[idx, f"pos_{side}"] = rank[t]
                    f.at[idx, f"ntp_{side}"] = float(ntp and r <= 10)
                    f.at[idx, f"stake_{side}"] = float(r <= 10 and not ntp)
            for _, row in day.iterrows():
                h, a, hg, ag = row["home"], row["away"], row["hg"], row["ag"]
                if pd.isna(hg):
                    continue
                played[h] += 1
                played[a] += 1
                gd[h] += hg - ag
                gd[a] += ag - hg
                pts[h] += 3 if hg > ag else 1 if hg == ag else 0
                pts[a] += 3 if ag > hg else 1 if hg == ag else 0
    return f


def rolling_team_stats(m: pd.DataFrame, n=19) -> pd.DataFrame:
    """Per side, over its previous n league matches (strictly before kickoff): finishing luck
    (goals - xG), corners for/against (set-piece proxy), penalties won, red cards, and recent
    xG difference (form)."""
    rows = []
    for idx, r in m.iterrows():
        rows.append((idx, r["date"], r["home"], r["hg"], r["ag"], r["hxg"], r["axg"], r["hc"], r["ac"], r["hpen"], r["hr"],
                     r["ar"]))
        rows.append((idx, r["date"], r["away"], r["ag"], r["hg"], r["axg"], r["hxg"], r["ac"], r["hc"], r["apen"], r["ar"],
                     r["hr"]))
    s = pd.DataFrame(rows, columns=["idx", "date", "team", "gf", "ga", "xgf", "xga", "cf", "ca", "pen", "red", "red_opp"])
    s = s.sort_values(["team", "date"])
    g = s.groupby("team")
    shift = lambda c, k=n: g[c].transform(lambda x: x.shift(1).rolling(k, min_periods=5).mean())
    s["fin_luck"] = shift("gf") - shift("xgf")
    s["def_luck"] = shift("ga") - shift("xga")
    s["corner_diff"] = shift("cf") - shift("ca")
    s["pen_rate"] = shift("pen", 38)
    s["red_rate"] = shift("red", 38)
    s["form_xgd5"] = shift("xgf", 5) - shift("xga", 5)
    s["long_xgd"] = shift("xgf", 38) - shift("xga", 38)
    out = pd.DataFrame(index=m.index)
    for side, flag in (("h", m["home"]), ("a", m["away"])):
        sub = s.merge(pd.DataFrame({"idx": m.index, "team": flag.values}), on=["idx", "team"]).set_index("idx")
        for c in ["fin_luck", "def_luck", "corner_diff", "pen_rate", "red_rate", "form_xgd5", "long_xgd"]:
            out[f"{c}_{side}"] = sub[c].reindex(m.index)
    return out


def lineup_strength(m: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Starting-XI strength vs the side's recent norm (seasons with FPL 'starts', 2022-23 onwards).
    Player attacking value = shrunk xG+xA per 90 over his previous 20 appearances; the XI's sum is
    compared with the team's average XI over its previous 10 matches. Lineups are public ~75 minutes
    before kickoff, so this is pre-kickoff information."""
    p = p.dropna(subset=["starts", "xg"]).copy()
    p = p[p["minutes"] > 0].sort_values("date")
    p["xgi"] = p["xg"].astype(float) + p["xa"].astype(float)
    g = p.groupby("element")
    prev_xgi = g["xgi"].transform(lambda x: x.shift(1).rolling(20, min_periods=1).sum()).fillna(0)
    prev_min = g["minutes"].transform(lambda x: x.shift(1).rolling(20, min_periods=1).sum()).fillna(0)
    pos_mean = p.groupby("position")["xgi"].sum() / p.groupby("position")["minutes"].sum() * 90
    prior = p["position"].map(pos_mean).fillna(pos_mean.mean())
    p["value"] = (prev_xgi + prior * 3) / (prev_min + 270) * 90
    xi = p[p["starts"] == 1].groupby(["season", "fixture", "team"])["value"].sum().rename("xi_value").reset_index()
    xi = xi.sort_values(["team", "season", "fixture"])
    xi = xi.merge(p[["season", "fixture", "date"]].drop_duplicates(["season", "fixture"]), on=["season", "fixture"])
    xi = xi.sort_values(["team", "date"])
    xi["norm"] = xi.groupby("team")["xi_value"].transform(lambda x: x.shift(1).rolling(10, min_periods=3).mean())
    xi["xi_rel"] = np.log(xi["xi_value"] / xi["norm"])
    out = pd.DataFrame(index=m.index)
    for side, col in (("h", "home"), ("a", "away")):
        j = m.reset_index()[["index", "season", "fixture", col]].merge(
            xi.rename(columns={"team": col}), on=["season", "fixture", col], how="left").set_index("index")
        out[f"xi_rel_{side}"] = j["xi_rel"].reindex(m.index).clip(-0.6, 0.6)
    return out


def build(m: pd.DataFrame) -> pd.DataFrame:
    euro = data.load_european()
    f = rest_and_congestion(m, euro)
    f = f.join(manager_features(m, data.load_managers()))
    f["derby"] = derby_flags(m)
    f = f.join(table_state(m))
    f = f.join(rolling_team_stats(m))
    f = f.join(lineup_strength(m, data.load_fpl_players()))
    f["gw"] = m["gw"]
    return f
