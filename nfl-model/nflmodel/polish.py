"""Presentation layer for output/NFL_Model_<season>.xlsx: navigation, sheet order, team colours, tiers and the charts.

Called by workbook.build() just before the workbook is saved. It only restyles and adds things in empty space
(never moves or rewrites a cell the self-test checks), so every number and formula stays exactly as built.
"""
import numpy as np
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule
from openpyxl.chart import BarChart, LineChart, ScatterChart, Reference, Series
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import Marker
from openpyxl.chart.text import RichText
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.text import Paragraph, ParagraphProperties, CharacterProperties, Font as DFont
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.utils import get_column_letter as COL

NAVY, SLATE, ACCENT, GOLD, PAPER, GREY, WHITE, INK = '17202B', '243447', '2E4A66', 'C99A2E', 'F4F6F9', '6B7280', 'FFFFFF', '1F2937'
GREEN, RED, STEEL = '2E7D4F', 'B23B3B', '8C96A3'
FONT = 'Arial'

# primary colour, text colour on it
TEAM = {
    'ARI': ('97233F', 'FFFFFF'), 'ATL': ('A71930', 'FFFFFF'), 'BAL': ('241773', 'FFFFFF'), 'BUF': ('00338D', 'FFFFFF'),
    'CAR': ('0085CA', 'FFFFFF'), 'CHI': ('0B162A', 'FF8200'), 'CIN': ('FB4F14', '000000'), 'CLE': ('311D00', 'FF3C00'),
    'DAL': ('003594', 'FFFFFF'), 'DEN': ('FB4F14', '002244'), 'DET': ('0076B6', 'FFFFFF'), 'GB': ('203731', 'FFB612'),
    'HOU': ('03202F', 'FFFFFF'), 'IND': ('002C5F', 'FFFFFF'), 'JAX': ('006778', 'D7A22A'), 'KC': ('E31837', 'FFB81C'),
    'LV': ('000000', 'A5ACAF'), 'LAC': ('0080C6', 'FFC20E'), 'LAR': ('003594', 'FFD100'), 'MIA': ('008E97', 'FFFFFF'),
    'MIN': ('4F2683', 'FFC62F'), 'NE': ('002244', 'FFFFFF'), 'NO': ('101820', 'D3BC8D'), 'NYG': ('0B2265', 'FFFFFF'),
    'NYJ': ('125740', 'FFFFFF'), 'PHI': ('004C54', 'FFFFFF'), 'PIT': ('101820', 'FFB612'), 'SF': ('AA0000', 'B3995D'),
    'SEA': ('002244', '69BE28'), 'TB': ('D50A0A', 'FFFFFF'), 'TEN': ('0C2340', '4B92DB'), 'WSH': ('5A1414', 'FFB612')}
ALIAS = {'LA': 'LAR', 'WAS': 'WSH', 'JAC': 'JAX'}
# a line/marker colour that shows up on white (very dark primaries swap to their second colour)
DARK = {'CHI', 'HOU', 'LV', 'NO', 'PIT', 'CLE', 'NE', 'SEA', 'TEN'}
def line_colour(t):
    t = ALIAS.get(t, t); bg, fg = TEAM.get(t, (STEEL, WHITE))
    return fg if t in DARK and fg not in ('FFFFFF', '000000') else bg

TIERS = [('Contender', 4.0, 'C99A2E'), ('Playoff team', 1.5, '2E7D4F'), ('Bubble', -1.5, '8C96A3'), ('Rebuilding', -4.5, 'C77B30'), ('Basement', -99, '7A1F1F')]
GROUPS = {   # tab colour by group
    'home': 'C99A2E', 'tipping': '2E4A66', 'model': '2E7D4F', 'week': '17202B', 'thisweek': 'E3B341', 'info': '9AA4B2'}

thin = Side(style='thin', color='D9DEE7')
fill = lambda c: PatternFill('solid', fgColor=c)
F = lambda size=10, bold=False, color=INK, italic=False, underline=None: Font(name=FONT, size=size, bold=bold, color=color, italic=italic, underline=underline)


# ------------------------------------------------------------------ small helpers
def link(ws, r, c, text, sheet, size=9):
    x = ws.cell(r, c, text); x.hyperlink = Hyperlink(ref=x.coordinate, location=f"'{sheet}'!A1", display=text)
    x.font = F(size, True, ACCENT, underline='single'); x.alignment = Alignment(vertical='center'); return x


def nav_bar(ws, items, row=3):
    """A row of links, spaced by the column widths (same idea as the tipping sheets' row 3)."""
    c = 1
    for text, sheet in items:
        if sheet not in ws.parent.sheetnames: continue
        link(ws, row, c, text, sheet); room = 0
        while room < len(text) * 1.05 + 3:
            room += ws.column_dimensions[COL(c)].width or 8.43; c += 1
    ws.row_dimensions[row].height = 18


def team_cf(ws, rng):
    """Fill each team code in `rng` with that team's colours (one rule per team)."""
    first = rng.split(':')[0]
    for t, (bg, fg) in TEAM.items():
        codes = [t] + [a for a, b in ALIAS.items() if b == t]
        cond = 'OR(' + ','.join(f'{first}="{c}"' for c in codes) + ')' if len(codes) > 1 else f'{first}="{t}"'
        ws.conditional_formatting.add(rng, FormulaRule(formula=[cond], fill=PatternFill(fill_type='solid', fgColor=bg, bgColor=bg),
                                                       font=Font(name=FONT, color=fg, bold=True)))


def _txt(sz=800, bold=False, col=INK):
    cp = CharacterProperties(sz=sz, b=bold, solidFill=col, latin=DFont(typeface=FONT))
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])


def tidy(ch, title=None, size=1200):
    """Consistent chart look: bold dark title, small axis text, light gridlines."""
    if title is not None: ch.title = title
    try:
        ch.title.tx.rich.p[0].pPr = ParagraphProperties(defRPr=CharacterProperties(sz=size, b=True, solidFill=INK, latin=DFont(typeface=FONT)))
    except Exception:
        pass
    for ax in (getattr(ch, 'x_axis', None), getattr(ch, 'y_axis', None)):
        if ax is None: continue
        ax.txPr = _txt(800)
        if getattr(ax, 'majorGridlines', None) is not None:
            ax.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill='E5E7EB'))
        try:
            if ax.title is not None:
                ax.title.tx.rich.p[0].pPr = ParagraphProperties(defRPr=CharacterProperties(sz=850, b=False, solidFill=GREY, latin=DFont(typeface=FONT)))
        except Exception:
            pass
        ax.delete = False
    if ch.legend is not None: ch.legend.txPr = _txt(800)
    return ch


def solid(s, colour, width=None, dash=None, marker=None):
    s.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill=colour, w=width, prstDash=dash))
    if s.marker is None: s.marker = Marker()
    if marker:
        s.marker.symbol = marker; s.marker.size = 6
        s.marker.graphicalProperties = GraphicalProperties(solidFill=colour, ln=LineProperties(solidFill=WHITE))
    else:
        s.marker.symbol = 'none'
    s.smooth = False


def header_row(ws, r, c0, labels):
    for j, h in enumerate(labels):
        x = ws.cell(r, c0 + j, h); x.font = F(9, True, WHITE); x.fill = fill(ACCENT)
        x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def find_header(ws, text, row):
    for c in range(1, ws.max_column + 1):
        if ws.cell(row, c).value == text: return c
    return None


# ------------------------------------------------------------------ the sheets
def power_rankings(wb):
    ws = wb['Power Rankings']; hr = 4
    cP, cT = find_header(ws, 'Power', hr), find_header(ws, 'Team', hr)
    if not cP or not cT: return
    last = hr
    while ws.cell(last + 1, cT).value: last += 1
    r1 = hr + 1
    team_cf(ws, f'{COL(cT)}{r1}:{COL(cT)}{last}')
    # medals for 1-3
    for r, col in zip(range(r1, r1 + 3), ('C99A2E', 'A8B0B9', 'A86B3C')):
        x = ws.cell(r, 1); x.fill = fill(col); x.font = F(10, True, WHITE)
    # tier column after the last used column
    tc = 1
    while ws.cell(hr, tc).value not in (None, 'Tier'): tc += 1
    header_row(ws, hr, tc, ['Tier']); ws.column_dimensions[COL(tc)].width = 14
    for r in range(r1, last + 1):
        p = ws.cell(r, cP).value or 0
        lab, _, col = next(t for t in TIERS if p >= t[1])
        x = ws.cell(r, tc, lab); x.fill = fill(col); x.font = F(9, True, WHITE); x.alignment = Alignment(horizontal='center', vertical='center')
        x.border = Border(bottom=Side(style='thin', color=WHITE))
    note_r = last + 2
    while ws.cell(note_r, 1).value: note_r += 1
    ws.cell(note_r, 1, 'Tiers by Power: Contender +4 or more · Playoff team +1.5 · Bubble −1.5 · Rebuilding −4.5 · Basement below that.').font = F(8, False, GREY, True)
    # chart 1: power score, coloured by tier
    ch = BarChart(); ch.type = 'bar'; ch.legend = None; ch.gapWidth = 35; ch.height = 17.5; ch.width = 15
    ch.add_data(Reference(ws, min_col=cP, min_row=hr, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=cT, min_row=r1, max_row=last))
    ch.x_axis.scaling.orientation = 'maxMin'; ch.x_axis.tickLblPos = 'low'; ch.y_axis.majorGridlines = None; ch.y_axis.number_format = '+0;-0;0'; ch.y_axis.crosses = 'max'
    tidy(ch, 'Power score (pts vs an average team)')
    s = ch.series[0]
    for i, r in enumerate(range(r1, last + 1)):
        p = ws.cell(r, cP).value or 0
        dp = DataPoint(idx=i); dp.graphicalProperties = GraphicalProperties(solidFill=next(t for t in TIERS if p >= t[1])[2]); s.dPt.append(dp)
    ch.x_axis.txPr = _txt(750, True)
    ws.add_chart(ch, f'{COL(tc + 2)}4')
    # chart 2: what the power score is made of (top 12, stacked)
    parts = [h for h in ('Market', 'Results + Elo', 'EPA offence', 'EPA defence', 'Special teams', '4th-down', 'QB now') if find_header(ws, h, hr)]
    if parts:
        cs = [find_header(ws, h, hr) for h in parts]
        if cs == list(range(cs[0], cs[0] + len(cs))):
            sb = BarChart(); sb.type = 'bar'; sb.grouping = 'stacked'; sb.overlap = 100; sb.gapWidth = 40; sb.height = 11; sb.width = 24
            sb.add_data(Reference(ws, min_col=cs[0], max_col=cs[-1], min_row=hr, max_row=min(last, r1 + 11)), titles_from_data=True)
            sb.set_categories(Reference(ws, min_col=cT, min_row=r1, max_row=min(last, r1 + 11)))
            sb.x_axis.scaling.orientation = 'maxMin'; sb.x_axis.tickLblPos = 'low'; sb.y_axis.majorGridlines = None; sb.legend.position = 'b'; sb.y_axis.crosses = 'max'
            tidy(sb, 'What makes up the power score: top 12')
            for s_, col in zip(sb.series, ('1F4E79', '7B3FA0', '2E7D4F', '9FD0B0', 'C99A2E', '8A5A12', 'B23B3B')):
                s_.graphicalProperties = GraphicalProperties(solidFill=col, ln=LineProperties(noFill=True))
            ws.add_chart(sb, f'A{note_r + 2}')


def ranking_history(wb, current_order):
    ws = wb['Ranking History']; hr = 4
    ncol = 1
    while ws.cell(hr, ncol + 1).value: ncol += 1
    last = hr
    while ws.cell(last + 1, 1).value: last += 1
    if ncol < 2: return
    team_cf(ws, f'A{hr + 1}:A{last}')
    ws._charts = []
    ch = LineChart(); ch.height = 11; ch.width = 24; ch.display_blanks = 'gap'
    ch.y_axis.scaling.orientation = 'maxMin'; ch.y_axis.scaling.min = 1; ch.y_axis.scaling.max = 32; ch.y_axis.majorUnit = 4
    ch.x_axis.crosses = 'max'
    for i in range(min(8, last - hr)):
        r = hr + 1 + i; t = ws.cell(r, 1).value
        s = Series(Reference(ws, min_col=2, max_col=ncol, min_row=r), title=t)
        solid(s, line_colour(t), 31750, marker='circle'); ch.series.append(s)
    ch.set_categories(Reference(ws, min_col=2, max_col=ncol, min_row=hr)); ch.legend.position = 'r'
    tidy(ch, 'The rank race: current top 8 (1 = best)')
    ws.add_chart(ch, f'{COL(ncol + 2)}4')
    # second chart: the bottom 8, so the whole league is covered at a glance
    ch2 = LineChart(); ch2.height = 11; ch2.width = 24; ch2.display_blanks = 'gap'
    ch2.y_axis.scaling.orientation = 'maxMin'; ch2.y_axis.scaling.min = 1; ch2.y_axis.scaling.max = 32; ch2.y_axis.majorUnit = 4
    ch2.x_axis.crosses = 'max'
    for r in range(max(hr + 1, last - 7), last + 1):
        t = ws.cell(r, 1).value; s = Series(Reference(ws, min_col=2, max_col=ncol, min_row=r), title=t)
        solid(s, line_colour(t), 31750, marker='circle'); ch2.series.append(s)
    ch2.set_categories(Reference(ws, min_col=2, max_col=ncol, min_row=hr)); ch2.legend.position = 'r'
    tidy(ch2, 'The bottom 8 (1 = best)')
    ws.add_chart(ch2, f'{COL(ncol + 2)}27')


def scatter_colours(wb, name, diagonal=None):
    if name not in wb.sheetnames: return
    ws = wb[name]
    for ch in ws._charts:
        if not isinstance(ch, ScatterChart): continue
        for s in ch.series:
            t = s.tx.v if s.tx is not None and s.tx.v else None
            col = line_colour(t) if t else STEEL
            if s.marker is None: s.marker = Marker()
            s.marker.symbol = 'circle'; s.marker.size = 8
            s.marker.graphicalProperties = GraphicalProperties(solidFill=col, ln=LineProperties(solidFill=WHITE))
            s.graphicalProperties = GraphicalProperties(ln=LineProperties(noFill=True))
            if s.dLbls is not None:
                s.dLbls.showLegendKey = False; s.dLbls.showVal = False; s.dLbls.showCatName = False; s.dLbls.showSerName = True
                s.dLbls.position = 'r'; s.dLbls.txPr = _txt(650, True, INK)
        tidy(ch); ch.height = 13; ch.width = 19
        ch.scatterStyle = 'lineMarker'; ch.visible_cells_only = False
        if diagonal:
            (xr, yr) = diagonal
            d = Series(Reference(ws, range_string=yr), Reference(ws, range_string=xr), title='Expected = actual')
            d.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill='9AA4B2', w=19050, prstDash='dash')); d.marker = Marker(symbol='none')
            ch.series.append(d)


def luck_diagonal(wb):
    ws = wb['Luck & Expected Wins']
    c = find_header(ws, 'Expected wins', 4); w = find_header(ws, 'Wins', 4)
    if not c or not w: return None
    vals = [ws.cell(r, k).value for r in range(5, 37) for k in (c, w) if isinstance(ws.cell(r, k).value, (int, float))]
    if not vals: return None
    lo, hi = float(np.floor(min(vals))), float(np.ceil(max(vals)))
    hc = 30   # helper cells, far right, hidden
    ws.cell(4, hc, 'diag x'); ws.cell(4, hc + 1, 'diag y')
    ws.cell(5, hc, lo); ws.cell(6, hc, hi); ws.cell(5, hc + 1, lo); ws.cell(6, hc + 1, hi)
    for k in (hc, hc + 1): ws.column_dimensions[COL(k)].hidden = True
    q = "'Luck & Expected Wins'!"
    return (f'{q}${COL(hc)}$5:${COL(hc)}$6', f'{q}${COL(hc + 1)}$5:${COL(hc + 1)}$6')


def luck_chart(wb):
    """Wins above (+) or below (−) what each team's play deserved, sorted, green = lucky, red = unlucky."""
    ws = wb['Luck & Expected Wins']; hr = 4
    cT, cL = find_header(ws, 'Team', hr), find_header(ws, 'Luck (wins)', hr)
    if not cT or not cL: return
    last = hr
    while ws.cell(last + 1, cT).value: last += 1
    team_cf(ws, f'{COL(cT)}{hr + 1}:{COL(cT)}{last}')
    ws._charts = []
    ch = BarChart(); ch.type = 'bar'; ch.legend = None; ch.gapWidth = 30; ch.height = 16.5; ch.width = 15
    ch.add_data(Reference(ws, min_col=cL, min_row=hr, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=cT, min_row=hr + 1, max_row=last))
    ch.x_axis.scaling.orientation = 'maxMin'; ch.x_axis.tickLblPos = 'low'; ch.y_axis.crosses = 'max'
    ch.y_axis.majorGridlines = None; ch.y_axis.number_format = '+0.0;-0.0;0'
    tidy(ch, 'Luck: wins above (+) or below (−) what their play deserved')
    s = ch.series[0]; s.invertIfNegative = False
    for i, r in enumerate(range(hr + 1, last + 1)):
        v = ws.cell(r, cL).value or 0
        dp = DataPoint(idx=i); dp.graphicalProperties = GraphicalProperties(solidFill=GREEN if v > 0.25 else RED if v < -0.25 else 'B8C0CA'); s.dPt.append(dp)
    s.dLbls = DataLabelList(); s.dLbls.showVal = True; s.dLbls.showSerName = False; s.dLbls.showCatName = False; s.dLbls.showLegendKey = False
    s.dLbls.numFmt = '+0.0;-0.0;0'; s.dLbls.position = 'outEnd'; s.dLbls.txPr = _txt(650)
    ch.x_axis.txPr = _txt(750, True)
    ws.add_chart(ch, f'{COL(ws.max_column + 2)}4')


def projections(wb):
    ws = wb['Season Projections']
    team_cf(ws, 'B5:B36')
    for ch in ws._charts:
        if not isinstance(ch, BarChart): continue
        tidy(ch, 'Playoff odds'); ch.gapWidth = 30
        s = ch.series[0]; s.dPt = []
        for i in range(32):
            p = ws.cell(5 + i, 13).value or 0
            col = GREEN if p >= 0.75 else GOLD if p >= 0.25 else 'B8C0CA'
            dp = DataPoint(idx=i); dp.graphicalProperties = GraphicalProperties(solidFill=col); s.dPt.append(dp)
        s.dLbls = DataLabelList(); s.dLbls.showVal = True; s.dLbls.showSerName = False; s.dLbls.showCatName = False; s.dLbls.showLegendKey = False
        s.dLbls.numFmt = '0%'; s.dLbls.position = 'outEnd'; s.dLbls.txPr = _txt(700)
        ch.x_axis.txPr = _txt(750, True); ch.y_axis.majorGridlines = None; ch.y_axis.crosses = 'max'; ch.y_axis.delete = True
    for k in (12, 13): ws.column_dimensions[COL(k)].hidden = True     # the chart's sorted copy of the table: the chart reads it, you don't need to
    for ch in ws._charts: ch.visible_cells_only = False
    ws.cell(38, 1, 'Chart colours: green = 75%+ to make the playoffs, gold = 25–75% (in the race), grey = under 25%.').font = F(8, False, GREY, True)


def leaderboard(wb):
    ws = wb['Leaderboard']
    style = {'You': (GOLD, 41275, None, 'circle'), 'Model': (NAVY, 28575, None, None), 'Betting line': ('9AA4B2', 28575, 'dash', None),
             'Panel consensus': (GREEN, 28575, None, None)}
    for ch in ws._charts:
        for s in ch.series:
            t = s.tx.v if s.tx is not None and s.tx.v else (s.tx.strRef.f if s.tx is not None and s.tx.strRef else '')
            col, w, dash, mk = style.get(t, (STEEL, 22225, None, None)); solid(s, col, w, dash, mk)
        tidy(ch); ch.height = 9; ch.width = 24
        if ch.legend is not None: ch.legend.position = 'b'


def money(wb):
    ws = wb['Money']
    for ch in ws._charts:
        tidy(ch); ch.height = 8.5; ch.width = 15
        for s in ch.series: solid(s, GOLD, 34925, marker='circle')


def value_report(wb):
    ws = wb['Value Report']
    cols = {'Actual': (GOLD, 34925, None), 'Expected': (NAVY, 25400, 'dash'), 'Value bot': (GREEN, 25400, None)}
    for ch in ws._charts:
        for s in ch.series:
            t = s.tx.v if s.tx is not None and s.tx.v else ''
            col, w, d = cols.get(t, (STEEL, 22225, None)); solid(s, col, w, d)
        tidy(ch)


def my_stats(wb):
    ws = wb['My Stats']
    for ch in ws._charts:
        tidy(ch)
        for s in ch.series: s.graphicalProperties = GraphicalProperties(solidFill=GOLD, ln=LineProperties(noFill=True))


def dashboard(wb, week, rank_rows):
    ws = wb['Dashboard']
    this = f'Wk {week}' if f'Wk {week}' in wb.sheetnames else None
    items = ([(f'▶ This week (Wk {week})', this)] if this else []) + [('Power Rankings', 'Power Rankings'), ('Leaderboard', 'Leaderboard'),
             ('Money', 'Money'), ('Edge Finder', 'Edge Finder'), ('Season Projections', 'Season Projections'), ('Settings', 'Settings')]
    nav_bar(ws, items)
    team_cf(ws, 'C6:C21')
    # power top 10 in the empty space under the playoff race
    r0 = 28; c0 = 9
    while any(ws.cell(r, c0).value for r in range(r0, r0 + 13)): r0 += 1
    x = ws.cell(r0, c0, 'POWER RANKINGS · TOP 10'); x.font = F(10, True, GOLD)
    for k in range(c0, c0 + 4): ws.cell(r0, k).border = Border(bottom=Side(style='medium', color=GOLD))
    header_row(ws, r0 + 1, c0, ['#', 'Team', 'Power', 'Tier'])
    for i, (rk, t, p) in enumerate(rank_rows[:10]):
        r = r0 + 2 + i
        ws.cell(r, c0, rk).font = F(10, True); ws.cell(r, c0).alignment = Alignment(horizontal='center')
        y = ws.cell(r, c0 + 1, t); y.alignment = Alignment(horizontal='center')
        z = ws.cell(r, c0 + 2, p); z.number_format = '+0.0;-0.0;0.0'; z.font = F(10, True); z.alignment = Alignment(horizontal='center')
        lab, _, col = next(tt for tt in TIERS if (p or 0) >= tt[1])
        q = ws.cell(r, c0 + 3, lab); q.fill = fill(col); q.font = F(9, True, WHITE); q.alignment = Alignment(horizontal='center')
        for k in range(c0, c0 + 4): ws.cell(r, k).border = Border(bottom=thin)
    team_cf(ws, f'{COL(c0 + 1)}{r0 + 2}:{COL(c0 + 1)}{r0 + 11}')
    link(ws, r0 + 12, c0, 'Full rankings ▸', 'Power Rankings')


def model_nav(wb, week):
    this = f'Wk {week}'
    items = [('⌂ Dashboard', 'Dashboard'), (f'▶ Wk {week}', this), ('Power Rankings', 'Power Rankings'), ('Ranking History', 'Ranking History'),
             ('Projections', 'Season Projections'), ('Team Efficiency', 'Team Efficiency'), ('QBs', 'QBs'), ('Luck', 'Luck & Expected Wins'),
             ('Schedule', 'Strength of Schedule')]
    for n in ('Power Rankings', 'Ranking History', 'Team Efficiency', 'QBs', 'Luck & Expected Wins', 'Strength of Schedule', 'Season Projections', 'About'):
        if n in wb.sheetnames and not any(ws_c.value for ws_c in wb[n][3]):
            nav_bar(wb[n], [i for i in items if i[1] != n])


def week_tabs(wb, week):
    for w in range(1, 19):
        n = f'Wk {w}'
        if n not in wb.sheetnames: continue
        ws = wb[n]
        team_cf(ws, 'C10:C25'); team_cf(ws, 'D10:D25')
        # the current week's tab gets a "this week" flag in the title band
        if w == week:
            ws.cell(1, 1).value = (ws.cell(1, 1).value or '') + '   ◀ THIS WEEK'


def pick_dropdowns(wb):
    """Dropdowns in the cream pick cells of every week tab: tip and spread bet = the two teams, over/under = Over/Under,
    locks = any team playing that week. weekly.py copies whatever is picked here back into the inputs file on the next run."""
    from openpyxl.worksheet.datavalidation import DataValidation
    from nflmodel.tipping_book import GAME0, BET0
    for w in range(1, 19):
        n = f'Wk {w}'
        if n not in wb.sheetnames: continue
        ws = wb[n]; rows = [GAME0 + j for j in range(16) if ws.cell(GAME0 + j, 3).value and ws.cell(GAME0 + j, 4).value]
        if not rows: continue
        ou = DataValidation(type='list', formula1='"Over,Under"', allow_blank=True)
        ou.promptTitle = 'Over / under'; ou.prompt = 'Pick Over or Under'; ou.showInputMessage = True
        ws.add_data_validation(ou)
        for j, i in enumerate(rows):
            b = BET0 + (i - GAME0)
            tip = DataValidation(type='list', formula1=f'=$C${i}:$D${i}', allow_blank=True)
            tip.promptTitle = 'Your tip'; tip.prompt = 'Pick a team from the list'; tip.showInputMessage = True
            sp = DataValidation(type='list', formula1=f'=$C${i}:$D${i}', allow_blank=True)
            sp.promptTitle = 'Spread bet'; sp.prompt = 'Pick the team you are taking on the line'; sp.showInputMessage = True
            ws.add_data_validation(tip); ws.add_data_validation(sp)
            tip.add(f'G{i}'); sp.add(f'G{b}'); ou.add(f'P{b}')
        # locks: a hidden list of this week's teams in column X
        hc = 24
        for k, i in enumerate(rows):
            ws.cell(GAME0 + 2 * k, hc, ws.cell(i, 3).value); ws.cell(GAME0 + 2 * k + 1, hc, ws.cell(i, 4).value)
        ws.column_dimensions[COL(hc)].hidden = True
        lk = DataValidation(type='list', formula1=f'=${COL(hc)}${GAME0}:${COL(hc)}${GAME0 + 2 * len(rows) - 1}', allow_blank=True)
        lk.promptTitle = 'Lock of the week'; lk.prompt = 'Pick a team playing this week'; lk.showInputMessage = True
        ws.add_data_validation(lk); lk.add('E7'); lk.add('H7'); lk.add('K7')
        # say so in the title band
        c2 = ws.cell(2, 1)
        if isinstance(c2.value, str) and 'edit them there' in c2.value:
            c2.value = c2.value.replace('Cream cells come from inputs/tipping_inputs.xlsx (edit them there, not here).',
                                        'Pick from the dropdowns in the cream cells (tip, spread, over/under, locks): the next run copies them into the inputs file.')


def tipping_nav(wb, week):
    """The tipping sheets already have Dashboard / Leaderboard / Money / My Stats in row 3: add this week and the rankings."""
    names = ['Leaderboard', 'Money', 'My Stats', 'Spreads & Totals', 'Head to Head', 'Expert Scout', 'Edge Finder', 'Value Report', 'Settings'] + \
            [f'Wk {w}' for w in range(1, 19)]
    for n in names:
        if n not in wb.sheetnames: continue
        ws = wb[n]; last = max([c.column for c in ws[3] if c.value is not None] or [0])
        if not last: continue
        c = last + 2
        for text, sheet in ((f'▶ This week (Wk {week})', f'Wk {week}'), ('Power Rankings', 'Power Rankings')):
            if sheet == n or sheet not in wb.sheetnames: continue
            link(ws, 3, c, text, sheet); room = 0
            while room < len(text) * 1.05 + 3:
                room += ws.column_dimensions[COL(c)].width or 8.43; c += 1


def order_and_tabs(wb, week):
    tipping = ['Leaderboard', 'Money', 'My Stats', 'Spreads & Totals', 'Head to Head', 'Expert Scout', 'Edge Finder', 'Value Report']
    model = ['Power Rankings', 'Ranking History', 'Season Projections', 'Team Efficiency', 'QBs', 'Luck & Expected Wins', 'Strength of Schedule']
    weeks = [f'Wk {w}' for w in range(1, 19)]
    info = ['About', 'Settings']
    want = ['Dashboard'] + [n for n in tipping + model + weeks + info if n in wb.sheetnames]
    rest = [s for s in wb._sheets if s.title not in want]
    wb._sheets = [wb[n] for n in want] + rest
    for ws in wb.worksheets:
        n = ws.title
        g = 'home' if n == 'Dashboard' else 'tipping' if n in tipping else 'model' if n in model else 'info' if n in info else \
            ('thisweek' if n == f'Wk {week}' else 'week') if n in weeks else 'info'
        ws.sheet_properties.tabColor = GROUPS[g]
        ws.sheet_view.tabSelected = n == 'Dashboard'
    wb.active = 0


def apply(wb, week, rank_rows):
    """rank_rows: [(rank, team code, power)] in rank order."""
    order_and_tabs(wb, week)
    dashboard(wb, week, rank_rows)
    model_nav(wb, week)
    if 'Power Rankings' in wb.sheetnames: power_rankings(wb)
    if 'Ranking History' in wb.sheetnames: ranking_history(wb, [t for _, t, _ in rank_rows])
    scatter_colours(wb, 'Team Efficiency')
    if 'Luck & Expected Wins' in wb.sheetnames: luck_chart(wb)
    if 'Season Projections' in wb.sheetnames: projections(wb)
    for n, fn in (('Leaderboard', leaderboard), ('Money', money), ('Value Report', value_report), ('My Stats', my_stats)):
        if n in wb.sheetnames: fn(wb)
    week_tabs(wb, week)
    tipping_nav(wb, week)
    if 'Team Efficiency' in wb.sheetnames:
        c = find_header(wb['Team Efficiency'], 'Team', 4)
        if c: team_cf(wb['Team Efficiency'], f'{COL(c)}5:{COL(c)}36')
    if 'QBs' in wb.sheetnames:
        c = find_header(wb['QBs'], 'Team', 4)
        if c: team_cf(wb['QBs'], f'{COL(c)}5:{COL(c)}{wb["QBs"].max_row}')
    pick_dropdowns(wb)
    for ws in wb.worksheets:
        for ch in ws._charts:
            if ch.title is not None:
                try: ch.title.overlay = False
                except Exception: pass
            if isinstance(ch, BarChart):
                for s_ in ch.series:
                    s_.invertIfNegative = False
