"""Full demo flow through the HTTP API + WebSocket with the network blocked and a bogus API key.

Mirrors what the browser does: sample goal from GET /scenarios/techfest, POST /runs with scenario=techfest,
approve over HTTP, Simulate failure (before and after the venue runs), re-plan, complete. Uses the real
recorded cassette (backend/cassettes/techfest.json) and the real llm.call (conftest fakes it for other tests)."""
import faulthandler
import ipaddress
import socket

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.main import app

REAL_CALL = llm.call  # captured at import, before conftest's autouse fixture swaps in the fake
LANGS = ["en", "hi", "mr"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(llm, "call", REAL_CALL)
    monkeypatch.setenv("GEMINI_API_KEY", "bogus")
    monkeypatch.setenv("LLM_MODE", "live")  # the UI default; Demo mode must replay regardless
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    def local(host) -> bool:
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host in ("localhost", "testserver", "")

    real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect

    def blocked_getaddrinfo(host, *a, **k):
        if local(host):
            return real_getaddrinfo(host, *a, **k)
        raise socket.gaierror(11001, "getaddrinfo failed (network blocked by test)")

    def blocked_connect(self, address):
        if isinstance(address, tuple) and not local(address[0]):
            raise OSError("network blocked by test")
        return real_connect(self, address)

    def no_provider(*_a, **_k):
        raise AssertionError("demo mode must never create a live LLM provider")

    monkeypatch.setattr(socket, "getaddrinfo", blocked_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(llm, "_provider", no_provider)
    faulthandler.dump_traceback_later(180, exit=True)  # a hung WebSocket read would otherwise block forever
    yield
    faulthandler.cancel_dump_traceback_later()


def drive(client: TestClient, run_id: str, inject: str):
    """Follow the run over the WebSocket like the UI. inject: 'before' | 'after' the venue has run."""
    events, injected, replans = [], False, 0
    with client.websocket_connect(f"/ws/{run_id}") as ws:
        while True:
            ev = ws.receive_json()
            events.append(ev)
            t, d = ev["type"], ev["data"]
            if t == "approval_needed":
                if inject == "before" and not injected and "venue" in d["node_id"]:
                    injected = True
                    assert client.post(f"/runs/{run_id}/inject-failure",
                                       json={"node_id": d["node_id"], "reason": "Venue declined"}).json()["mode"] == "armed"
                client.post(f"/runs/{run_id}/approve/{d['node_id']}").raise_for_status()
            elif t == "node_status" and inject == "after" and not injected and d["status"] == "done":
                node = next(n for n in client.get(f"/runs/{run_id}").json()["nodes"] if n["id"] == d["node_id"])
                if node["tool"] == "book_venue":
                    injected = True
                    r = client.post(f"/runs/{run_id}/inject-failure", json={"node_id": node["id"], "reason": "Venue declined"})
                    assert r.json()["mode"] == "triggered"
            elif t == "replan_diff":
                replans += 1
            elif t == "error":
                pytest.fail(f"error event: {d['message']}")
            elif t == "run_complete" and replans >= 1:
                return events


@pytest.mark.parametrize("inject", ["before", "after"])
@pytest.mark.parametrize("lang", LANGS)
def test_full_demo_flow_offline(lang, inject):
    with TestClient(app) as client:
        sc = client.get("/scenarios/techfest").json()
        body = {"goal": sc["goals"][lang], "budget_inr": sc["budget_inr"], "deadline": sc["deadline"],
                "language": lang, "scenario": "techfest"}
        run_id = client.post("/runs", json=body).json()["run_id"]
        events = drive(client, run_id, inject)
        types = [e["type"] for e in events]
        assert types.index("plan_created") < types.index("premortem_done") < types.index("approval_needed")
        diff = next(e["data"] for e in events if e["type"] == "replan_diff")
        assert diff["failed_node"] and diff["added"] or diff["changed"]
        final = events[-1]["data"]
        assert final["status"] == "complete" and final["done"] == final["total"] >= 6
        view = client.get(f"/runs/{run_id}").json()
        assert all(n["status"] == "done" for n in view["nodes"])


def test_user_edited_goal_and_float_budget_still_replays():
    """A goal the cassette never saw must fall back to the closest recorded response, not go live."""
    with TestClient(app) as client:
        body = {"goal": "Organise a 2-day technical festival for about 300 students, budget ₹1.5 lakh, in 3 weeks.",
                "budget_inr": 150000.0, "deadline": "3 weeks", "language": "en", "scenario": "techfest"}
        run_id = client.post("/runs", json=body).json()["run_id"]
        events = drive(client, run_id, "after")
        assert events[-1]["data"]["status"] == "complete"


def test_network_error_message_is_friendly():
    assert llm._is_network_error(socket.gaierror(11001, "getaddrinfo failed"))
    assert llm._is_network_error(RuntimeError("x") if False else ConnectionError("down"))
