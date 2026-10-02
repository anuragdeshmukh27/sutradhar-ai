from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

Status = Literal["pending", "running", "done", "flagged", "awaiting_approval"]


class PlanNode(BaseModel):
    id: str
    title: str  # in the user's language
    subtitle: str = ""  # English subtitle
    description: str
    depends_on: list[str] = Field(default_factory=list)
    tool: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    success_criteria: str
    est_cost_inr: float = 0
    reversible: bool = True


def validate_dag(nodes: list[PlanNode], external_ids: frozenset = frozenset()) -> None:
    """Unique ids, known tools, deps exist (in nodes or external_ids), no cycles."""
    from .tools import REGISTRY

    ids = [n.id for n in nodes]
    if len(set(ids)) != len(ids):
        raise ValueError("node ids must be unique")
    known = set(ids) | set(external_ids)
    for n in nodes:
        if n.tool not in REGISTRY:
            raise ValueError(f"node {n.id}: unknown tool '{n.tool}'. Valid tools: {sorted(REGISTRY)}")
        for d in n.depends_on:
            if d not in known:
                raise ValueError(f"node {n.id}: depends_on unknown node '{d}'")
            if d == n.id:
                raise ValueError(f"node {n.id} depends on itself")
    deps = {n.id: [d for d in n.depends_on if d in ids] for n in nodes}
    state: dict[str, int] = {}

    def visit(i: str):
        if state.get(i) == 1:
            raise ValueError("task graph contains a cycle")
        if state.get(i) == 2:
            return
        state[i] = 1
        for d in deps[i]:
            visit(d)
        state[i] = 2

    for i in ids:
        visit(i)


class PlannerOutput(BaseModel):
    nodes: list[PlanNode]

    @model_validator(mode="after")
    def _check(self):
        if not 6 <= len(self.nodes) <= 10:
            raise ValueError(f"plan must have 6-10 nodes, got {len(self.nodes)}")
        validate_dag(self.nodes)
        return self


class NodeRisk(BaseModel):
    node_id: str
    fail_probability: float = Field(ge=0, le=1)
    failure_modes: list[str] = Field(default_factory=list)
    mitigation: str = ""
    checkpoint: Optional[str] = None  # optional suggested checkpoint (advisory)


class CriticOutput(BaseModel):
    risks: list[NodeRisk]
    summary: str


class VerifyOutput(BaseModel):
    passed: bool
    reason: str


class ReplanOutput(BaseModel):
    nodes: list[PlanNode]
    explanation: str = ""

    @model_validator(mode="after")
    def _check(self):
        if not self.nodes:
            raise ValueError("replacement plan must contain at least one node")
        return self


class ReplanDiff(BaseModel):
    failed_node: str
    reason: str
    added: list[str]
    removed: list[str]
    changed: list[str]
    summary: str = ""


class Node(PlanNode):
    status: Status = "pending"
    fail_probability: Optional[float] = None
    failure_modes: list[str] = Field(default_factory=list)
    mitigation: str = ""
    risk: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None  # set when the node failed (drives re-planning)


class TaskGraph(BaseModel):
    nodes: list[Node] = Field(default_factory=list)

    def get(self, node_id: str) -> Optional[Node]:
        return next((n for n in self.nodes if n.id == node_id), None)

    def descendants(self, node_id: str) -> set[str]:
        out: set[str] = set()
        frontier = [node_id]
        while frontier:
            cur = frontier.pop()
            for n in self.nodes:
                if cur in n.depends_on and n.id not in out:
                    out.add(n.id)
                    frontier.append(n.id)
        return out

    def deps_done(self, node: Node) -> bool:
        return all((d := self.get(x)) is not None and d.status == "done" for x in node.depends_on)

    def edges(self) -> list[dict]:
        return [{"source": d, "target": n.id} for n in self.nodes for d in n.depends_on]
