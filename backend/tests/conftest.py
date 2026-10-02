import os
import re
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="sutradhar_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["FILES_DIR"] = str(_tmp / "files")
os.environ["STEP_DELAY"] = "0"
os.environ["RISK_THRESHOLD"] = "0.5"
os.environ["FAILURE_INJECTION"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import llm  # noqa: E402
from app.db import init_db  # noqa: E402
from app.models import CriticOutput, NodeRisk, PlannerOutput, PlanNode, ReplanOutput, VerifyOutput  # noqa: E402


def N(id, tool, deps=(), cost=0, **args):
    return PlanNode(id=id, title=id, subtitle=id, description=id, depends_on=list(deps), tool=tool,
                    tool_args=args, success_criteria="done", est_cost_inr=cost)


PLAN = [
    N("research", "web_search", query="venues"),
    N("tracker", "update_tracker", row={"item": "venue", "cost": 80000}),
    N("venue", "book_venue", ["research"], 80000, venue="Hall A"),
    N("permissions", "request_permission", ["venue"], authority="Principal", purpose="fest"),
    N("poster", "create_poster_brief", event_name="Fest"),
    N("invite", "send_email", ["poster"], to="students@x.in", subject="Join us", body="hi"),
    N("run_event", "schedule_event", ["venue", "permissions"], title="Fest", date="D1"),
]


def fake_call(prompt, schema, system="", scenario="default"):
    if schema is PlannerOutput:
        return PlannerOutput(nodes=PLAN)
    if schema is CriticOutput:
        ids = re.findall(r'"node_id": "([^"]+)"', prompt)
        return CriticOutput(summary="Venue is the biggest risk.", risks=[
            NodeRisk(node_id=i, fail_probability=0.6 if i.startswith("venue") else 0.1,
                     failure_modes=["declined"], mitigation="have a backup") for i in ids])
    if schema is VerifyOutput:
        return VerifyOutput(passed=True, reason="looks good")
    if schema is ReplanOutput:
        return ReplanOutput(explanation="Switched to an alternate venue.", nodes=[
            N("venue_alt", "book_venue", ["research"], 70000, venue="Hall B"),
            N("permissions", "request_permission", ["venue_alt"], authority="Principal", purpose="fest at Hall B"),
            N("run_event", "schedule_event", ["venue_alt", "permissions"], title="Fest", date="D1"),
        ])
    raise AssertionError(schema)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    init_db()
    monkeypatch.setattr(llm, "call", fake_call)
