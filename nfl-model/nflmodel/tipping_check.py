"""Self-tests for the tipping half of the workbook.

1. Recalculate the finished workbook in LibreOffice (headless) and scan every cell for formula errors.
2. Compare the recalculated week-tab formulas (fair prices / lines, winner, ✓/✗, stakes with locks, P/L) and the
   Leaderboard's live W / L totals with the Python engine.
3. Pure-maths checks of the fair-price rule and P/L arithmetic on known cases.
"""
import os, shutil, subprocess, tempfile
import numpy as np
from openpyxl import load_workbook
from nflmodel.tipping import fair_price, fair_line, NW, MODEL, LINE
from nflmodel.tipping_book import week_layout, GAME0, BET0

ERRORS = ('#REF!', '#N/A', '#DIV/0!', '#VALUE!', '#NAME?', '#NUM!', '#NULL!', 'Err:')


def soffice():
    for p in ('soffice', 'libreoffice', '/usr/bin/soffice', '/Applications/LibreOffice.app/Contents/MacOS/soffice'):
        if shutil.which(p) or os.path.exists(p): return shutil.which(p) or p
    return None


def recalc(path, outdir=None):
    """Open in LibreOffice, recalculate, save a copy as xlsx. Returns the copy's path (or None without LibreOffice)."""
    exe = soffice()
    if not exe: return None
    outdir = outdir or tempfile.mkdtemp(prefix='nfl_recalc_')
    prof = tempfile.mkdtemp(prefix='lo_profile_')
    subprocess.run([exe, f'-env:UserInstallation=file://{prof}', '--headless', '--calc', '--convert-to', 'xlsx:Calc MS Excel 2007 XML', '--outdir', outdir, path],
                   check=True, capture_output=True, timeout=600)
    shutil.rmtree(prof, ignore_errors=True)
    return os.path.join(outdir, os.path.basename(path))


def scan_errors(path):
    wb = load_workbook(path, data_only=True); bad = []; n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    n += 1
                    if c.value.startswith(ERRORS): bad.append(f'{ws.title}!{c.coordinate} {c.value}')
    return bad, wb


def same(a, b, tol=1e-6):
    blank = lambda x: x is None or x == '' or (isinstance(x, float) and np.isnan(x))
    if blank(a) and blank(b): return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float, np.floating, np.integer)):
        return abs(float(a) - float(b)) <= tol * max(1, abs(float(b)))
    return str(a).strip() == str(b).strip()


def compare(wb, ctx):
    """Recalculated formula values vs the engine. Returns (cells compared, mismatches)."""
    G, R = ctx['G'], ctx['R']; n, bad = 0, []
    def cmp(ws, ref, want):
        nonlocal n; n += 1; got = ws[ref].value
        if not same(got, want): bad.append(f'{ws.title}!{ref}: workbook {got!r} vs engine {want!r}')
    for wk in range(1, NW + 1):
        ws = wb[f'Wk {wk}']; g = G[G.week == wk].sort_values('game')
        for j, r in enumerate(g.itertuples()):
            i, b = GAME0 + j, BET0 + j
            for c, v in (('H', r.aodds), ('I', r.hodds), ('J', r.hline), ('K', r.total), ('L', r.winner), ('M', r.tip_res),
                         ('N', ctx['S']['tip'] * r.tip_lock if isinstance(r.tip, str) else None), ('O', r.tip_pl_real),
                         ('R', ctx['P'].at[r.Index, LINE] if LINE in ctx['P'] else None)):
                cmp(ws, f'{c}{i}', v)
            for c, v in (('C', r.aline), ('D', r.sp_aprice), ('E', r.hline), ('F', r.sp_hprice), ('K', r.sp_res), ('L', r.sp_pl_real),
                         ('M', r.total), ('N', r.o_price), ('O', r.u_price), ('R', r.ou_res), ('S', r.ou_pl_real)):
                cmp(ws, f'{c}{b}', v)
            if isinstance(r.spread_bet, str): cmp(ws, f'H{b}', ctx['S']['spread'] * r.sp_lock)
            if isinstance(r.ou_bet, str): cmp(ws, f'Q{b}', ctx['S']['ou'] * r.ou_lock)
        lay = week_layout(ctx, wk)
        for t, x in lay['rows'].items():
            cmp(ws, f'S{x}', 0 if np.isnan(ctx['W'].at[t, wk]) else ctx['W'].at[t, wk]); cmp(ws, f'T{x}', 0 if np.isnan(ctx['N'].at[t, wk]) else ctx['N'].at[t, wk])
    ws = wb['Leaderboard']; wcol = 4 + NW
    for x in range(5, 5 + len(R)):
        t = ws.cell(x, 2).value
        n += 2
        if not same(ws.cell(x, wcol).value, R.at[t, 'W']): bad.append(f'Leaderboard {t} W: workbook {ws.cell(x, wcol).value} vs engine {R.at[t, "W"]}')
        if not same(ws.cell(x, wcol + 1).value, R.at[t, 'L']): bad.append(f'Leaderboard {t} L: workbook {ws.cell(x, wcol + 1).value} vs engine {R.at[t, "L"]}')
    return n, bad


def maths_checks(ctx):
    """Known-answer checks of the tipping maths, plus internal consistency of the engine's totals."""
    out = []
    def chk(ok, msg): out.append(('PASS' if ok else 'FAIL', msg))
    chk(fair_price(1.90, 2.00) == 1.95 and fair_price(1.50, 1.60) == 1.55 and fair_price(2.10, np.nan) == 2.10 and fair_price(1.333, 1.5) == 1.41,
        'fair price = ROUND(2/(1/open+1/close),2); one side missing uses the other')
    chk(fair_line(-3.0, -3.5) == -3.5 and fair_line(-3.0, -4.0) == -3.5 and fair_line(2.5, 3.0) == 2.5 and fair_line(-7.0, -7.0) == -7.0 and fair_line(44.0, 45.5) == 44.5,
        'fair line = midpoint of open and close, quarter points to the .5')
    G, S, R, W = ctx['G'], ctx['S'], ctx['R'], ctx['W']
    t = G[G.tip_res.notna()]
    want = np.where(t.tip_res == '✓', S['tip'] * t.tip_lock * (t.tip_odds - 1), -S['tip'] * t.tip_lock)
    chk(np.allclose(t.tip_pl_real.values, want), f'tip P/L = stake × (odds − 1) or −stake, locks ×{S["lock"]:g} ({len(t)} tips)')
    s = G[G.sp_res.notna()]
    pr = s.sp_price.where(s.sp_price > 1)
    want = np.where(s.sp_res == '✓', S['spread'] * s.sp_lock * (pr - 1), np.where(s.sp_res == '✗', -S['spread'] * s.sp_lock, 0))
    chk(np.allclose(s.sp_pl_real.values, want), f'spread P/L at the fair line and price, pushes return the stake ({len(s)} bets)')
    o = G[G.ou_res.notna()]
    want = np.where(o.ou_res == '✓', S['ou'] * o.ou_lock * (o.ou_price - 1), np.where(o.ou_res == '✗', -S['ou'] * o.ou_lock, 0))
    chk(np.allclose(o.ou_pl_real.values, want), f'over/under P/L ({len(o)} bets)')
    locks = sum(1 for w in ctx['inp']['weeks'].values() if w['locks'].get('tip'))
    chk(int((t.tip_lock > 1).sum()) <= locks and all(int(((G.week == wk) & (G.tip_lock > 1)).sum()) <= 1 for wk in range(1, NW + 1)),
        f'at most one tip lock per week ({int((t.tip_lock > 1).sum())} used)')
    chk(bool((R.W == W.fillna(0).sum(axis=1).reindex(R.index)).all()), 'leaderboard wins = sum of the weekly wins, for every tipper')
    chk(bool((R.W + R.L == R.graded).all()), 'wins + losses = graded picks, for every tipper')
    M = ctx['money'].dropna(subset=['staked'])
    chk(abs(M.pl.sum() - (G.tip_pl_real.sum() + G.sp_pl_real.sum() + G.ou_pl_real.sum())) < 1e-6, f'Money total {M.pl.sum():+,.2f} = sum of every bet\'s P/L')
    chk(MODEL in R.index and LINE in R.index, 'the model and the line are on the leaderboard')
    return out
