"""Model selection under a strict protocol.

1. Tune each model's hyper-parameters on TUNE seasons only (walk-forward RPS).
2. Compare tuned models on TUNE, TEST_A and TEST_B against the margin-free closing market.
3. Blend models (weights fitted on TUNE).
4. Test each factor/structural change: fitted on TUNE, kept only if RPS improves on BOTH test periods.
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


def log(stage, name, desc, scores, decision="", note=""):
    rec = {"time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "stage": stage, "test": name,
           "description": desc, **{f"RPS_{k}": round(v, 5) for k, v in scores.items()}, "decision": decision,
           "note": note}
    LOG.append(rec)
    print(f"  [{stage}] {name:<34} " + " ".join(f"{k}={v:.5f}" for k, v in scores.items()) + f"  {decision} {note}")


def period_rps(pred, m, periods=("TUNE", "TEST_A", "TEST_B")):
    p = ev.probs_from_pred(pred)
    out = {}
    for k in periods:
        idx = p.index[m.loc[p.index, "season"].isin(PERIODS[k])]
        if len(idx):
            out[k] = ev.rps(p.loc[idx, ["pH", "pD", "pA"]].to_numpy(), ev.outcome(m.loc[idx])).mean()
    return out


def rps_on(pred, m, idx):
    p = ev.probs_from_pred(pred.loc[idx])
    return ev.rps(p[["pH", "pD", "pA"]].to_numpy(), ev.outcome(m.loc[idx])).mean()


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


def run_all(m: pd.DataFrame, f: pd.DataFrame, quick=False):
    t0 = time.time()
    LOG.clear()
    start = "2018-07-01"
    print("Stage 1: tuning on", TUNE)
    specs, preds = {}, {}
    for name, spec in BASE_SPECS.items():
        specs[name] = tune(name, spec, m) if not quick else spec
        preds[name] = run_model(specs[name], m, start)
        preds[name].to_pickle(CACHE / f"pred_{name}.pkl")
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
    best_blend, best_name, best_scores = None, None, None
    single = {n: period_rps(preds[n], m) for n in cands}
    ref = min(cands, key=lambda n: single[n]["TUNE"])
    log("3-blend", f"best single model ({ref})", "reference for blending", single[ref], "baseline")
    current, current_scores = {ref: 1.0}, single[ref]
    for combo in [("xg_goals_mix", "market"), ("xg_goals_mix", "market", "elo"), ("xg", "dixon_coles", "market"),
                  ("xg", "market", "elo"), ("xg_goals_mix", "dixon_coles", "market", "elo")]:
        w, _ = tune_blend(preds, m, list(combo))
        sc = period_rps(blend(preds, w), m)
        better = sc["TEST_A"] < current_scores["TEST_A"] and sc["TEST_B"] < current_scores["TEST_B"]
        log("3-blend", "+".join(combo), "geometric blend of expected goals " + json.dumps(w), sc,
            "KEPT" if better else "dropped", "beats current on both test periods" if better else "")
        if better:
            current, current_scores = w, sc
    base = blend(preds, current)
    # 4. factors
    print("Stage 4: factors")
    promoted = data.promoted_teams(m)
    F = adjust.prepare(f, m, promoted)
    kept, kept_params = [], None
    base_pred = base.copy()
    base_scores = current_scores

    tune_idx = base.index[m.loc[base.index, "season"].isin(TUNE)]

    def score_with(names, fit_idx):
        spec = adjust.merge_specs(names)
        params = adjust.fit(F.loc[fit_idx], base.loc[fit_idx], m.loc[fit_idx], spec)
        return params, period_rps(adjust.apply(F.loc[base.index], base, params), m)

    order = ["draw_bias", "early_season", "promoted_early", "rest_days", "rest_diff", "euro_congestion", "manager_change",
             "derby", "motivation", "finishing_luck", "penalty_skill", "red_card_rate", "set_pieces", "form"]
    for name in order:
        params, sc = score_with(kept + [name], tune_idx)
        better = sc["TEST_A"] < base_scores["TEST_A"] and sc["TEST_B"] < base_scores["TEST_B"]
        coefs = {"beta": [round(x, 4) for x in params["beta"]], "delta": [round(x, 4) for x in params["delta"]]}
        log("4-factor", name, json.dumps(adjust.FACTORS[name]), sc, "KEPT" if better else "dropped",
            json.dumps(coefs))
        if better:
            kept.append(name)
            kept_params, base_scores = params, sc
    # lineup strength: data only from 2022-23, so fit on 2022-23 and judge on 2023-24 and TEST_B
    ref_pred = adjust.apply(F.loc[base.index], base, kept_params) if kept_params else base
    lu_fit = base.index[(m.loc[base.index, "season"] == "2022-23") & F.loc[base.index, "xi_rel_h"].notna()]
    params = adjust.fit(F.loc[lu_fit], ref_pred.loc[lu_fit], m.loc[lu_fit], adjust.merge_specs(["lineup_strength"]))
    adj = adjust.apply(F.loc[base.index], ref_pred, params)
    a_idx = base.index[m.loc[base.index, "season"] == "2023-24"]
    b_idx = base.index[m.loc[base.index, "season"].isin(TEST_B)]
    sc_new = {"TEST_A(23-24)": rps_on(adj, m, a_idx), "TEST_B": rps_on(adj, m, b_idx)}
    sc_old = {"TEST_A(23-24)": rps_on(ref_pred, m, a_idx), "TEST_B": rps_on(ref_pred, m, b_idx)}
    better = all(sc_new[k] < sc_old[k] for k in sc_new)
    log("4-factor", "lineup_strength", "starting-XI xG+xA value vs team norm; fitted on 2022-23 (first season "
        "with FPL starts)", sc_new, "KEPT" if better else "dropped",
        f"reference {json.dumps({k: round(v, 5) for k, v in sc_old.items()})}; beta={np.round(params['beta'], 4).tolist()}")
    if better:
        kept.append("lineup_strength")
    return {"specs": specs, "preds": preds, "blend": current, "factors": kept, "base_scores": base_scores,
            "elapsed": time.time() - t0}
