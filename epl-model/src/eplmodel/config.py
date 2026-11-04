"""Project-wide constants: paths, seasons, evaluation periods."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "cache"
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
REPORTS = ROOT / "reports"

# football-data.co.uk season codes. 2015-16 to 2017-18 are burn-in (ratings warm-up only).
SEASONS = ["1516", "1617", "1718", "1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"]
CURRENT = "2627"


def label(code: str) -> str:
    """'2324' -> '2023-24'."""
    return f"20{code[:2]}-{code[2:]}"


# Walk-forward evaluation periods. Parameters are tuned on TUNE only; a change is kept only if it
# improves RPS on BOTH test periods (which were never used for tuning).
TUNE = ["2018-19", "2019-20", "2020-21", "2021-22"]
TEST_A = ["2022-23", "2023-24"]
TEST_B = ["2024-25", "2025-26"]
LIVE = [label(CURRENT)]

# Matches played without (or with heavily restricted) crowds: Project Restart to end of 2020-21.
NO_CROWD_START = "2020-06-01"
NO_CROWD_END = "2021-05-31"

MAX_GOALS = 10   # scoreline grid is computed to 10-10 internally; reports show 0-5 plus "6+"
N_SIMS = 20000
