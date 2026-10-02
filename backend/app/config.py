import datetime
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FILES_DIR = Path(os.getenv("FILES_DIR", BACKEND_DIR / "files"))


def risk_threshold() -> float:
    return float(os.getenv("RISK_THRESHOLD", "0.5"))


def step_delay() -> float:
    return float(os.getenv("STEP_DELAY", "1.4"))


def run_delay() -> float:
    """Pause while a node shows as running, so the audience can see it."""
    return float(os.getenv("RUN_DELAY", "1.0"))


def num(x: float) -> str:
    """Format a number for prompts: 150000.0 and 150000 must hash the same (cassette keys)."""
    return str(int(x)) if float(x).is_integer() else str(x)


def today() -> str:
    """ISO date injected into planner/replanner prompts (override with TODAY_OVERRIDE for tests)."""
    return os.getenv("TODAY_OVERRIDE") or datetime.date.today().isoformat()
