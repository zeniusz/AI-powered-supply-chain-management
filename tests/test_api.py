import pytest
from fastapi.testclient import TestClient

import server

LATE = "EX-TRANSFER_LATE-TR-5301"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server.engine, "STATE_FILE", server.engine.STATE_FILE.with_name(".test_state.json"))
    monkeypatch.setattr(server.tiles, "config", lambda: {"name": "test", "url": "", "attribution": "", "ok": True, "message": ""})
    c = TestClient(server.app)
    c.post("/api/demo/reset")
    yield c
    server.engine.STATE_FILE.unlink(missing_ok=True)


def test_snapshot_has_everything_the_frontend_needs(client):
    s = client.get("/api/state").json()
    assert s["kpis"]["open"] == 7 and s["kpis"]["p1"] == 2
    assert {"exceptions", "transfers", "facilities", "orders", "positions", "notifications", "events", "audit", "skus"} <= set(s)
    assert next(e for e in s["exceptions"] if e["id"] == LATE)["priority"] == "P1"


def test_workspace_returns_impact_and_options(client):
    w = client.get(f"/api/exceptions/{LATE}").json()
    assert w["impact"]["delay_h"] == 48 and len(w["impact"]["orders"]) == 7
    assert {o["action"] for o in w["assessment"]["options"]} >= {"reallocate_orders", "emergency_replenishment"}


def test_action_flow_updates_state_and_second_attempt_is_a_clear_error(client):
    r = client.post(f"/api/exceptions/{LATE}/actions", json={"action": "reallocate_orders"})
    assert r.status_code == 200 and r.json()["state"]["kpis"]["orders_at_risk"] < 8
    again = client.post(f"/api/exceptions/{LATE}/actions", json={"action": "reallocate_orders"})
    assert again.status_code == 409 and "error" in again.json()


def test_next_event_reports_the_record_it_touched(client):
    d = client.post("/api/demo/next").json()
    assert d["event"]["record_id"] == "TR-5308" and d["state"]["demo"]["cursor"] == 1
    assert any(c["action"] == "Event applied" for c in d["changes"])


def test_replayed_event_is_reported_as_duplicate(client):
    client.post("/api/simulate/transfer", json={"transfer_id": "TR-5301", "kind": "delay", "hours": 6})
    first = next(e for e in client.get("/api/state").json()["events"] if e["event_type"] == "TRANSFER_ETA_UPDATED" and e["event_id"].startswith("EV-M"))
    r = client.post("/api/simulate/replay", json={"event_id": first["event_id"]}).json()
    assert r["message"] == "duplicate ignored"


def test_customer_tracking_exposes_no_internal_fields(client):
    d = client.get("/api/track/OR-20491").json()
    assert set(d) == {"order_id", "stage", "channel", "expected_by", "updated", "carrier", "tracking_code", "collect_at", "items", "timeline"}
    blob = str(d)
    assert "TR-" not in blob and "DC-" not in blob and "OVS-OLV" not in blob
    assert client.get("/api/track/OR-0").status_code == 404


def test_approval_sends_customer_message_once(client):
    n = next(n for n in client.get("/api/state").json()["notifications"] if n["status"] == "Awaiting approval")
    ok = client.post(f"/api/notifications/{n['notification_id']}/send", json={"body": "Edited"})
    assert ok.status_code == 200
    assert client.post(f"/api/notifications/{n['notification_id']}/send", json={}).status_code == 409


def test_assistant_answers_from_tools_and_proposes_without_executing(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/api/assistant", json={"question": "What should I do?", "context": {"exception_id": LATE}}).json()
    assert r["tools"] and r["proposals"] and all(p["exception_id"] == LATE for p in r["proposals"])
    assert client.get("/api/state").json()["kpis"]["orders_at_risk"] == 8  # nothing executed
