import pytest

from app import ledger
from app.db import Email, session
from app.executor import execute_node
from app.models import Node
from app.risk import needs_approval, risk_score


def test_risk_gate():
    assert risk_score(0.6, True, 80000, 150000) > 0.8
    assert risk_score(0.1, False, 0, 150000) == pytest.approx(0.1)
    assert needs_approval(0.6, False)  # high risk
    assert needs_approval(0.1, True)  # irreversible always gates
    assert not needs_approval(0.49, False)
    assert needs_approval(0.3, False, threshold=0.25)


def _email_node():
    return Node(id="e", title="e", description="e", tool="send_email", success_criteria="x",
                tool_args={"to": "a@b.c", "subject": "Hi", "body": "b"})


def test_ledger_undo_recalls_email():
    res = execute_node("t1", _email_node(), 1000)
    assert res["ok"]
    row = ledger.list_for_run("t1")[0]
    assert row["status"] == "done" and row["reversible"]
    out = ledger.undo(row["id"])
    assert out["status"] == "undone"
    with session() as s:
        assert s.query(Email).filter_by(run_id="t1").one().status == "recalled"
    with pytest.raises(ValueError):  # cannot undo twice
        ledger.undo(row["id"])


def test_irreversible_cannot_be_undone():
    n = Node(id="v", title="v", description="v", tool="book_venue", success_criteria="x", tool_args={})
    execute_node("t2", n, 1000)
    with pytest.raises(ValueError):
        ledger.undo(ledger.list_for_run("t2")[0]["id"])


def test_failed_tool_is_logged_as_failed():
    n = Node(id="v", title="v", description="v", tool="book_venue", success_criteria="x", tool_args={})
    res = execute_node("t3", n, 1000, injected_reason="Venue declined")
    assert not res["ok"]
    assert ledger.list_for_run("t3")[0]["status"] == "failed"
