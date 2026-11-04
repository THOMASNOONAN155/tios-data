"""EPL_Model.xlsx: one clean theme, frozen headers, colour scales and charts."""
from __future__ import annotations

import numpy as np
import pandas as pd
import xlsxwriter

from .predictor import compact_grid

NAVY, TEAL, LIGHT, GREY = "#1F3864", "#2E75B6", "#EAF1FB", "#7F7F7F"
GREEN_RED = {"type": "3_color_scale", "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"}
RED_GREEN = {"type": "3_color_scale", "min_color": "#63BE7B", "mid_color": "#FFEB84", "max_color": "#F8696B"}
WHITE_BLUE = {"type": "2_color_scale", "min_color": "#FFFFFF", "max_color": "#5B9BD5"}


class Book:
    def __init__(self, path):
        self.wb = xlsxwriter.Workbook(path, {"nan_inf_to_errors": True})
        wb = self.wb
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter"}
        self.f = {
            "title": wb.add_format({**base, "bold": True, "font_size": 16, "font_color": NAVY}),
            "sub": wb.add_format({**base, "italic": True, "font_color": GREY}),
            "head": wb.add_format({**base, "bold": True, "font_color": "white", "bg_color": NAVY, "border": 1,
                                   "border_color": "#BFBFBF", "text_wrap": True, "align": "center"}),
            "txt": wb.add_format({**base, "border": 1, "border_color": "#D9D9D9"}),
            "bold": wb.add_format({**base, "bold": True, "border": 1, "border_color": "#D9D9D9"}),
            "num1": wb.add_format({**base, "num_format": "0.0", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "num2": wb.add_format({**base, "num_format": "0.00", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "num3": wb.add_format({**base, "num_format": "0.000", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "int": wb.add_format({**base, "num_format": "0", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "pct": wb.add_format({**base, "num_format": "0%", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "pct1": wb.add_format({**base, "num_format": "0.0%", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "move": wb.add_format({**base, "num_format": "▲0;▼0;–", "border": 1, "border_color": "#D9D9D9", "align": "center"}),
            "wrap": wb.add_format({**base, "text_wrap": True, "valign": "top"}),
            "h2": wb.add_format({**base, "bold": True, "font_size": 12, "font_color": TEAL}),
        }

    def sheet(self, name, title, subtitle=""):
        ws = self.wb.add_worksheet(name)
        ws.hide_gridlines(2)
        ws.set_zoom(100)
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.write(0, 0, title, self.f["title"])
        if subtitle:
            ws.write(1, 0, subtitle, self.f["sub"])
        ws.set_row(0, 24)
        return ws

    def table(self, ws, df, row, col=0, fmts=None, widths=None, scales=None, freeze=True):
        """Write df with a header row at `row`. fmts: {column: format key}. scales: {column: rule}."""
        fmts, scales = fmts or {}, scales or {}
        for j, c in enumerate(df.columns):
            ws.write(row, col + j, c, self.f["head"])
        for i, rec in enumerate(df.itertuples(index=False), 1):
            for j, v in enumerate(rec):
                fmt = self.f[fmts.get(df.columns[j], "txt")]
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    ws.write_blank(row + i, col + j, None, fmt)
                elif isinstance(v, (int, float, np.integer, np.floating)):
                    ws.write_number(row + i, col + j, float(v), fmt)
                else:
                    ws.write(row + i, col + j, str(v), fmt)
        for c, rule in scales.items():
            j = list(df.columns).index(c)
            ws.conditional_format(row + 1, col + j, row + len(df), col + j, rule)
        for j, c in enumerate(df.columns):
            ws.set_column(col + j, col + j, (widths or {}).get(c, max(9, min(28, len(str(c)) + 2))))
        ws.set_row(row, 30)
        if freeze:
            ws.freeze_panes(row + 1, col + 1)
        return row + len(df)

    def close(self):
        self.wb.close()


def build(path, ctx):
    """ctx keys: gw, gw_dates, generated, matches(df), grids(list), rankings(df), history(df), luck(df),
    fixtures(df), sos(df), sims(df), accuracy(df), live(df), about(list[str])."""
    b = Book(path)
    sheet_name = lambda s: s

    # Dashboard ------------------------------------------------------------------------------
    ws = b.sheet("Dashboard", f"Premier League {ctx['season']} — Gameweek {ctx['gw']} predictions",
                 f"{ctx['gw_dates']} · generated {ctx['generated']} · data to {ctx['data_to']}")
    md = ctx["matches"]
    end = b.table(ws, md, 3, fmts={"xG H": "num2", "xG A": "num2", "Score %": "pct", "Home %": "pct", "Draw %": "pct",
                                   "Away %": "pct", "Over 2.5 %": "pct", "BTTS %": "pct"},
                  widths={"Kickoff (UK)": 16, "Home": 15, "Away": 15, "Top 5 scores": 46, "Most likely": 11},
                  scales={"Home %": WHITE_BLUE, "Draw %": WHITE_BLUE, "Away %": WHITE_BLUE, "Over 2.5 %": WHITE_BLUE,
                          "BTTS %": WHITE_BLUE})
    ws.freeze_panes(4, 3)
    r = end + 2
    ws.write(r, 0, "Scoreline probability grids (rows = home goals, columns = away goals, 6 = 6 or more)", b.f["h2"])
    r += 1
    for k, (label, g) in enumerate(ctx["grids"]):
        c0 = (k % 2) * 9
        r0 = r + (k // 2) * 10
        ws.write(r0, c0, label, b.f["bold"])
        cg = compact_grid(g)
        for j in range(7):
            ws.write(r0 + 1, c0 + 1 + j, "6+" if j == 6 else j, b.f["head"])
            ws.write(r0 + 2 + j, c0, "6+" if j == 6 else j, b.f["head"])
            for i in range(7):
                ws.write_number(r0 + 2 + j, c0 + 1 + i, cg[j, i], b.f["pct1"])
        ws.conditional_format(r0 + 2, c0 + 1, r0 + 8, c0 + 7, WHITE_BLUE)

    # Power rankings -------------------------------------------------------------------------
    ws = b.sheet("Power Rankings", "Power rankings", "Net = expected goal difference per game against an average "
                 "Premier League schedule (home and away). Movement is versus the previous gameweek.")
    pr = ctx["rankings"]
    b.table(ws, pr, 3, fmts={"Rank": "int", "Move": "move", "Net rating": "num2", "Attack (xG for)": "num2",
                             "Defence (xG against)": "num2", "xPts/game": "num2", "xGD/game (actual)": "num2",
                             "GD/game": "num2", "Played": "int"},
            widths={"Team": 16}, scales={"Net rating": GREEN_RED, "Attack (xG for)": GREEN_RED,
                                         "Defence (xG against)": RED_GREEN, "xGD/game (actual)": GREEN_RED})

    # Ranking history ------------------------------------------------------------------------
    ws = b.sheet("Ranking History", "Ranking history", "Power-ranking position before each gameweek this season.")
    h = ctx["history"].reset_index().rename(columns={"index": "Team"})
    end = b.table(ws, h, 3, fmts={c: "int" for c in h.columns[1:]}, widths={"Team": 16},
                  scales={c: {"type": "3_color_scale", "min_color": "#63BE7B", "mid_color": "#FFFFFF",
                              "max_color": "#F8696B"} for c in h.columns[1:]})
    ch = b.wb.add_chart({"type": "line"})
    for i in range(len(h)):
        ch.add_series({"name": ["Ranking History", 4 + i, 0], "categories": ["Ranking History", 3, 1, 3, h.shape[1] - 1],
                       "values": ["Ranking History", 4 + i, 1, 4 + i, h.shape[1] - 1], "marker": {"type": "circle", "size": 4}})
    ch.set_y_axis({"reverse": True, "min": 1, "max": 20, "major_unit": 1, "name": "Rank"})
    ch.set_title({"name": "Power-ranking trends"})
    ch.set_size({"width": 1000, "height": 520})
    ch.set_legend({"position": "right"})
    ws.insert_chart(end + 2, 0, ch)

    # Attack & defence -----------------------------------------------------------------------
    ws = b.sheet("Attack & Defence", "Attack and defence ratings",
                 "Expected goals scored / conceded per game against an average opponent (home and away averaged).")
    ad = pr[["Team", "Attack (xG for)", "Defence (xG against)", "Net rating"]].sort_values("Attack (xG for)", ascending=False)
    end = b.table(ws, ad, 3, fmts={"Attack (xG for)": "num2", "Defence (xG against)": "num2", "Net rating": "num2"},
                  widths={"Team": 16}, scales={"Attack (xG for)": GREEN_RED, "Defence (xG against)": RED_GREEN,
                                               "Net rating": GREEN_RED})
    sc = b.wb.add_chart({"type": "scatter"})
    sc.add_series({"name": "Teams", "categories": ["Attack & Defence", 4, 2, end, 2], "values": ["Attack & Defence", 4, 1, end, 1],
                   "marker": {"type": "circle", "size": 7, "fill": {"color": TEAL}},
                   "data_labels": {"custom": [{"value": f"='Attack & Defence'!$A${5 + i}"} for i in range(len(ad))],
                                   "position": "right", "font": {"size": 8}}})
    sc.set_x_axis({"name": "Defence: xG conceded per game (left = better)", "reverse": True})
    sc.set_y_axis({"name": "Attack: xG scored per game"})
    sc.set_title({"name": "Attack vs defence"})
    sc.set_legend({"none": True})
    sc.set_size({"width": 820, "height": 560})
    ws.insert_chart(3, 6, sc)

    # Expected points & luck -----------------------------------------------------------------
    ws = b.sheet("Expected Points & Luck", "Expected points and luck",
                 "Expected points simulate each match from its xG. Luck = points minus expected points; "
                 "finishing = goals minus xG; goalkeeping = xG against minus goals against.")
    lk = ctx["luck"]
    end = b.table(ws, lk, 3, fmts={c: "num1" for c in lk.columns if c != "Team"} | {"Played": "int", "Points": "int"},
                  widths={"Team": 16}, scales={"Luck (pts)": GREEN_RED, "Finishing (G-xG)": GREEN_RED,
                                               "Goalkeeping (xGA-GA)": GREEN_RED})
    bc = b.wb.add_chart({"type": "bar"})
    bc.add_series({"name": "Actual points", "categories": ["Expected Points & Luck", 4, 0, end, 0],
                   "values": ["Expected Points & Luck", 4, 2, end, 2], "fill": {"color": NAVY}})
    bc.add_series({"name": "Expected points (xG)", "categories": ["Expected Points & Luck", 4, 0, end, 0],
                   "values": ["Expected Points & Luck", 4, 3, end, 3], "fill": {"color": "#9DC3E6"}})
    bc.set_title({"name": "Expected vs actual points"})
    bc.set_y_axis({"reverse": True})
    bc.set_size({"width": 720, "height": 620})
    ws.insert_chart(3, len(lk.columns) + 1, bc)

    # Fixture difficulty ---------------------------------------------------------------------
    ws = b.sheet("Fixture Difficulty", "Fixture difficulty — next 5 games",
                 "Each cell: opponent (venue) and the model's expected points for that game (green = easier). "
                 "Strength of schedule = average opponent net rating minus league average (higher = harder).")
    fd = ctx["fixtures"]
    xp_cols = [c for c in fd.columns if c.startswith("xPts ")]
    b.table(ws, fd, 3, fmts={c: "num2" for c in xp_cols} | {"xPts next 5": "num1", "SoS played": "num2",
                                                            "SoS remaining": "num2", "SoS played rank": "int",
                                                            "SoS remaining rank": "int"},
            widths={"Team": 16} | {c: 17 for c in fd.columns if c.startswith("Opp ")},
            scales={c: GREEN_RED for c in xp_cols} | {"xPts next 5": GREEN_RED, "SoS played": RED_GREEN,
                                                      "SoS remaining": RED_GREEN})

    # Season projections ---------------------------------------------------------------------
    ws = b.sheet("Season Projections", f"Season projections ({ctx['n_sims']:,} simulations)",
                 "Includes rating uncertainty. Top 5 is shown because England has had five Champions League places "
                 "in recent seasons; top 7 approximates all European places (cup winners can change this).")
    sp = ctx["sims"]
    end = b.table(ws, sp, 3, fmts={"Points now": "int", "Projected pts": "num1", "Low (10%)": "int", "High (90%)": "int",
                                   "Projected GD": "num1", "Avg position": "num1", "Title": "pct1", "Top 4": "pct1",
                                   "Top 5": "pct1", "Top 7": "pct1", "Relegation": "pct1"},
                  widths={"Team": 16}, scales={"Projected pts": GREEN_RED, "Title": WHITE_BLUE, "Top 4": WHITE_BLUE,
                                               "Top 5": WHITE_BLUE, "Top 7": WHITE_BLUE,
                                               "Relegation": {"type": "2_color_scale", "min_color": "#FFFFFF",
                                                              "max_color": "#F8696B"}})
    for k, (col, colour) in enumerate([("Title", NAVY), ("Top 4", TEAL), ("Relegation", "#C00000")]):
        j = list(sp.columns).index(col)
        c = b.wb.add_chart({"type": "bar"})
        c.add_series({"name": col, "categories": ["Season Projections", 4, 0, end, 0],
                      "values": ["Season Projections", 4, j, end, j], "fill": {"color": colour},
                      "data_labels": {"value": True, "num_format": "0%", "font": {"size": 7}}})
        c.set_title({"name": f"{col} odds"})
        c.set_y_axis({"reverse": True})
        c.set_x_axis({"num_format": "0%", "max": 1})
        c.set_legend({"none": True})
        c.set_size({"width": 430, "height": 560})
        ws.insert_chart(end + 3, k * 7, c)

    # Model vs market ------------------------------------------------------------------------
    ws = b.sheet("Model vs Market", "Accuracy: model vs bookmakers' closing odds",
                 "Walk-forward backtest (every prediction made using only matches before kickoff). Lower RPS / log loss "
                 "is better. Market = closing odds with the margin removed.")
    acc = ctx["accuracy"]
    end = b.table(ws, acc, 3, fmts={c: "num3" for c in acc.columns if acc[c].dtype != object} | {"Matches": "int"},
                  widths={"Period": 22, "Forecaster": 26})
    if ctx.get("live") is not None and len(ctx["live"]):
        ws.write(end + 2, 0, "This season so far (live, walk-forward)", b.f["h2"])
        b.table(ws, ctx["live"], end + 3, fmts={c: "num3" for c in ctx["live"].columns if ctx["live"][c].dtype != object}
                | {"Matches": "int"}, widths={"Forecaster": 26}, freeze=False)

    # About ----------------------------------------------------------------------------------
    ws = b.sheet("About", "About this workbook")
    ws.set_column(0, 0, 130)
    for i, line in enumerate(ctx["about"]):
        ws.write(2 + i, 0, line, b.f["h2"] if line.startswith("## ") else b.f["wrap"])
        if line.startswith("## "):
            ws.write(2 + i, 0, line[3:], b.f["h2"])
    b.close()
