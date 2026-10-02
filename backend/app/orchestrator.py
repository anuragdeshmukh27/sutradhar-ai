"""LangGraph state machine: plan -> premortem -> select -> (execute | wait | replan | finish) -> select ...

The graph state is just the next route; the mutable run data lives on the Run object so the API
and the graph share it. Everything runs on one asyncio loop, so state changes between awaits are safe."""
import asyncio
import logging
import time
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import critic, executor, ledger, llm, planner, replanner, verifier
from .config import risk_threshold, run_delay, step_delay
from .models import Node, TaskGraph
from .risk import needs_approval

log = logging.getLogger("sutradhar")
MAX_REPLANS = 3
RUNS: dict[str, "Run"] = {}


class State(TypedDict, total=False):
    route: str


class Run:
    def __init__(self, goal: str, budget_inr: float, deadline: str, language: str, scenario: str = "default"):
        self.id = uuid.uuid4().hex[:8]
        self.goal, self.budget_inr, self.deadline = goal, budget_inr, deadline
        self.language, self.scenario = language, scenario
        self.graph = TaskGraph()
        self.status = "created"  # created | running | complete | failed
        self.events: list[dict] = []
        self.subs: set[asyncio.Queue] = set()
        self.decisions: asyncio.Queue = asyncio.Queue()
        self.approved: set[str] = set()
        self.injected: dict[str, str] = {}  # failure injected into a node that is currently running
        self.replans = 0
        self.risk_summary = ""
        self.task: asyncio.Task | None = None
        self.lg = _build_graph(self)
        RUNS[self.id] = self

    # ---- events -------------------------------------------------------------------------------
    def emit(self, type_: str, data: dict | None = None):
        ev = {"type": type_, "data": data or {}, "ts": time.time()}
        self.events.append(ev)
        for q in list(self.subs):
            q.put_nowait(ev)

    def thought(self, agent: str, text: str):
        self.emit("agent_thought", {"agent": agent, "text": text})

    def emit_status(self, n: Node):
        self.emit("node_status", {"node_id": n.id, "status": n.status, "risk": n.risk,
                                  "fail_probability": n.fail_probability, "error": n.error})

    def snapshot(self) -> dict:
        return {"nodes": [n.model_dump() for n in self.graph.nodes], "edges": self.graph.edges()}

    def view(self) -> dict:
        return {"run_id": self.id, "goal": self.goal, "budget_inr": self.budget_inr, "deadline": self.deadline,
                "language": self.language, "status": self.status, "replans": self.replans,
                "risk_summary": self.risk_summary, **self.snapshot()}

    # ---- lifecycle ----------------------------------------------------------------------------
    def start(self):
        self._launch("plan")

    def _launch(self, route: str):
        self.status = "running"
        self.task = asyncio.get_running_loop().create_task(self._drive(route))

    async def _drive(self, route: str):
        try:
            await self.lg.ainvoke({"route": route}, {"recursion_limit": 500})
        except llm.LLMError as exc:
            self.status = "failed"
            self.emit("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - never leave the UI hanging
            log.exception("run crashed")
            self.status = "failed"
            self.emit("error", {"message": f"Something went wrong: {exc}"})

    # ---- human decisions ----------------------------------------------------------------------
    def approve(self, node_id: str):
        n = self._awaiting(node_id)
        self.approved.add(node_id)
        n.status = "pending"
        self.emit_status(n)
        self.decisions.put_nowait(node_id)

    def reject(self, node_id: str):
        n = self._awaiting(node_id)
        n.status, n.error = "flagged", "Rejected by human reviewer"
        self.emit_status(n)
        self.decisions.put_nowait(node_id)

    def _awaiting(self, node_id: str) -> Node:
        n = self.graph.get(node_id)
        if n is None:
            raise KeyError("node not found")
        if n.status != "awaiting_approval":
            raise ValueError("node is not awaiting approval")
        return n

    def inject_failure(self, node_id: str, reason: str) -> str:
        """Fail a node whatever state it is in. Returns "armed" (node has not finished yet: the tool call
        will return `reason` when it executes) or "triggered" (node already finished: re-plan starts now)."""
        n = self.graph.get(node_id)
        if n is None:
            raise KeyError("node not found")
        label = n.subtitle or n.title
        if n.status in ("running", "pending", "awaiting_approval") or (n.status == "flagged" and not n.error):
            self.injected[node_id] = reason  # picked up when the tool call runs / returns
            self.thought("system", f"Failure armed for '{label}': it will fail with '{reason}' when it runs.")
            return "armed"
        # finished (done) or already failed: record the failure and heal now
        ledger.record(self.id, node_id, "system", n.tool, n.tool_args, {"ok": False, "summary": reason},
                      n.reversible)
        n.status, n.error = "flagged", reason
        self.approved.discard(node_id)
        self.emit_status(n)
        self.thought("system", f"Failure injected into '{label}': {reason}")
        if self.task is None or self.task.done():
            self._launch("select")  # run had finished: resume to heal
        else:
            self.decisions.put_nowait(node_id)  # wake the loop if it is waiting for approval
        return "triggered"


# ---- graph nodes ------------------------------------------------------------------------------
def _apply_flags(run: Run, nodes: list[Node]):
    for n in nodes:
        if n.status == "pending" and (n.risk or 0) >= risk_threshold():
            n.status = "flagged"


def _build_graph(run: Run):
    async def plan(_: State) -> State:
        run.thought("planner", "Reading the goal and drafting a task graph...")
        run.graph = await asyncio.to_thread(planner.plan, run.goal, run.budget_inr, run.deadline,
                                            run.language, run.scenario)
        run.thought("planner", f"Plan ready: {len(run.graph.nodes)} steps.")
        run.emit("plan_created", run.snapshot())
        return {}

    async def premortem(_: State) -> State:
        run.thought("critic", "Running a pre-mortem: imagine this plan failed, why?")
        try:
            out = await asyncio.to_thread(critic.assess, run.goal, run.graph.nodes, run.budget_inr, run.scenario, run.language)
            run.risk_summary = out.summary
        except llm.LLMError as exc:
            run.thought("critic", f"Critic unavailable ({exc}); using default risk estimates.")
            for n in run.graph.nodes:
                n.fail_probability = 0.2 if n.reversible else 0.6
                n.risk = n.fail_probability
        _apply_flags(run, run.graph.nodes)
        run.emit("premortem_done", {"summary": run.risk_summary, "risks": [
            {"node_id": n.id, "fail_probability": n.fail_probability, "risk": n.risk,
             "failure_modes": n.failure_modes, "mitigation": n.mitigation} for n in run.graph.nodes]})
        for n in run.graph.nodes:
            if n.status == "flagged":
                run.emit_status(n)
        return {}

    async def select(_: State) -> State:
        g = run.graph
        if any(n.status == "flagged" and n.error for n in g.nodes):
            return {"route": "replan"}
        ready = []
        for n in g.nodes:
            if n.status in ("pending", "flagged") and not n.error and g.deps_done(n):
                if n.id not in run.approved and needs_approval(n.risk or 0, not n.reversible):
                    n.status = "awaiting_approval"
                    run.emit_status(n)
                    why = "irreversible action" if not n.reversible else "high risk"
                    run.emit("approval_needed", {"node_id": n.id, "title": n.title, "subtitle": n.subtitle,
                                                 "risk": n.risk, "reason": why,
                                                 "failure_modes": n.failure_modes})
                else:
                    ready.append(n)
        if ready:
            return {"route": "execute"}
        if any(n.status == "awaiting_approval" for n in g.nodes):
            return {"route": "wait"}
        return {"route": "finish"}

    async def execute(_: State) -> State:
        g = run.graph
        ready = [n for n in g.nodes if n.status in ("pending", "flagged") and not n.error and g.deps_done(n)
                 and (n.id in run.approved or not needs_approval(n.risk or 0, not n.reversible))]
        for n in ready:
            n.status = "running"
            run.emit_status(n)
            run.thought("executor", f"Running '{n.subtitle or n.title}' with {n.tool}")
            await asyncio.sleep(run_delay())
            reason = run.injected.pop(n.id, None)
            res = await asyncio.to_thread(executor.execute_node, run.id, n, run.budget_inr, reason)
            late = run.injected.pop(n.id, None)
            if late:
                res = {**res, "ok": False, "summary": late}
            run.emit("tool_call", {"node_id": n.id, "tool": n.tool, "args": n.tool_args, "ok": res["ok"],
                                   "summary": res["summary"], "ledger_id": res.get("ledger_id")})
            v = await asyncio.to_thread(verifier.verify, n, res, run.scenario, run.language)
            run.emit("verify_result", {"node_id": n.id, "passed": v.passed, "reason": v.reason})
            run.thought("verifier", f"{n.subtitle or n.title}: {'PASS' if v.passed else 'FAIL'}: {v.reason}")
            n.result = {"summary": res["summary"], "data": res.get("data", {}), "ledger_id": res.get("ledger_id")}
            if v.passed:
                n.status, n.error = "done", None
            else:
                n.status, n.error = "flagged", v.reason
            run.emit_status(n)
            await asyncio.sleep(step_delay())
        return {}

    async def wait(_: State) -> State:
        run.thought("system", "Paused: waiting for a human decision.")
        await run.decisions.get()
        return {}

    async def replan(_: State) -> State:
        g = run.graph
        failed = next(n for n in g.nodes if n.status == "flagged" and n.error)
        run.replans += 1
        if run.replans > MAX_REPLANS:
            run.emit("error", {"message": "Too many re-plans; stopping this run."})
            run.status = "failed"
            return {"route": "finish"}
        reason = failed.error
        run.thought("replanner", f"'{failed.subtitle or failed.title}' failed ({reason}). "
                                 "Re-planning only this branch.")
        affected = replanner.affected_ids(g, failed.id)
        for row in ledger.list_for_run(run.id):  # compensate reversible work in the broken branch
            if row["node_id"] in affected and row["status"] == "done" and row["reversible"]:
                try:
                    await asyncio.to_thread(ledger.undo, row["id"])
                    run.thought("replanner", f"Undid {row['tool']} from '{row['node_id']}' (branch is being replaced).")
                except ValueError:
                    pass
        run.approved -= affected
        for i in affected:
            run.injected.pop(i, None)
        diff = await asyncio.to_thread(replanner.replan, run.goal, g, failed.id, reason, run.language,
                                       run.budget_inr, run.scenario)
        new = [n for n in g.nodes if n.id in set(diff.added) | set(diff.changed)]
        try:
            await asyncio.to_thread(critic.assess, run.goal, new, run.budget_inr, run.scenario, run.language)
        except llm.LLMError:
            for n in new:
                n.fail_probability = 0.2 if n.reversible else 0.6
                n.risk = n.fail_probability
        _apply_flags(run, new)
        run.emit("replan_diff", {**diff.model_dump(), **run.snapshot()})
        return {"route": "select"}

    async def finish(_: State) -> State:
        done = sum(n.status == "done" for n in run.graph.nodes)
        if run.status != "failed":
            run.status = "complete" if done == len(run.graph.nodes) else "failed"
        run.emit("run_complete", {"status": run.status, "done": done, "total": len(run.graph.nodes),
                                  "replans": run.replans})
        return {}

    b = StateGraph(State)
    for name, fn in [("plan", plan), ("premortem", premortem), ("select", select), ("execute", execute),
                     ("wait", wait), ("replan", replan), ("finish", finish)]:
        b.add_node(name, fn)
    b.add_conditional_edges(START, lambda s: s["route"], {"plan": "plan", "select": "select"})
    b.add_edge("plan", "premortem")
    b.add_edge("premortem", "select")
    b.add_conditional_edges("select", lambda s: s["route"],
                            {"execute": "execute", "wait": "wait", "replan": "replan", "finish": "finish"})
    b.add_edge("execute", "select")
    b.add_edge("wait", "select")
    b.add_conditional_edges("replan", lambda s: s.get("route", "select"), {"select": "select", "finish": "finish"})
    b.add_edge("finish", END)
    return b.compile()
