"""Evaluation: margin error, straight-up picks, against-the-spread vs closing line, probability quality, weekly consistency."""
import numpy as np, pandas as pd
from scipy.stats import norm


def no_vig_prob(home_ml, away_ml):
    """Home win probability implied by closing moneylines, vig removed proportionally."""
    def imp(ml):
        return np.where(ml < 0, -ml / (-ml + 100.0), 100.0 / (ml + 100.0))
    ph, pa = imp(np.asarray(home_ml, float)), imp(np.asarray(away_ml, float))
    return ph / (ph + pa)


def evaluate(df, pred='pred', prob='prob'):
    """df needs: result (home margin), spread_line (home favoured +), pred, prob, season, week."""
    d = df[df.result.notna() & df[pred].notna()].copy()
    y = d.result.values; p = d[pred].values; L = d.spread_line.values
    out = {'games': len(d)}
    out['MAE'] = np.mean(np.abs(p - y)); out['RMSE'] = np.sqrt(np.mean((p - y) ** 2))
    nt = y != 0
    out['SU_acc'] = np.mean((np.sign(p[nt]) == np.sign(y[nt])) | ((p[nt] == 0) & False))
    # against the spread: side the model prefers vs the closing line
    edge = p - L; cov = y - L
    m = (edge != 0) & (cov != 0)
    w = np.sum(np.sign(edge[m]) == np.sign(cov[m])); l = m.sum() - w
    out['ATS_W'], out['ATS_L'] = int(w), int(l); out['ATS_pct'] = w / max(1, w + l)
    for thr in (2, 3):
        mm = m & (np.abs(edge) >= thr)
        ww = np.sum(np.sign(edge[mm]) == np.sign(cov[mm]))
        out[f'ATS_{thr}+'] = f'{ww}-{mm.sum() - ww}'
    pr = np.clip(d[prob].values, 1e-4, 1 - 1e-4); yy = (y > 0).astype(float)
    out['Brier'] = np.mean((pr[nt] - yy[nt]) ** 2)
    out['LogLoss'] = -np.mean(yy[nt] * np.log(pr[nt]) + (1 - yy[nt]) * np.log(1 - pr[nt]))
    # weekly consistency
    d['su'] = np.where(nt, (np.sign(p) == np.sign(y)).astype(float), np.nan)
    wk = d.groupby(['season', 'week']).su.mean()
    out['wk_acc_sd'] = wk.std(); out['wk_acc_p10'] = wk.quantile(0.10)
    out['wk_RMSE_sd'] = d.assign(e=(p - y) ** 2).groupby(['season', 'week']).e.mean().pow(0.5).std()
    return out


def line_as_model(df, sd=13.5):
    """The closing line itself as a forecaster: margin = spread_line, win prob from no-vig moneyline (or normal approx)."""
    d = df.copy(); d['pred'] = d.spread_line
    p = no_vig_prob(d.home_moneyline.values, d.away_moneyline.values)
    d['prob'] = np.where(np.isnan(p), norm.cdf(d.spread_line / sd), p)
    return d


def calibration_table(df, prob='prob', bins=(0, .2, .3, .4, .5, .6, .7, .8, 1.0)):
    d = df[df.result.notna() & (df.result != 0)].copy()
    d['bin'] = pd.cut(d[prob], bins, include_lowest=True)
    t = d.groupby('bin', observed=True).agg(games=('result', 'size'), predicted=(prob, 'mean'), actual=('result', lambda r: (r > 0).mean()))
    return t


def fmt(res):
    return (f"n={res['games']:5d}  MAE {res['MAE']:.2f}  RMSE {res['RMSE']:.2f}  SU {res['SU_acc']*100:.1f}%  "
            f"ATS {res['ATS_W']}-{res['ATS_L']} ({res['ATS_pct']*100:.1f}%)  Brier {res['Brier']:.4f}  LogLoss {res['LogLoss']:.4f}")
