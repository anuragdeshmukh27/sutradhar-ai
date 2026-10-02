from . import llm, prompts, tools
from .config import num, today
from .models import Node, PlannerOutput, TaskGraph


def plan(goal: str, budget_inr: float, deadline: str, language: str, scenario: str = "default") -> TaskGraph:
    system = prompts.load("planner", language=language, tools=tools.describe(), today=today())
    user = f"Goal: {goal}\nBudget (INR): {num(budget_inr)}\nDeadline: {deadline}\nLanguage: {language}"
    out = llm.call(user, PlannerOutput, system=system, scenario=scenario, lang=language)
    nodes = []
    for n in out.nodes:
        n = Node(**n.model_dump())
        n.reversible = tools.REGISTRY[n.tool].reversible  # the tool, not the LLM, decides reversibility
        nodes.append(n)
    return TaskGraph(nodes=nodes)
