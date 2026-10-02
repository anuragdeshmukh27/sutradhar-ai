from .db import LedgerRow, row_dict, session
from .tools import REGISTRY


def record(run_id: str, node_id: str, agent: str, tool: str, args: dict, result: dict, reversible: bool) -> dict:
    ok = bool(result.get("ok"))
    with session() as s:
        row = LedgerRow(run_id=run_id, node_id=node_id, agent=agent, tool=tool, args=args, result=result,
                        reversible=reversible, undo_payload=result.get("undo_payload", {}),
                        status="done" if ok else "failed")
        s.add(row)
        s.flush()
        return row_dict(row)


def list_for_run(run_id: str) -> list[dict]:
    with session() as s:
        rows = s.query(LedgerRow).filter_by(run_id=run_id).order_by(LedgerRow.id).all()
        return [row_dict(r) for r in rows]


def undo(ledger_id: int) -> dict:
    """Call the tool's undo for a ledger row. Returns the updated row (raises ValueError if not undoable)."""
    with session() as s:
        row = s.get(LedgerRow, ledger_id)
        if row is None:
            raise ValueError("ledger entry not found")
        if row.status != "done":
            raise ValueError(f"cannot undo an entry with status '{row.status}'")
        if not row.reversible:
            raise ValueError("this action is irreversible")
        res = REGISTRY[row.tool].undo(row_dict(row))
        if not res.get("ok"):
            raise ValueError(res.get("summary", "undo failed"))
        row.status = "undone"
        return row_dict(row)
