"""Production predictor: the selected blend + factor adjustments, fitted as of a given date."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import adjust, data, evaluate as ev, models
from .config import CONFIG

SPEC_FILE = CONFIG / "model_spec.json"


def load_spec() -> dict:
    return json.loads(SPEC_FILE.read_text())


def _ctx(m_played, fixtures, as_of, needs_prior):
    promoted = data.promoted_teams(pd.concat([m_played, fixtures]))
    season = data.season_of(as_of)
    return {"teams_now": set(fixtures["home"]) | set(fixtures["away"]), "new_teams": promoted.get(season, set()),
            "season_of_date": data.season_of,
            "promoted_prior": ev.promoted_prior(m_played, promoted, as_of) if needs_prior else None}


def fit_predict(spec: dict, m_played: pd.DataFrame, fixtures: pd.DataFrame, as_of: pd.Timestamp,
                F_fix: pd.DataFrame | None = None, with_factors=True) -> pd.DataFrame:
    """Expected goals (lh, la), rho and draw multiplier for `fixtures`, using only m_played with date < as_of."""
    tr = m_played[(m_played["date"] < as_of) & m_played["hg"].notna()]
    preds = {}
    for name, w in spec["blend"].items():
        ms = spec["models"][name]
        mod = models.RatingModel(**ms["params"]) if ms["cls"] == "RatingModel" else models.EloModel(**ms["params"])
        fx = fixtures
        trn = tr
        if ms["cls"] == "EloModel":
            allm = pd.concat([tr, fixtures]).sort_values(["date", "home"])
            ratings = mod.run(allm, data.promoted_teams(allm))
            trn = tr.join(ratings)
            fx = fixtures.join(ratings)
        mod.fit(trn, as_of, _ctx(tr, fixtures, as_of, getattr(mod, "promoted_prior", False)))
        lh, la, rho = mod.predict(fx)
        preds[name] = pd.DataFrame({"lh": lh, "la": la, "rho": rho}, index=fixtures.index)
    rho_model = spec["models"][spec["rho_from"]]
    if spec["rho_from"] not in preds:
        mod = models.RatingModel(**rho_model["params"])
        mod.fit(tr, as_of, _ctx(tr, fixtures, as_of, False))
        rho = mod.state["rho"]
    else:
        rho = preds[spec["rho_from"]]["rho"].iloc[0]
    wsum = sum(spec["blend"].values())
    lh = np.exp(sum(w * np.log(preds[n]["lh"]) for n, w in spec["blend"].items()) / wsum)
    la = np.exp(sum(w * np.log(preds[n]["la"]) for n, w in spec["blend"].items()) / wsum)
    out = pd.DataFrame({"lh": lh, "la": la, "rho": rho, "dmult": 1.0}, index=fixtures.index)
    if with_factors and spec.get("factor_params") and F_fix is not None:
        out = adjust.apply(F_fix.loc[fixtures.index], out, spec["factor_params"])
    return out


def match_outputs(pred: pd.DataFrame) -> pd.DataFrame:
    """Everything reported per match: xG, 1X2, O/U 2.5, BTTS, most likely score, top-5 scores, grid."""
    g = models.score_grid(pred["lh"].values, pred["la"].values, pred["rho"].values, pred["dmult"].values)
    mk = models.grid_markets(g)
    rows = []
    for k, idx in enumerate(pred.index):
        flat = g[k].ravel()
        order = np.argsort(-flat)[:5]
        top = [(int(o // g.shape[2]), int(o % g.shape[2]), float(flat[o])) for o in order]
        rows.append({"idx": idx, "xg_h": pred["lh"].iloc[k], "xg_a": pred["la"].iloc[k], "pH": mk["pH"][k],
                     "pD": mk["pD"][k], "pA": mk["pA"][k], "pOver25": mk["pOver"][k], "pBTTS": mk["pBTTS"][k],
                     "ml_score": f"{top[0][0]}-{top[0][1]}", "ml_pct": top[0][2],
                     "top5": ", ".join(f"{h}-{a} {p:.0%}" for h, a, p in top), "grid": g[k]})
    return pd.DataFrame(rows).set_index("idx")


def compact_grid(g: np.ndarray) -> np.ndarray:
    """11x11 grid -> 7x7 with the last row/column meaning '6+'."""
    out = np.zeros((7, 7))
    out[:6, :6] = g[:6, :6]
    out[6, :6] = g[6:, :6].sum(0)
    out[:6, 6] = g[:6, 6:].sum(1)
    out[6, 6] = g[6:, 6:].sum()
    return out
