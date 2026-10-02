from .config import risk_threshold


def risk_score(fail_probability: float, irreversible: bool, est_cost_inr: float, budget_inr: float) -> float:
    """risk = f(fail_probability, irreversible, est_cost_inr), capped at 1."""
    cost_share = min(1.0, est_cost_inr / budget_inr) if budget_inr > 0 else 0.0
    return min(1.0, fail_probability + 0.15 * irreversible + 0.15 * cost_share)


def needs_approval(risk: float, irreversible: bool, threshold: float | None = None) -> bool:
    t = risk_threshold() if threshold is None else threshold
    return irreversible or risk >= t
