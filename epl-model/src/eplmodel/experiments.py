"""Model selection under a strict protocol.

1. Tune each model's hyper-parameters on TUNE seasons only (walk-forward RPS).
2. Compare tuned models on TUNE, TEST_A and TEST_B against the margin-free closing market.
3. Blend models (weights fitted on TUNE).
4. Structural changes to the rating fit, and 5. factor adjustments fitted on TUNE.
   A blend, structural change or factor is kept only if its RPS gain is statistically clear on BOTH
   test periods: a paired bootstrap over match dates must put the one-sided 95% upper bound of the
   RPS change below zero in each period.
Every trial is appended to reports/experiment_log.csv and summarised in reports/EXPERIMENTS.md.
"""
from __future__ import annotations

import copy
import itertools
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import adjust, data, evaluate as ev, features, models
from .config import CACHE, CONFIG, LIVE, REPORTS, TEST_A, TEST_B, TUNE

PERIODS = {"TUNE": TUNE, "TEST_A": TEST_A, "TEST_B": TEST_B, "LIVE": LIVE}
LOG = []


def log(stage, name, desc, scores, decision="", note="", extra=None):
    rec = {"time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "stage": stage, "test": name,
           "description": desc, **{f"RPS_{k}": round(v, 5) for k, v in scores.items()}, **(extra or {}),
           "decision": decision, "note": note}
    LOG.append(rec)
    print(f"  [{stage}] {name:<34} " + " ".join(f"{k}={v:.5f}" for k, v in scores.items())
          + "".join(f" {k}={v}" for k, v in (extra or {}).items() if k.startswith("dRPS") and "upper" not in k)
          + f"  {decision} {note}", flush=True)


def period_rps(pred, m, periods=("TUNE", "TEST_A", "TEST_B")):
    p = ev.probs_from_pred(pred)
    out = {}
    for k in periods:
        idx = p.index[m.loc[p.index, "season"].isin(PERIODS[k])]
        if len(idx):
            out[k] = ev.rps(p.loc[idx, ["pH", "pD", "pA"]].to_numpy(), ev.outcome(m.loc[idx])).mean()
    return out


def make(spec):
    cls = {"RatingModel": models.RatingModel, "EloModel": models.EloModel}[spec["cls"]]
    return cls(**spec["params"])


def run_model(spec, m, start, end=None):
    mod = make(spec)
    if spec["cls"] == "EloModel":
        m = m.join(mod.run(m, data.promoted_teams(m)))
    return ev.walk_forward(mod, m, start, end)


BASE_SPECS = {
    "poisson": {"cls": "RatingModel", "params": {"name": "poisson", "target": "goals", "dc": False}},
    "dixon_coles": {"cls": "RatingModel", "params": {"name": "dixon_coles", "target": "goals", "dc": True}},
    "xg": {"cls": "RatingModel", "params": {"name": "xg", "target": "xg", "dc": True}},
    "xg_goals_mix": {"cls": "RatingModel", "params": {"name": "xg_goals_mix", "target": "mix", "dc": True}},
    "market": {"cls": "RatingModel", "params": {"name": "market", "target": "market", "dc": True}},
    "elo": {"cls": "EloModel", "params": {"name": "elo"}},
}
GRIDS = {
    "RatingModel": {"half_life": [90, 150, 240, 365, 540], "reg": [0.5, 1, 2, 4, 8],
                    "season_decay": [1.0, 0.85, 0.7, 0.5]},
    "EloModel": {"k": [10, 15, 20, 30, 40], "home": [40, 60, 80], "season_regress": [0.0, 0.15, 0.3, 0.5]},
}


def tune(name, spec, m):
    """Coordinate descent over the grid, scored on TUNE only."""
    tune_start, tune_end = "2018-07-01", "2022-06-30"
    grid = dict(GRIDS[spec["cls"]])
    if spec["params"].get("target") == "mix":
        grid["xg_weight"] = [0.3, 0.5, 0.7, 0.85]
    best = copy.deepcopy(spec)
    cache = {}

    def score(sp):
        key = json.dumps(sp["params"], sort_keys=True)
        if key not in cache:
            cache[key] = period_rps(run_model(sp, m, tune_start, tune_end), m, ("TUNE",))["TUNE"]
        return cache[key]

    best_s = score(best)
    for _ in range(2):
        changed = False
        for p, values in grid.items():
            for v in values:
                cand = copy.deepcopy(best)
                cand["params"][p] = v
                s = score(cand)
                if s < best_s - 1e-6:
                    best, best_s, changed = cand, s, True
        if not changed:
            break
    tuned = {k: v for k, v in best["params"].items() if k != "name"}
    log("1-tune", name, f"coordinate-descent tuning over {len(cache)} settings", {"TUNE": best_s},
        "tuned", json.dumps(tuned))
    return best


def blend(preds: dict, weights: dict, rho_from="dixon_coles"):
    names = [k for k, w in weights.items() if w > 0]
    idx = preds[names[0]].index
    for n in names[1:]:
        idx = idx.intersection(preds[n].index)
    lh = sum(weights[n] * np.log(preds[n].loc[idx, "lh"]) for n in names) / sum(weights[n] for n in names)
    la = sum(weights[n] * np.log(preds[n].loc[idx, "la"]) for n in names) / sum(weights[n] for n in names)
    return pd.DataFrame({"lh": np.exp(lh), "la": np.exp(la), "rho": preds[rho_from].loc[idx, "rho"]}, index=idx)


def tune_blend(preds, m, names, step=0.1):
    best, best_s = None, np.inf
    k = int(round(1 / step))
    for combo in itertools.product(range(k + 1), repeat=len(names)):
        if sum(combo) != k:
            continue
        w = {n: c * step for n, c in zip(names, combo)}
        s = period_rps(blend(preds, w), m, ("TUNE",))["TUNE"]
        if s < best_s:
            best, best_s = w, s
    return best, best_s


def market_pred(m):
    mp = m[["mH", "mD", "mA", "mOver"]].rename(columns={"mH": "pH", "mD": "pD", "mA": "pA", "mOver": "pOver"})
    g = models.score_grid(m["mkt_lh"].fillna(1.4).values, m["mkt_la"].fillna(1.1).values, -0.05)
    mk = models.grid_markets(g)
    mp["pBTTS"] = mk["pBTTS"]
    flat = g.reshape(len(g), -1).argmax(1)
    mp["ml_h"], mp["ml_a"] = flat // g.shape[2], flat % g.shape[2]
    mp["lh"], mp["la"] = m["mkt_lh"].values, m["mkt_la"].values
    return mp


def per_match_rps(pred, m, idx):
    p = ev.probs_from_pred(pred.loc[idx])
    return pd.Series(ev.rps(p[["pH", "pD", "pA"]].to_numpy(), ev.outcome(m.loc[idx])), index=idx)


def significance(new, ref, m, idx, n_boot=2000, seed=11):
    """Paired cluster bootstrap of the per-match RPS change (new - ref), resampling match dates.
    Returns (mean change, one-sided 95% upper bound, share of resamples with no improvement)."""
    d = per_match_rps(new, m, idx) - per_match_rps(ref, m, idx)
    g = d.groupby(m.loc[idx, "date"].values)
    sums, counts = g.sum().to_numpy(), g.size().to_numpy()
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(sums), (n_boot, len(sums)))
    boot = sums[pick].sum(1) / counts[pick].sum(1)
    return float(d.mean()), float(np.percentile(boot, 95)), float((boot >= 0).mean())


def judge(stage, name, desc, new, ref, m, periods=("TEST_A", "TEST_B"), idx_override=None, note=""):
    """Keep only if the RPS gain is significant (one-sided 95% bootstrap) on both test periods."""
    scores = period_rps(new, m)
    stats, ok = {}, True
    for k in periods:
        idx = idx_override[k] if idx_override else new.index[m.loc[new.index, "season"].isin(PERIODS[k])]
        idx = idx.intersection(ref.index)
        mean, hi, p = significance(new, ref, m, idx)
        stats[k] = (mean, hi, p)
        ok &= hi < 0
        if idx_override:
            scores[k] = per_match_rps(new, m, idx).mean()
    extra = {f"dRPS_{k}": round(v[0], 5) for k, v in stats.items()}
    extra |= {f"dRPS_{k}_upper95": round(v[1], 5) for k, v in stats.items()}
    extra |= {f"p_noimprove_{k}": round(v[2], 3) for k, v in stats.items()}
    raw_better = all(v[0] < 0 for v in stats.values())
    decision = "KEPT" if ok else ("dropped (gain within noise)" if raw_better else "dropped")
    log(stage, name, desc, scores, decision, note, extra)
    return ok


def run_all(m: pd.DataFrame, f: pd.DataFrame, quick=False, reuse_tuning=False):
    t0 = time.time()
    LOG.clear()
    start = "2018-07-01"
    print("Stage 1: tuning on", TUNE)
    specs, preds = {}, {}
    tuned_file = CACHE / "tuned_specs.json"
    cached = json.loads(tuned_file.read_text()) if reuse_tuning and tuned_file.exists() else {}
    for name, spec in BASE_SPECS.items():
        if name in cached:
            specs[name] = cached[name]
            log("1-tune", name, "tuned settings reused from previous run (deterministic)", {}, "tuned",
                json.dumps({k: v for k, v in cached[name]["params"].items() if k != "name"}))
        else:
            specs[name] = tune(name, spec, m) if not quick else spec
        preds[name] = run_model(specs[name], m, start)
    if not quick:
        tuned_file.write_text(json.dumps(specs, indent=1))
    # 2. comparison
    print("Stage 2: model comparison")
    mk = market_pred(m)
    for name in preds:
        log("2-compare", name, "tuned model, walk-forward", period_rps(preds[name], m))
    mrps = {k: ev.rps(mk.loc[m["season"].isin(v), ["pH", "pD", "pA"]].to_numpy(), ev.outcome(m[m["season"].isin(v)])).mean()
            for k, v in list(PERIODS.items())[:3]}
    log("2-compare", "closing_market", "margin-free closing odds (benchmark)", mrps)
    # 3. blends
    print("Stage 3: blends (weights fitted on TUNE)")
    cands = ["dixon_coles", "xg", "xg_goals_mix", "market", "elo"]
    single = {n: period_rps(preds[n], m) for n in cands}
    ref = min(cands, key=lambda n: single[n]["TUNE"])
    log("3-blend", f"best single model ({ref})", "reference for blending (best on TUNE)", single[ref], "baseline")
    current = {ref: 1.0}
    for combo in [("xg_goals_mix", "market"), ("xg_goals_mix", "market", "elo"), ("xg", "dixon_coles", "market"),
                  ("xg", "market", "elo"), ("xg_goals_mix", "dixon_coles", "market", "elo")]:
        w, _ = tune_blend(preds, m, list(combo))
        if judge("3-blend", "+".join(combo), "geometric blend of expected goals " + json.dumps(w), blend(preds, w),
                 blend(preds, current), m):
            current = w
    base = blend(preds, current)
    # 4. structural changes to the rating fit (re-run walk-forward for each blend component)
    print("Stage 4: structural tests")
    for name, change, desc in [
            ("no_crowd_home_adv", {"no_crowd": True}, "separate home advantage for matches without crowds (Jun 2020-May 2021)"),
            ("promoted_prior", {"promoted_prior": True}, "promoted clubs' ratings start at the historical promoted-club average"),
            ("red_card_downweight", {"red_weight": 0.5}, "matches with a red card count half in the rating fit (red cards as luck)")]:
        new_preds = dict(preds)
        changed = False
        for n in current:
            if specs[n]["cls"] == "RatingModel":
                sp = copy.deepcopy(specs[n])
                sp["params"].update(change)
                new_preds[n] = run_model(sp, m, start)
                changed = True
        if changed and judge("4-structural", name, desc, blend(new_preds, current), base, m):
            for n in current:
                if specs[n]["cls"] == "RatingModel":
                    specs[n]["params"].update(change)
            preds = new_preds
            base = blend(preds, current)
    # penalties as luck: non-penalty xG plus league-average penalty value, on the xG model (information only
    # if the xG model is not part of the selected blend)
    sp = copy.deepcopy(specs["xg"])
    sp["params"]["target"] = "npxg_pen"
    judge("4-structural", "npxg_plus_avg_penalties", "xG model rebuilt on non-penalty xG + average penalty value "
          "(penalties treated as luck); compared with the xG model", run_model(sp, m, start), preds["xg"], m,
          note="" if "xg" in current else "information only: the xG model is not in the selected blend")
    # 5. factors
    print("Stage 5: factors")
    promoted = data.promoted_teams(m)
    F = adjust.prepare(f, m, promoted)
    kept, kept_params = [], None
    tune_idx = base.index[m.loc[base.index, "season"].isin(TUNE)]
    current_pred = base

    order = ["draw_bias", "early_season", "promoted_early", "rest_days", "rest_diff", "euro_congestion", "manager_change",
             "derby", "motivation", "finishing_luck", "penalty_skill", "red_card_rate", "set_pieces", "form"]
    for name in order:
        spec = adjust.merge_specs(kept + [name])
        params = adjust.fit(F.loc[tune_idx], base.loc[tune_idx], m.loc[tune_idx], spec)
        new = adjust.apply(F.loc[base.index], base, params)
        k = len(adjust.FACTORS[name].get("goals", []))
        own = {"beta": [round(x, 4) for x in params["beta"][-k:]] if k else [],
               "delta": [round(x, 4) for x in params["delta"]]}
        if judge("5-factor", name, json.dumps(adjust.FACTORS[name]), new, current_pred, m,
                 note="coefficients " + json.dumps(own)):
            kept.append(name)
            kept_params, current_pred = params, new
    # lineup strength: data only from 2022-23, so fit on 2022-23 and judge on 2023-24 and TEST_B
    lu_fit = base.index[(m.loc[base.index, "season"] == "2022-23") & F.loc[base.index, "xi_rel_h"].notna()]
    params = adjust.fit(F.loc[lu_fit], current_pred.loc[lu_fit], m.loc[lu_fit], adjust.merge_specs(["lineup_strength"]))
    adj = adjust.apply(F.loc[base.index], current_pred, params)
    a_idx = base.index[m.loc[base.index, "season"] == "2023-24"]
    b_idx = base.index[m.loc[base.index, "season"].isin(TEST_B)]
    judge("5-factor", "lineup_strength", "starting-XI xG+xA value vs team norm; fitted on 2022-23 (first season with "
          "FPL starts), judged on 2023-24 and TEST_B; not usable live without a lineup feed", adj, current_pred, m,
          idx_override={"TEST_A": a_idx, "TEST_B": b_idx}, note="coefficients " + json.dumps(np.round(params["beta"], 4).tolist()))
    return {"specs": specs, "preds": preds, "blend": current, "factors": kept, "F": F,
            "elapsed": time.time() - t0}
