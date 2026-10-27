import json

import bridge


def call(method, path, body=None):
    r = json.loads(bridge.handle(method, path, json.dumps(body) if body is not None else ""))
    return r["status"], r["body"]


def test_bridge_mirrors_the_server_api():
    call("POST", "/api/demo/reset")
    status, state = call("GET", "/api/state")
    assert status == 200 and state["kpis"]["open"] == 7
    status, ws = call("GET", "/api/exceptions/EX-TRANSFER_LATE-TR-5301")
    assert status == 200 and ws["impact"]["delay_h"] == 48
    status, done = call("POST", "/api/exceptions/EX-TRANSFER_LATE-TR-5301/actions", {"action": "reallocate_orders", "args": {}})
    assert status == 200 and done["state"]["kpis"]["orders_at_risk"] < 8
    assert call("POST", "/api/exceptions/EX-TRANSFER_LATE-TR-5301/actions", {"action": "reallocate_orders"})[0] == 409
    assert call("GET", "/api/track/OR-0")[0] == 404


def test_bridge_next_event_and_assistant():
    call("POST", "/api/demo/reset")
    _, d = call("POST", "/api/demo/next")
    assert d["event"]["record_id"] == "TR-5308" and d["state"]["demo"]["cursor"] == 1
    _, r = call("POST", "/api/assistant", {"question": "What should I do?", "context": {"exception_id": "EX-TRANSFER_LATE-TR-5301"}})
    assert r["tools"] and r["proposals"]
