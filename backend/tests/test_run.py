"""P2 full-run check (simulated approvals) and P3 self-healing checks."""
import asyncio

from app import ledger
from app.orchestrator import Run


async def wait_for(cond, timeout=10):
    for _ in range(int(timeout / 0.02)):
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out")


def types(run):
    return [e["type"] for e in run.events]


async def _start():
    run = Run("Run a tech fest", 150000, "3 weeks", "en")
    run.start()
    await wait_for(lambda: any(n.status == "awaiting_approval" for n in run.graph.nodes))
    return run


def test_full_run_pauses_for_approval_then_completes():
    async def go():
        run = await _start()
        assert "plan_created" in types(run) and "premortem_done" in types(run) and "approval_needed" in types(run)
        assert run.graph.get("venue").status == "awaiting_approval"
        assert run.graph.get("run_event").status == "pending"  # downstream is held back
        run.approve("venue")
        await wait_for(lambda: run.status != "running")
        assert run.status == "complete"
        assert all(n.status == "done" for n in run.graph.nodes)
        assert types(run)[-1] == "run_complete"
        assert any(r["tool"] == "send_email" for r in ledger.list_for_run(run.id))

    asyncio.run(go())


def test_reject_triggers_replan():
    async def go():
        run = await _start()
        run.reject("venue")
        await wait_for(lambda: "replan_diff" in types(run))
        assert run.graph.get("venue") is None and run.graph.get("venue_alt") is not None

    asyncio.run(go())


def test_selfheal_only_touches_failed_branch():
    async def go():
        run = await _start()
        run.approve("venue")
        await wait_for(lambda: run.status == "complete")
        before = {n.id: n.model_dump() for n in run.graph.nodes}
        done_before = {k for k, v in before.items() if v["status"] == "done"}

        run.inject_failure("venue", "Venue declined")
        await wait_for(lambda: "replan_diff" in types(run))
        diff = next(e for e in run.events if e["type"] == "replan_diff")["data"]
        assert diff["failed_node"] == "venue"
        assert set(diff["removed"]) == {"venue"}
        assert set(diff["added"]) == {"venue_alt"}
        assert set(diff["changed"]) == {"permissions", "run_event"}

        # nodes outside the failed sub-graph are byte-for-byte untouched
        untouched = done_before - {"venue", "permissions", "run_event"}
        assert untouched == {"research", "tracker", "poster", "invite"}
        for i in untouched:
            assert run.graph.get(i).model_dump() == before[i]

        # replacement venue is a new risky step: it needs approval again, then the run completes
        await wait_for(lambda: run.graph.get("venue_alt").status == "awaiting_approval")
        run.approve("venue_alt")
        await wait_for(lambda: run.status == "complete")
        assert run.replans == 1
        assert all(n.status == "done" for n in run.graph.nodes)

    asyncio.run(go())
