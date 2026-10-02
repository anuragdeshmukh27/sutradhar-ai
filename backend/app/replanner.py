import json

from . import llm, prompts, tools
from .config import today
from .models import Node, PlanNode, ReplanDiff, ReplanOutput, TaskGraph, enforce_final_deps, validate_dag


def affected_ids(graph: TaskGraph, failed_id: str) -> set[str]:
    return {failed_id} | graph.descendants(failed_id)


def replan(goal: str, graph: TaskGraph, failed_id: str, reason: str, language: str, budget_inr: float,
           scenario: str = "default") -> ReplanDiff:
    """Regenerate only the failed node + its downstream sub-graph. Mutates `graph`; nodes outside the
    affected set are never touched. Returns the diff."""
    affected = affected_ids(graph, failed_id)
    kept = [n for n in graph.nodes if n.id not in affected]
    kept_ids = {n.id for n in kept}
    old = {n.id: n for n in graph.nodes if n.id in affected}

    plan_fields = set(PlanNode.model_fields)
    user = (
        f"Goal: {goal}\nLanguage: {language}\nTotal budget (INR): {budget_inr}\n"
        f"FAILED step: {failed_id}\nFailure reason: {reason}\n"
        f"Steps to regenerate (failed step + its dependents):\n"
        f"{json.dumps([n.model_dump(include=plan_fields) for n in old.values()], ensure_ascii=False)}\n"
        f"Kept steps (do not change; you may depend on them):\n"
        f"{json.dumps([{'id': n.id, 'title': n.subtitle or n.title} for n in kept], ensure_ascii=False)}"
    )
    out = llm.call(user, ReplanOutput, scenario=scenario,
                   system=prompts.load("replanner", language=language, tools=tools.describe(), today=today()))

    new_nodes: list[Node] = []
    for pn in out.nodes:
        if pn.id in kept_ids:  # never overwrite a kept node
            continue
        n = Node(**pn.model_dump())
        n.depends_on = [d for d in n.depends_on if d in kept_ids or d in {x.id for x in out.nodes}]
        new_nodes.append(n)
    enforce_final_deps(new_nodes, [*kept, *new_nodes])
    validate_dag(new_nodes, frozenset(kept_ids))
    for n in new_nodes:
        n.reversible = tools.REGISTRY[n.tool].reversible

    new_ids = {n.id for n in new_nodes}
    changed = [i for i in old if i in new_ids and (i == failed_id or _differs(old[i], next(n for n in new_nodes if n.id == i)))]
    diff = ReplanDiff(
        failed_node=failed_id, reason=reason,
        added=[n.id for n in new_nodes if n.id not in old],
        removed=[i for i in old if i not in new_ids],
        changed=changed, summary=out.explanation,
    )
    graph.nodes = kept + new_nodes
    return diff


def _differs(a: Node, b: Node) -> bool:
    keys = ("title", "description", "tool", "tool_args", "depends_on", "success_criteria")
    return any(getattr(a, k) != getattr(b, k) for k in keys)
