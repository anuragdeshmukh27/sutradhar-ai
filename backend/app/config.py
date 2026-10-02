import datetime
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FILES_DIR = Path(os.getenv("FILES_DIR", BACKEND_DIR / "files"))


def risk_threshold() -> float:
    return float(os.getenv("RISK_THRESHOLD", "0.5"))


def step_delay() -> float:
    return float(os.getenv("STEP_DELAY", "0.8"))


def today() -> str:
    """ISO date injected into planner/replanner prompts (override with TODAY_OVERRIDE for tests)."""
    return os.getenv("TODAY_OVERRIDE") or datetime.date.today().isoformat()
