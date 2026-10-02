import json

from . import llm, prompts
from .models import CriticOutput, Node
from .risk import risk_score


def assess(goal: str, nodes: list[Node], budget_inr: float, scenario: str = "default") -> CriticOutput:
    """Pre-mortem: annotate `nodes` in place with fail_probability, failure_modes, mitigation, risk."""
    brief = [{"node_id": n.id, "title": n.subtitle or n.title, "tool": n.tool, "depends_on": n.depends_on,
              "est_cost_inr": n.est_cost_inr, "reversible": n.reversible, "success_criteria": n.success_criteria}
             for n in nodes]
    user = f"Goal: {goal}\nBudget (INR): {budget_inr}\nPlan nodes:\n{json.dumps(brief, ensure_ascii=False)}"
    out = llm.call(user, CriticOutput, system=prompts.load("critic"), scenario=scenario)
    by_id = {r.node_id: r for r in out.risks}
    for n in nodes:
        r = by_id.get(n.id)
        n.fail_probability = r.fail_probability if r else 0.2
        n.failure_modes = r.failure_modes if r else []
        n.mitigation = r.mitigation if r else ""
        n.risk = risk_score(n.fail_probability, not n.reversible, n.est_cost_inr, budget_inr)
    return out
