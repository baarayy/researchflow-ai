import asyncio
import uuid

import pytest

from app.container import build_container
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from tests.api.conftest import make_client

pytestmark = pytest.mark.db

QUESTION = (
    "Compare open-source LLMs for building AI agents. Evaluate their reasoning, "
    "hardware requirements, licensing and suitability for production."
)


async def wait_for_status(client, sid, statuses, timeout=20.0):
    for _ in range(int(timeout / 0.1)):
        body = (await client.get(f"/api/v1/research/{sid}")).json()
        if body["status"] in statuses:
            return body
        await asyncio.sleep(0.1)
    raise AssertionError(f"session stuck in {body['status']}")


async def start(client, **extra):
    r = await client.post("/api/v1/research", json={"question": QUESTION, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_health(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok" and body["demo_mode"] is True


async def test_full_flow_with_plan_approval(client):
    sid = await start(client)
    body = await wait_for_status(client, sid, {"awaiting_approval"})
    assert body["pending_approval"]["kind"] == "plan_review" and body["tasks"]

    r = await client.post(f"/api/v1/research/{sid}/approve", json={})
    assert r.status_code == 200
    body = await wait_for_status(client, sid, {"completed", "partial", "failed"})
    assert body["status"] == "completed" and body["has_report"]
    assert body["sources"] and body["evidence"]
    assert {e["source_key"] for e in body["evidence"]} <= {s["source_key"] for s in body["sources"]}

    report = (await client.get(f"/api/v1/research/{sid}/report")).json()
    assert report["status"] == "complete" and report["markdown"].startswith("# Research report")

    # The event log is streamed over SSE and ends once the run is terminal.
    async with client.stream("GET", f"/api/v1/research/{sid}/events") as resp:
        text = "".join([chunk async for chunk in resp.aiter_text()])
    assert "event: interrupt" in text and "event: approval" in text and "event: end" in text
    assert text.index("planner") < text.index("report_generator")

    # Replay from a cursor only returns newer events (ids are global, not per session).
    ids = [int(line[4:]) for line in text.splitlines() if line.startswith("id: ")]
    async with client.stream(
        "GET", f"/api/v1/research/{sid}/events", headers={"Last-Event-ID": str(ids[2])}
    ) as resp:
        replay = "".join([chunk async for chunk in resp.aiter_text()])
    assert [int(line[4:]) for line in replay.splitlines() if line.startswith("id: ")] == ids[3:]


async def test_double_approval_and_approval_when_not_paused_conflict(client):
    sid = await start(client)
    await wait_for_status(client, sid, {"awaiting_approval"})
    first, second = await asyncio.gather(
        client.post(f"/api/v1/research/{sid}/approve", json={}),
        client.post(f"/api/v1/research/{sid}/approve", json={}),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    await wait_for_status(client, sid, {"completed", "partial"})
    r = await client.post(f"/api/v1/research/{sid}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


async def test_revise_replans(client):
    sid = await start(client)
    await wait_for_status(client, sid, {"awaiting_approval"})
    r = await client.post(
        f"/api/v1/research/{sid}/revise", json={"feedback": "Add a task on GPU memory"}
    )
    assert r.status_code == 200
    body = await wait_for_status(client, sid, {"awaiting_approval"})
    # wait until the new plan is projected
    for _ in range(50):
        if any("GPU memory" in t["question"] for t in body["tasks"]):
            break
        await asyncio.sleep(0.1)
        body = (await client.get(f"/api/v1/research/{sid}")).json()
    assert any("GPU memory" in t["question"] for t in body["tasks"])


async def test_idempotency_key_prevents_duplicate_runs(client):
    headers = {"Idempotency-Key": "abc-123"}
    a = await client.post("/api/v1/research", json={"question": QUESTION}, headers=headers)
    b = await client.post("/api/v1/research", json={"question": QUESTION}, headers=headers)
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    sessions = (await client.get("/api/v1/sessions")).json()
    assert sessions["total"] == 1


async def test_resume_after_server_restart(container):
    """Pause at approval, throw away the app + runner, approve on a brand-new one."""
    async with await make_client(container) as client:
        sid = await start(client)
        await wait_for_status(client, sid, {"awaiting_approval"})
    await container.close()  # "server stops"

    fresh = await build_container(get_settings(), get_sessionmaker())  # "server restarts"
    try:
        async with await make_client(fresh) as client:
            assert (
                await client.post(f"/api/v1/research/{sid}/approve", json={})
            ).status_code == 200
            body = await wait_for_status(client, sid, {"completed", "partial", "failed"})
            assert body["status"] == "completed"
    finally:
        await fresh.close()


async def test_validation_and_not_found_errors(client):
    r = await client.post("/api/v1/research", json={"question": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = await client.get(f"/api/v1/research/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert (await client.get("/api/v1/research/not-a-uuid")).status_code == 422
    r = await client.post(
        "/api/v1/research", json={"question": QUESTION, "document_ids": [str(uuid.uuid4())]}
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/research", json={"question": QUESTION}, headers={"X-User-Id": "bad id!"}
    )
    assert r.status_code == 401


async def test_report_not_ready_and_sessions_are_per_user(client):
    sid = await start(client)
    await wait_for_status(client, sid, {"awaiting_approval"})
    assert (await client.get(f"/api/v1/research/{sid}/report")).status_code == 404
    other = {"X-User-Id": "someone-else"}
    assert (await client.get(f"/api/v1/research/{sid}", headers=other)).status_code == 404
    assert (
        await client.post(f"/api/v1/research/{sid}/approve", json={}, headers=other)
    ).status_code == 404
    assert (await client.get("/api/v1/sessions", headers=other)).json()["total"] == 0


async def test_sessions_pagination(client):
    for _ in range(3):
        await start(client, require_plan_approval=True)
    page = (await client.get("/api/v1/sessions", params={"limit": 2, "offset": 0})).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    page2 = (await client.get("/api/v1/sessions", params={"limit": 2, "offset": 2})).json()
    assert len(page2["items"]) == 1
    assert (await client.get("/api/v1/sessions", params={"limit": 0})).status_code == 422
