import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import ledger
from .config import FILES_DIR
from .db import CalendarEvent, Email, init_db, row_dict, session
from .orchestrator import RUNS, Run


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Sutradhar AI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    goal: str
    budget_inr: float = 150000
    deadline: str = "3 weeks"
    language: str = "en"
    scenario: str = "default"  # cassette name; the UI's Demo mode sends "techfest" with LLM_MODE=replay


class FailureRequest(BaseModel):
    node_id: str
    reason: str = "Venue declined"


def _run(run_id: str) -> Run:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@app.post("/runs")
async def create_run(req: RunRequest):
    run = Run(req.goal, req.budget_inr, req.deadline, req.language, req.scenario)
    run.start()
    return {"run_id": run.id}


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    return _run(run_id).view()


def _decide(run_id: str, node_id: str, approve: bool):
    run = _run(run_id)
    try:
        (run.approve if approve else run.reject)(node_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/runs/{run_id}/approve/{node_id}")
async def approve(run_id: str, node_id: str):
    return _decide(run_id, node_id, True)


@app.post("/runs/{run_id}/reject/{node_id}")
async def reject(run_id: str, node_id: str):
    return _decide(run_id, node_id, False)


@app.post("/runs/{run_id}/inject-failure")
async def inject_failure(run_id: str, req: FailureRequest):
    try:
        mode = _run(run_id).inject_failure(req.node_id, req.reason)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "mode": mode}


@app.get("/runs/{run_id}/ledger")
async def get_ledger(run_id: str):
    return ledger.list_for_run(run_id)


@app.get("/runs/{run_id}/outbox")
async def get_outbox(run_id: str):
    with session() as s:
        emails = [row_dict(e) for e in s.query(Email).filter_by(run_id=run_id).order_by(Email.id)]
        events = [row_dict(e) for e in s.query(CalendarEvent).filter_by(run_id=run_id).order_by(CalendarEvent.id)]
    files = sorted(p.name for p in FILES_DIR.glob("*") if f"_{run_id}" in p.name)
    return {"emails": emails, "events": events, "files": files}


@app.post("/ledger/{ledger_id}/undo")
async def undo(ledger_id: int):
    try:
        return ledger.undo(ledger_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/files/{name}")
async def get_file(name: str):
    path = (FILES_DIR / Path(name).name).resolve()
    if path.parent != FILES_DIR.resolve() or not path.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(path, filename=path.name)


@app.websocket("/ws/{run_id}")
async def ws(websocket: WebSocket, run_id: str):
    await websocket.accept()
    run = RUNS.get(run_id)
    if run is None:
        await websocket.close(code=4404)
        return
    q: asyncio.Queue = asyncio.Queue()
    for ev in run.events:  # replay history, then go live (no await between, so nothing is missed)
        q.put_nowait(ev)
    run.subs.add(q)
    try:
        while True:
            await websocket.send_json(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        run.subs.discard(q)
