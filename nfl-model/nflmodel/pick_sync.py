"""Copy picks made in the workbook's dropdowns back into inputs/tipping_inputs.xlsx.

Tom picks his tip, spread bet, over/under and locks from dropdowns on the week tabs of output/NFL_Model_<season>.xlsx.
That workbook is rebuilt on every run, so before the build this copies any pick made there into the inputs file
(which stays the single source the build reads). Rules:
  * a pick in the workbook that differs from the inputs file wins (it was made after the last build);
  * an empty cell in the workbook never clears a pick in the inputs file;
  * a value that isn't one of that game's teams (or Over/Under) is ignored and reported.
The inputs file is backed up by weekly.py before this runs.
"""
import os
from openpyxl import load_workbook

from nflmodel.tipping_book import GAME0, BET0
from nflmodel.tipping_inputs import G0, LOCK_ROW, NG, NW


def _t(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def sync(workbook_path, inputs_path):
    """Returns a list of human-readable changes (empty if nothing changed)."""
    if not (os.path.exists(workbook_path) and os.path.exists(inputs_path)):
        return []
    out = load_workbook(workbook_path, data_only=True, read_only=True)
    picked = {}   # (week, away, home) -> dict(tip, spread, ou) ; ('lock', week) -> dict(tip, spread, ou)
    for wk in range(1, NW + 1):
        n = f'Wk {wk}'
        if n not in out.sheetnames: continue
        ws = out[n]
        rows = list(ws.iter_rows(min_row=1, max_row=BET0 + NG, max_col=16, values_only=True))
        for j in range(NG):
            g = rows[GAME0 - 1 + j]; b = rows[BET0 - 1 + j]
            away, home = _t(g[2]), _t(g[3])
            if not away or not home: continue
            picked[(wk, away, home)] = dict(tip=_t(g[6]), spread=_t(b[6]), ou=_t(b[15]))
        lk = rows[6]
        picked[('lock', wk)] = dict(tip=_t(lk[4]), spread=_t(lk[7]), ou=_t(lk[10]))
    out.close()

    wb = load_workbook(inputs_path)
    changes, skipped = [], []
    for wk in range(1, NW + 1):
        ws = wb[f'Wk {wk}']; teams = set()
        for i in range(NG):
            r = G0 + i
            away, home = _t(ws.cell(r, 4).value), _t(ws.cell(r, 5).value)
            if not away or not home: continue
            teams |= {away, home}
            p = picked.get((wk, away, home))
            if not p: continue
            for key, col, ok in (('tip', 8, {away, home}), ('spread', 9, {away, home}), ('ou', 10, {'Over', 'Under'})):
                v = p[key]
                if v is None or v == _t(ws.cell(r, col).value): continue
                if v not in ok: skipped.append(f'Wk {wk} {away} @ {home} {key}: "{v}"'); continue
                old = _t(ws.cell(r, col).value); ws.cell(r, col).value = v
                changes.append(f'Wk {wk} {away} @ {home}: {key} {old or "(blank)"} → {v}')
        lp = picked.get(('lock', wk)) or {}
        for key, col in (('tip', 2), ('spread', 5), ('ou', 8)):
            v = lp.get(key)
            if v is None or v == _t(ws.cell(LOCK_ROW, col).value): continue
            if v not in teams: skipped.append(f'Wk {wk} lock {key}: "{v}"'); continue
            old = _t(ws.cell(LOCK_ROW, col).value); ws.cell(LOCK_ROW, col).value = v
            changes.append(f'Wk {wk} lock {key}: {old or "(blank)"} → {v}')
    if changes:
        wb.save(inputs_path)
    wb.close()
    return changes + [f'ignored (not a valid choice) {s}' for s in skipped]
