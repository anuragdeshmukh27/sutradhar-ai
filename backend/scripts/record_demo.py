"""Record the demo cassette (needs a live LLM key).  Usage (from backend/):
    .venv\Scripts\python.exe scripts\record_demo.py          # records en, hi, mr into cassettes/techfest.json
Each language runs the full flow: plan -> approve -> venue fails ("Venue declined") -> re-plan -> complete.
Then run with --check to prove the cassette replays with no network."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
CHECK = "--check" in sys.argv
os.environ["LLM_MODE"] = "replay" if CHECK else "record"
os.environ["STEP_DELAY"] = os.environ["RUN_DELAY"] = "0"

from app.db import init_db  # noqa: E402
from app.orchestrator import Run  # noqa: E402

SC = json.loads((Path(__file__).resolve().parents[1] / "scenarios" / "techfest.json").read_text(encoding="utf-8"))


async def one(lang: str):
    run = Run(SC["goals"][lang], SC["budget_inr"], SC["deadline"], lang, "techfest")
    run.start()
    venue = injected = None
    for _ in range(1200):
        await asyncio.sleep(0.1)
        for n in run.graph.nodes:
            if n.status == "awaiting_approval":
                run.approve(n.id)
        v = next((n for n in run.graph.nodes if n.tool == "book_venue"), None)
        if v and v.status == "done" and not injected:
            injected = v.id
            run.inject_failure(v.id, "Venue declined")
        if run.task and run.task.done() and run.status in ("complete", "failed") and (injected or CHECK is False and run.status == "failed"):
            break
    done = sum(n.status == "done" for n in run.graph.nodes)
    print(f"[{lang}] status={run.status} replans={run.replans} nodes={done}/{len(run.graph.nodes)}")
    for e in run.events:
        if e["type"] == "error":
            print("   error:", e["data"]["message"])
        if os.getenv("VERBOSE") and e["type"] == "agent_thought":
            print("   ", e["data"]["agent"], e["data"]["text"][:150])
    return run.status == "complete" and run.replans == 1


async def main():
    init_db()
    ok = [await one(l) for l in ("en", "hi", "mr")]
    print("ALL OK" if all(ok) else "SOME FAILED")
    sys.exit(0 if all(ok) else 1)

asyncio.run(main())
