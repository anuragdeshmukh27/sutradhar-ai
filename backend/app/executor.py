from . import ledger
from .models import Node
from .tools import REGISTRY


def execute_node(run_id: str, node: Node, budget_inr: float, injected_reason: str | None = None) -> dict:
    """Run one node through the tool registry and log it in the ledger. Never raises."""
    tool = REGISTRY.get(node.tool)
    if tool is None:
        result = {"ok": False, "summary": f"Unknown tool '{node.tool}'", "data": {}, "undo_payload": {}}
    elif injected_reason:
        result = {"ok": False, "summary": injected_reason, "data": {}, "undo_payload": {}}
    else:
        try:
            result = tool.run(node.tool_args, {"run_id": run_id, "node_id": node.id, "budget_inr": budget_inr})
        except Exception as exc:  # noqa: BLE001 - a crashing tool is a failed step, not a crashed run
            result = {"ok": False, "summary": f"Tool error: {exc}", "data": {}, "undo_payload": {}}
    row = ledger.record(run_id, node.id, "executor", node.tool, node.tool_args, result,
                        tool.reversible if tool else False)
    result["ledger_id"] = row["id"]
    return result
