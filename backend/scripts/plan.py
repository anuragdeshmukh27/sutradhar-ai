"""Print the planner's DAG.  Usage (from backend/):
    .venv\\Scripts\\python.exe scripts\\plan.py "<goal>" [--lang en|hi|mr] [--budget 150000] [--deadline "3 weeks"]
    .venv\\Scripts\\python.exe scripts\\plan.py --scenario techfest --lang hi
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app import planner  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("goal", nargs="?")
ap.add_argument("--lang", default="en")
ap.add_argument("--budget", type=float, default=150000)
ap.add_argument("--deadline", default="3 weeks")
ap.add_argument("--scenario")
a = ap.parse_args()

goal, budget, deadline, scen = a.goal, a.budget, a.deadline, "default"
if a.scenario:
    sc = json.loads((Path(__file__).resolve().parents[1] / "scenarios" / f"{a.scenario}.json").read_text(encoding="utf-8"))
    goal, budget, deadline, scen = sc["goals"][a.lang], sc["budget_inr"], sc["deadline"], a.scenario
if not goal:
    ap.error("give a goal or --scenario")

g = planner.plan(goal, budget, deadline, a.lang, scen)
for n in g.nodes:
    dep = ",".join(n.depends_on) or "-"
    print(f"[{n.id}] {n.title} ({n.subtitle})\n    tool={n.tool} deps={dep} cost=₹{n.est_cost_inr:.0f} reversible={n.reversible}")
print(f"\n{len(g.nodes)} nodes, total est cost ₹{sum(n.est_cost_inr for n in g.nodes):.0f}")
