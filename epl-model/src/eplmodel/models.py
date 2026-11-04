"""Rating models.

Every model maps a match to (lambda_home, lambda_away, rho): the expected goals of each side plus a
Dixon-Coles low-score correlation. A full scoreline grid follows from those three numbers.

* RatingModel  - time-decayed attack/defence ratings fitted by weighted Poisson maximum likelihood.
                 The target can be goals (Poisson / Dixon-Coles), xG, a goals/xG mix, or the expected
                 goals implied by past closing odds (the market-based rating).
* EloModel     - goal-difference Elo; rating gap mapped to expected goals by a Poisson regression.
* Blend        - geometric blend of several models' expected goals.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import MAX_GOALS, NO_CROWD_END, NO_CROWD_START

G = np.arange(MAX_GOALS + 1)
_LOGFACT = np.array([math.lgamma(k + 1) for k in G])


# --------------------------------------------------------------------------------------------
# Scoreline grids
# --------------------------------------------------------------------------------------------
def poisson_pmf(lam):
    lam = np.asarray(lam, float)[..., None]
    return np.exp(G * np.log(np.maximum(lam, 1e-9)) - lam - _LOGFACT)


def dc_tau(lh, la, rho):
    """Dixon-Coles adjustment factors for 0-0, 0-1, 1-0, 1-1."""
    return 1 - lh * la * rho, 1 + lh * rho, 1 + la * rho, 1 - rho


def score_grid(lh, la, rho=0.0, dmult=None):
    """Array (n, 11, 11): P(home goals = i, away goals = j). dmult optionally scales the draw cells
    (fitted draw adjustments)."""
    lh, la = np.atleast_1d(lh).astype(float), np.atleast_1d(la).astype(float)
    rho = np.broadcast_to(np.asarray(rho, float), lh.shape)
    g = poisson_pmf(lh)[:, :, None] * poisson_pmf(la)[:, None, :]
    t00, t01, t10, t11 = dc_tau(lh, la, rho)
    g[:, 0, 0] *= t00
    g[:, 0, 1] *= t01
    g[:, 1, 0] *= t10
    g[:, 1, 1] *= t11
    g = np.clip(g, 0, None)
    if dmult is not None:
        d = np.arange(g.shape[1])
        g[:, d, d] *= np.asarray(dmult, float)[:, None]
    return g / g.sum(axis=(1, 2), keepdims=True)


_I, _J = np.meshgrid(G, G, indexing="ij")


def grid_markets(g):
    """Derived market probabilities from scoreline grids."""
    return {
        "pH": (g * (_I > _J)).sum((1, 2)), "pD": (g * (_I == _J)).sum((1, 2)), "pA": (g * (_I < _J)).sum((1, 2)),
        "pOver": (g * ((_I + _J) > 2.5)).sum((1, 2)), "pBTTS": (g * ((_I > 0) & (_J > 0))).sum((1, 2)),
    }


# --------------------------------------------------------------------------------------------
# Odds -> probabilities and market-implied expected goals
# --------------------------------------------------------------------------------------------
def devig(odds: np.ndarray) -> np.ndarray:
    """Remove the bookmaker margin with the power method: p_i = (1/o_i)^k with sum p = 1.
    Handles favourite-longshot bias better than simple normalisation. odds: (n, k)."""
    inv = 1.0 / np.asarray(odds, float)
    lo, hi = np.full(len(inv), 0.5), np.full(len(inv), 2.0)
    for _ in range(60):
        k = (lo + hi) / 2
        s = (inv ** k[:, None]).sum(1)
        lo = np.where(s > 1, k, lo)
        hi = np.where(s > 1, hi, k)
    return inv ** ((lo + hi) / 2)[:, None]


def implied_lambdas(pH, pA, pOver, rho=-0.05, iters=40):
    """Solve for (lambda_h, lambda_a) whose Dixon-Coles grid best matches market P(H), P(A), P(over 2.5)
    in least squares (vectorised Gauss-Newton with numeric Jacobian)."""
    n = len(pH)
    x = np.log(np.c_[np.full(n, 1.45), np.full(n, 1.15)])
    target = np.c_[pH, pA, pOver]
    use_ou = ~np.isnan(pOver)
    target = np.where(np.isnan(target), 0, target)

    def resid(x):
        m = grid_markets(score_grid(np.exp(x[:, 0]), np.exp(x[:, 1]), rho))
        r = np.c_[m["pH"], m["pA"], m["pOver"]] - target
        r[:, 2] *= use_ou
        return r

    for _ in range(iters):
        r = resid(x)
        J = np.empty((n, 3, 2))
        for k in range(2):
            dx = np.zeros_like(x)
            dx[:, k] = 1e-4
            J[:, :, k] = (resid(x + dx) - r) / 1e-4
        JTJ = np.einsum("nik,nil->nkl", J, J) + 1e-9 * np.eye(2)
        step = np.linalg.solve(JTJ, np.einsum("nik,ni->nk", J, r)[..., None])[..., 0]
        x = x - np.clip(step, -0.5, 0.5)
        if np.abs(step).max() < 1e-7:
            break
    return np.exp(x[:, 0]), np.exp(x[:, 1])


def market_probs(m: pd.DataFrame, prefix="c_") -> pd.DataFrame:
    """Margin-free closing probabilities for 1X2 and over 2.5."""
    out = pd.DataFrame(index=m.index)
    o = m[[f"{prefix}H", f"{prefix}D", f"{prefix}A"]].to_numpy(float)
    ok = np.isfinite(o).all(1) & (o > 1).all(1)
    p = np.full(o.shape, np.nan)
    p[ok] = devig(o[ok])
    out["mH"], out["mD"], out["mA"] = p.T
    ou = m[["c_over", "c_under"]].to_numpy(float)
    ok = np.isfinite(ou).all(1) & (ou > 1).all(1)
    q = np.full(ou.shape, np.nan)
    q[ok] = devig(ou[ok])
    out["mOver"] = q[:, 0]
    pre = m[["pre_over", "pre_under"]].to_numpy(float)
    ok = np.isfinite(pre).all(1) & (pre > 1).all(1)
    q2 = np.full(pre.shape, np.nan)
    q2[ok] = devig(pre[ok])
    out["mOver_any"] = out["mOver"].fillna(pd.Series(q2[:, 0], index=m.index))
    return out


def add_market_lambdas(m: pd.DataFrame) -> pd.DataFrame:
    """Columns mkt_lh / mkt_la: expected goals implied by closing 1X2 + over/under 2.5 odds
    (pre-closing O/U before 2019-20, when closing O/U was not published)."""
    mp = market_probs(m)
    m = m.join(mp)
    ok = mp[["mH", "mA", "mOver_any"]].notna().all(1)
    lh, la = implied_lambdas(mp.loc[ok, "mH"].values, mp.loc[ok, "mA"].values, mp.loc[ok, "mOver_any"].values)
    m["mkt_lh"], m["mkt_la"] = np.nan, np.nan
    m.loc[ok, "mkt_lh"], m.loc[ok, "mkt_la"] = lh, la
    return m


# --------------------------------------------------------------------------------------------
# Weighted Poisson rating engine
# --------------------------------------------------------------------------------------------
def fit_ratings(hi, ai, yh, ya, w, n_teams, reg, prior_a=None, prior_d=None, Zh=None, Za=None, theta0=None,
                iters=25):
    """Maximise sum w*[y*eta - exp(eta)] - reg/2*|ratings - prior|^2 with
    eta_home = mu + home + att[h] - def[a] + Zh@beta,  eta_away = mu + att[a] - def[h] + Za@beta.
    Returns theta = [mu, home, att(n), def(n), beta(k)] and fitted lambdas."""
    n = len(hi)
    k = 0 if Zh is None else Zh.shape[1]
    P = 2 + 2 * n_teams + k
    Xh = np.zeros((n, P))
    Xa = np.zeros((n, P))
    r = np.arange(n)
    Xh[:, 0] = Xa[:, 0] = 1
    Xh[:, 1] = 1
    Xh[r, 2 + hi] = 1
    Xh[r, 2 + n_teams + ai] = -1
    Xa[r, 2 + ai] = 1
    Xa[r, 2 + n_teams + hi] = -1
    if k:
        Xh[:, 2 + 2 * n_teams:] = Zh
        Xa[:, 2 + 2 * n_teams:] = Za
    X = np.vstack([Xh, Xa])
    y = np.r_[yh, ya]
    ww = np.r_[w, w]
    prior = np.zeros(P)
    if prior_a is not None:
        prior[2:2 + n_teams] = prior_a
        prior[2 + n_teams:2 + 2 * n_teams] = prior_d
    R = np.zeros(P)
    R[2:2 + 2 * n_teams] = reg
    R[2 + 2 * n_teams:] = 1e-3
    theta = prior.copy() if theta0 is None else theta0.copy()
    if theta0 is None:
        theta[0] = np.log(max((ww * y).sum() / ww.sum(), 0.1))
    for _ in range(iters):
        eta = X @ theta
        lam = np.exp(eta)
        g = X.T @ (ww * (y - lam)) - R * (theta - prior)
        H = (X * (ww * lam)[:, None]).T @ X + np.diag(R + 1e-9)
        step = np.linalg.solve(H, g)
        theta += step
        if np.abs(step).max() < 1e-6:
            break
    lam = np.exp(X @ theta)
    return theta, lam[:n], lam[n:]


def fit_rho(yh, ya, lh, la, w):
    """Dixon-Coles rho by weighted maximum likelihood on a grid (given fitted lambdas)."""
    low = (yh <= 1) & (ya <= 1)
    if low.sum() < 30:
        return 0.0
    yh, ya, lh, la, w = yh[low], ya[low], lh[low], la[low], w[low]
    best, best_ll = 0.0, -np.inf
    for rho in np.arange(-0.30, 0.151, 0.005):
        t00, t01, t10, t11 = dc_tau(lh, la, rho)
        tau = np.select([(yh == 0) & (ya == 0), (yh == 0) & (ya == 1), (yh == 1) & (ya == 0)], [t00, t01, t10], t11)
        if (tau <= 0).any():
            continue
        ll = (w * np.log(tau)).sum()
        if ll > best_ll:
            best, best_ll = rho, ll
    return best


@dataclass
class RatingModel:
    """Time-decayed attack/defence model.

    target: 'goals' | 'xg' | 'mix' | 'market' | 'npxg_pen'
    half_life: days for match weights to halve.  season_decay: extra multiplier per season boundary
    (summer transfers make old seasons less relevant).  reg: ridge strength pulling ratings to prior.
    dc: fit Dixon-Coles rho.  xg_weight: share of xG in the target when target='mix'.
    no_crowd: separate home-advantage term for matches played without crowds.
    promoted_prior: prior (attack, defence) for teams new to the league, learned walk-forward.
    red_weight: weight multiplier for training matches that had a red card.
    """
    name: str = "poisson"
    target: str = "goals"
    half_life: float = 240.0
    season_decay: float = 1.0
    reg: float = 2.0
    dc: bool = True
    xg_weight: float = 0.6
    no_crowd: bool = False
    promoted_prior: bool = False
    red_weight: float = 1.0
    window_days: int = 1500
    _theta: dict = field(default_factory=dict, repr=False)

    def _targets(self, tr):
        g_h, g_a = tr["hg"].to_numpy(float), tr["ag"].to_numpy(float)
        if self.target == "goals":
            return g_h, g_a
        if self.target == "market":
            ok = tr["mkt_lh"].notna().to_numpy()
            return np.where(ok, tr["mkt_lh"], g_h), np.where(ok, tr["mkt_la"], g_a)
        # provider-specific xG scaling to goal level, from training data only (walk-forward safe)
        xh, xa = tr["hxg"].to_numpy(float).copy(), tr["axg"].to_numpy(float).copy()
        if self.target == "npxg_pen":
            # non-penalty xG plus the league-average penalty value: treats penalties as luck
            ok = tr["us_hnpxg"].notna().to_numpy()
            xh = np.where(ok, tr["us_hnpxg"] + 0.105, xh)
            xa = np.where(ok, tr["us_anpxg"] + 0.085, xa)
        src = tr["xg_src"].to_numpy()
        for s in np.unique(src[src != ""]):
            mm = src == s
            k = (g_h[mm].sum() + g_a[mm].sum()) / max(xh[mm].sum() + xa[mm].sum(), 1e-9)
            xh[mm] *= k
            xa[mm] *= k
        has = ~np.isnan(xh)
        wx = 1.0 if self.target in ("xg", "npxg_pen") else self.xg_weight
        return np.where(has, wx * xh + (1 - wx) * g_h, g_h), np.where(has, wx * xa + (1 - wx) * g_a, g_a)

    def _zh(self, df):
        if not self.no_crowd:
            return None, None
        nc = ((df["date"] >= NO_CROWD_START) & (df["date"] <= NO_CROWD_END)).to_numpy(float)
        return nc[:, None], np.zeros((len(df), 1))

    def fit(self, tr: pd.DataFrame, as_of: pd.Timestamp, ctx: dict):
        tr = tr[tr["date"] >= as_of - pd.Timedelta(days=self.window_days)]
        age = (as_of - tr["date"]).dt.days.to_numpy(float)
        w = 0.5 ** (age / self.half_life)
        if self.season_decay != 1.0:
            cur = ctx["season_of_date"](as_of)
            n_back = (int(cur[:4]) - tr["season"].str[:4].astype(int)).to_numpy()
            w = w * self.season_decay ** n_back
        if self.red_weight != 1.0:
            w = w * np.where((tr["hr"] + tr["ar"]).to_numpy() > 0, self.red_weight, 1.0)
        teams = sorted(set(tr["home"]) | set(tr["away"]) | ctx["teams_now"])
        idx = {t: i for i, t in enumerate(teams)}
        hi, ai = tr["home"].map(idx).to_numpy(), tr["away"].map(idx).to_numpy()
        yh, ya = self._targets(tr)
        pa = pdf = None
        if self.promoted_prior and ctx.get("promoted_prior") is not None:
            pa = np.array([ctx["promoted_prior"][0] if t in ctx["new_teams"] else 0.0 for t in teams])
            pdf = np.array([ctx["promoted_prior"][1] if t in ctx["new_teams"] else 0.0 for t in teams])
        Zh, Za = self._zh(tr)
        prev = self._theta.get("theta")
        theta0 = None
        if prev is not None and prev[1] == teams:
            theta0 = prev[0]
        theta, lh, la = fit_ratings(hi, ai, yh, ya, w, len(teams), self.reg, pa, pdf, Zh, Za, theta0)
        self._theta["theta"] = (theta, teams)
        rho = 0.0
        if self.dc:
            rho = fit_rho(tr["hg"].to_numpy(), tr["ag"].to_numpy(), lh, la, w)
        n = len(teams)
        self.state = {"mu": theta[0], "home": theta[1], "att": dict(zip(teams, theta[2:2 + n])),
                      "def": dict(zip(teams, theta[2 + n:2 + 2 * n])), "beta": theta[2 + 2 * n:], "rho": rho}
        return self

    def predict(self, df: pd.DataFrame):
        s = self.state
        att = df["home"].map(s["att"]).fillna(0).to_numpy(), df["away"].map(s["att"]).fillna(0).to_numpy()
        dfn = df["home"].map(s["def"]).fillna(0).to_numpy(), df["away"].map(s["def"]).fillna(0).to_numpy()
        eh = s["mu"] + s["home"] + att[0] - dfn[1]
        ea = s["mu"] + att[1] - dfn[0]
        Zh, Za = self._zh(df)
        if Zh is not None:
            eh = eh + Zh @ s["beta"]
        return np.exp(eh), np.exp(ea), np.full(len(df), s["rho"])


# --------------------------------------------------------------------------------------------
# Elo
# --------------------------------------------------------------------------------------------
@dataclass
class EloModel:
    """Goal-difference Elo (World-Football-Elo style). The pre-match rating gap is mapped to expected
    goals with a time-weighted Poisson regression fitted on past matches only."""
    name: str = "elo"
    k: float = 20.0
    home: float = 60.0
    season_regress: float = 0.2
    map_half_life: float = 730.0

    def run(self, m: pd.DataFrame, promoted: dict) -> pd.DataFrame:
        """Sequential pass: returns pre-match ratings for every match (no look-ahead by construction)."""
        r = {}
        out_h, out_a = np.empty(len(m)), np.empty(len(m))
        season = None
        for i, row in enumerate(m[["season", "home", "away", "hg", "ag"]].itertuples(index=False)):
            if row.season != season:
                season = row.season
                if r:
                    mean = np.mean(list(r.values()))
                    for t in r:
                        r[t] = r[t] * (1 - self.season_regress) + mean * self.season_regress
                    # promoted clubs start at the average of the clubs they replace (last season's bottom 3)
                    if season in promoted:
                        bottom = sorted(r.values())[:3]
                        for t in promoted[season]:
                            r[t] = float(np.mean(bottom))
            rh, ra = r.setdefault(row.home, 1500.0), r.setdefault(row.away, 1500.0)
            out_h[i], out_a[i] = rh, ra
            if pd.isna(row.hg):  # future fixture: record current ratings, no update
                continue
            e = 1 / (1 + 10 ** (-(rh + self.home - ra) / 400))
            s = 1.0 if row.hg > row.ag else 0.5 if row.hg == row.ag else 0.0
            gd = abs(row.hg - row.ag)
            mult = 1 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
            delta = self.k * mult * (s - e)
            r[row.home] = rh + delta
            r[row.away] = ra - delta
        self.final = r
        return pd.DataFrame({"elo_h": out_h, "elo_a": out_a}, index=m.index)

    def fit(self, tr, as_of, ctx):
        tr = tr[tr["date"] >= as_of - pd.Timedelta(days=4 * self.map_half_life)]
        w = 0.5 ** ((as_of - tr["date"]).dt.days.to_numpy(float) / self.map_half_life)
        dr = ((tr["elo_h"] + self.home - tr["elo_a"]) / 400).to_numpy()
        X = np.c_[np.ones_like(dr), dr]
        self.coef = []
        for y, sgn in ((tr["hg"].to_numpy(float), 1), (tr["ag"].to_numpy(float), -1)):
            b = np.array([np.log(y.mean() + 1e-9), 0.0])
            Xs = X * np.array([1, sgn])
            for _ in range(20):
                lam = np.exp(Xs @ b)
                step = np.linalg.solve((Xs * (w * lam)[:, None]).T @ Xs + 1e-6 * np.eye(2), Xs.T @ (w * (y - lam)))
                b += step
                if np.abs(step).max() < 1e-8:
                    break
            self.coef.append((b, sgn))
        self.rho = ctx.get("rho", -0.05)
        return self

    def predict(self, df):
        dr = ((df["elo_h"] + self.home - df["elo_a"]) / 400).to_numpy()
        (bh, sh), (ba, sa) = self.coef
        return np.exp(bh[0] + sh * bh[1] * dr), np.exp(ba[0] + sa * ba[1] * dr), np.full(len(df), self.rho)
