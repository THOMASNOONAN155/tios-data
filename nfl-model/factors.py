"""Test every candidate factor walk-forward. A factor is KEPT only if it lowers RMSE on the development seasons
(2012-2019) AND on the holdout seasons (2020-2025), and does not worsen log-loss on either.
2026 is not used here at all (it is the final untouched check in report.py).
Writes results/factors.csv and results/factors.md."""
import json, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
from model import build_features, walk_forward, load_all
from metrics import evaluate

DEV = list(range(2012, 2020)); HOLD = list(range(2020, 2026))
PARAMS = json.load(open('results/params.json')) if len(sys.argv) < 2 else {}
CORE = ['home', 'mkt_d']

CANDIDATES = [
    ('Efficiency: EPA/play rating', dict(add=['epa_d'])),
    ('Efficiency: success-rate rating', dict(add=['sr_d'])),
    ('Efficiency: EPA split into offence & defence', dict(add=['epa_off_d', 'epa_def_d'])),
    ('Results: opponent-adjusted (damped) margin rating', dict(add=['res_d'])),
    ('QB: starter value vs team\'s recent starters', dict(add=['qb_d'])),
    ('Injuries: non-QB snap share ruled out (off/def)', dict(add=['inj_off_d', 'inj_def_d'])),
    ('Home field: market-estimated HFA (adapts by era)', dict(add=['mkt_hfa_home'], drop=['home'])),
    ('Home field: blend weights favour recent seasons', dict(weight_recent=4.0)),
    ('Rest: days-of-rest difference', dict(add=['rest_d'])),
    ('Rest: coming off a bye', dict(add=['bye_d'])),
    ('Rest: short week (<=5 days)', dict(add=['short_d'])),
    ('Travel: miles travelled', dict(add=['miles_d'])),
    ('Time zones: hours shifted', dict(add=['tz_d'])),
    ('Time zones: body clock (west team, 1pm ET)', dict(add=['clock_d'])),
    ('Time zones: east team in late game out west', dict(add=['night_west'])),
    ('Divisional game: extra home edge', dict(add=['div'])),
    ('Divisional game: margins shrink', dict(add=['mkt_d_div'])),
    ('Weather: high wind (>15 mph) shrinks margins', dict(add=['wind_x_mkt'])),
    ('Weather: dome/warm team in cold (<=35F) game', dict(add=['cold_warm_d'])),
    ('Recent form: short-memory market rating', dict(add=['mkt_fast_d'])),
    ('Recent form: short-memory EPA rating', dict(add=['epa_fast_d'])),
    ('Early season: market weight varies by week', dict(add=['mkt_d_early'])),
    ('Early season: EPA weight varies by week', dict(add=['epa_d_early'])),
    ('Early season: wider win-prob spread in weeks 1-4', dict(sigma_early=True)),
]


def run(f, feats, opts, seasons):
    kw = {k: v for k, v in opts.items() if k in ('weight_recent', 'sigma_early')}
    return evaluate(walk_forward(f, feats, seasons, **kw))


def apply(base, opts):
    feats = [x for x in base if x not in opts.get('drop', [])] + [x for x in opts.get('add', []) if x not in base]
    return feats


def main():
    f = build_features(PARAMS)
    rows = []
    core = list(CORE); core_opts = {}
    # stage 1: each factor on top of market-only core
    def test(base, base_opts, stage):
        b_dev = run(f, base, base_opts, DEV); b_hold = run(f, base, base_opts, HOLD)
        out = []
        for name, opts in CANDIDATES:
            feats = apply(base, opts); o = dict(base_opts, **{k: v for k, v in opts.items() if k not in ('add', 'drop')})
            if feats == base and o == base_opts: continue
            d, h = run(f, feats, o, DEV), run(f, feats, o, HOLD)
            r = dict(stage=stage, factor=name, dev_dRMSE=d['RMSE'] - b_dev['RMSE'], hold_dRMSE=h['RMSE'] - b_hold['RMSE'],
                     dev_dLL=d['LogLoss'] - b_dev['LogLoss'], hold_dLL=h['LogLoss'] - b_hold['LogLoss'],
                     dev_dSU=(d['SU_acc'] - b_dev['SU_acc']) * 100, hold_dSU=(h['SU_acc'] - b_hold['SU_acc']) * 100,
                     dev_ATS=d['ATS_pct'] * 100, hold_ATS=h['ATS_pct'] * 100)
            r['helps'] = (r['dev_dRMSE'] < 0 and r['hold_dRMSE'] < 0 and r['dev_dLL'] <= 0.0002 and r['hold_dLL'] <= 0.0002)
            out.append((r, feats, o)); print(stage, name, {k: round(v, 4) if isinstance(v, float) else v for k, v in r.items() if k not in ('stage', 'factor')}, flush=True)
        return b_dev, b_hold, out
    # greedy forward selection: add the factor with the best dev gain that also helps holdout, repeat
    stage = 0
    while True:
        stage += 1
        b_dev, b_hold, out = test(core, core_opts, stage)
        rows += [r for r, _, _ in out]
        good = [x for x in out if x[0]['helps']]
        if not good: break
        best = min(good, key=lambda x: x[0]['dev_dRMSE'])
        print('>>> keep', best[0]['factor'], flush=True)
        core, core_opts = best[1], best[2]
        if stage > 15: break
    final_dev, final_hold = run(f, core, core_opts, DEV), run(f, core, core_opts, HOLD)
    df = pd.DataFrame(rows); df.to_csv('results/factors.csv', index=False)
    json.dump(dict(features=core, opts=core_opts, dev=final_dev, holdout=final_hold), open('results/selected.json', 'w'), indent=1, default=float)
    print('FINAL', core, core_opts); print('dev', final_dev); print('hold', final_hold)


if __name__ == '__main__':
    main()
