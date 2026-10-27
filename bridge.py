"""Standalone entry point: the same API as server.py, without FastAPI, called straight from JavaScript (Pyodide).

build_standalone.py packs this module with the rest of the Python code into one HTML file. State lives in memory,
so a page reload restores the starting data.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict

import assistant
import engine
import views
from models import shift

OSM = {"name": "OpenStreetMap", "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
       "attribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', "ok": True, "message": ""}
CONFIG = {"tiles": OSM}
STATE = engine.new_state()


def _snap() -> dict:
    return views.snapshot(STATE, CONFIG)


def _done(message: str) -> dict:
    return {"message": message, "state": _snap()}


def _transfer_event(b: dict) -> str:
    t = STATE.transfers[b["transfer_id"]]
    kind = b["kind"]
    if kind == "delay":
        base = max(t.eta or t.planned_arrival, STATE.now)
        hours = int(b.get("hours", 24))
        return engine.manual_event(STATE, "transfer", t.transfer_id, "TRANSFER_ETA_UPDATED", f"Carrier reports a {hours} h delay.", {"new_eta": shift(base, hours)})
    types = {"customs_hold": "TRANSFER_CUSTOMS_HOLD", "customs_released": "TRANSFER_CUSTOMS_RELEASED", "departed": "TRANSFER_DEPARTED",
             "arrived": "TRANSFER_ARRIVED", "received": "TRANSFER_RECEIVED"}
    if kind not in types:
        raise engine.Rejected(f"unknown event {kind}")
    return engine.manual_event(STATE, "transfer", t.transfer_id, types[kind], f"{kind.replace('_', ' ').capitalize()} (simulated).",
                               {"reason": "Documents under review"} if kind == "customs_hold" else {})


def _order_event(b: dict) -> str:
    types = {"scan": "CARRIER_SCAN", "delay": "CARRIER_DELAY", "picked": "ORDER_PICKED", "packed": "ORDER_PACKED", "shipped": "ORDER_SHIPPED", "delivered": "ORDER_DELIVERED"}
    texts = {"scan": "Sorted at a regional centre", "shipped": "Shipped", "delivered": "Delivered"}
    if b["kind"] not in types:
        raise engine.Rejected(f"unknown event {b['kind']}")
    return engine.manual_event(STATE, "order", b["order_id"], types[b["kind"]], f"{b['kind'].capitalize()} (simulated).",
                               {"location": "Regional sort centre"} if b["kind"] == "scan" else {}, texts.get(b["kind"], ""))


def _action(ex_id: str, b: dict) -> str:
    a = b.get("args", {})
    action = b["action"]
    if action == "reallocate_orders":
        return f"Reallocated {len(engine.reallocate_orders(STATE, ex_id))} order lines"
    if action == "repromise_orders":
        return f"New promise dates set for {len(engine.repromise_orders(STATE, ex_id))} orders"
    if action == "emergency_replenishment":
        return f"Emergency transfer {engine.emergency_replenishment(STATE, ex_id, a['source'], a['store'], a['sku'], int(a['qty']))} created"
    if action == "resubmit_order":
        engine.resubmit_order(STATE, STATE.exceptions[ex_id].record_id)
        return "Order resubmitted"
    raise engine.Rejected(f"unsupported action {action}")


def _next() -> dict:
    before_audit, before_events = len(STATE.audit), len(STATE.events)
    message = engine.next_scripted_event(STATE) or "Scenario complete"
    event = asdict(STATE.events[-1]) if len(STATE.events) > before_events else None
    return {"message": message, "event": event, "changes": [asdict(a) for a in STATE.audit[before_audit:]], "state": _snap()}


def _ask(b: dict) -> dict:
    ctx = b.get("context", {})
    reply = assistant.ask(STATE, b["question"], ctx)
    ex_id = ctx.get("exception_id", "")
    engine.audit(STATE, "Assistant", "Question answered", ex_id or "—", f"{b['question']} ({reply.provider}, {len(reply.tool_calls)} tool calls)")
    return {"text": reply.text, "provider": reply.provider, "proposals": [{**p, "exception_id": p.get("exception_id") or ex_id} for p in reply.proposals],
            "tools": [{"tool": c["tool"], "args": c["args"], "result": c["result"]} for c in reply.tool_calls]}


def _route(method: str, path: str, b: dict):
    global STATE
    if method == "GET":
        if path == "/api/state":
            return _snap()
        if m := re.fullmatch(r"/api/exceptions/([^/]+)", path):
            return views.workspace(STATE, m[1])
        if m := re.fullmatch(r"/api/track/([^/]+)", path):
            data = views.tracking(STATE, m[1])
            if data is None:
                raise LookupError("We couldn't find that order.")
            return data
    if method == "POST":
        if m := re.fullmatch(r"/api/exceptions/([^/]+)/assign", path):
            engine.assign(STATE, m[1], b.get("owner", engine.OPERATOR))
            return _done("Assigned to you")
        if m := re.fullmatch(r"/api/exceptions/([^/]+)/resolve", path):
            engine.resolve(STATE, m[1], b.get("note", ""))
            return _done("Exception resolved")
        if m := re.fullmatch(r"/api/exceptions/([^/]+)/actions", path):
            return _done(_action(m[1], b))
        if m := re.fullmatch(r"/api/notifications/([^/]+)/send", path):
            return _done(f"{m[1]}: {engine.approve_and_send(STATE, m[1], b.get('body')).lower()}")
        if m := re.fullmatch(r"/api/notifications/([^/]+)/reject", path):
            engine.reject_notification(STATE, m[1], b.get("note", ""))
            return _done(f"{m[1]} rejected")
        if m := re.fullmatch(r"/api/notifications/([^/]+)/retry", path):
            return _done(f"{m[1]}: {engine.retry_notification(STATE, m[1]).lower()}")
        if m := re.fullmatch(r"/api/orders/([^/]+)/resubmit", path):
            engine.resubmit_order(STATE, m[1])
            return _done("Order resubmitted")
        if m := re.fullmatch(r"/api/orders/([^/]+)/restock", path):
            engine.restock_return(STATE, m[1])
            return _done("Return restocked")
        if path == "/api/demo/next":
            return _next()
        if path == "/api/demo/reset":
            STATE = engine.new_state()
            return _done("Demo data reset")
        if path == "/api/demo/auto-send":
            engine.set_auto_send(STATE, bool(b["enabled"]))
            return _done("Policy updated")
        if path == "/api/simulate/transfer":
            return _done(_transfer_event(b))
        if path == "/api/simulate/order":
            return _done(_order_event(b))
        if path == "/api/simulate/replay":
            original = next((e for e in STATE.events if e.event_id == b["event_id"]), None)
            if original is None:
                raise engine.Rejected(f"unknown event {b['event_id']}")
            return _done(engine.process_event(STATE, original))
        if path == "/api/assistant":
            return _ask(b)
    raise LookupError(f"{method} {path} not found")


def handle(method: str, path: str, body: str = "") -> str:
    """Returns JSON: {"status": int, "body": object}. Mirrors the HTTP status codes of server.py."""
    try:
        return json.dumps({"status": 200, "body": _route(method, path.split("?")[0], json.loads(body) if body else {})})
    except engine.Rejected as exc:
        return json.dumps({"status": 409, "body": {"error": str(exc)}})
    except (KeyError, LookupError) as exc:
        return json.dumps({"status": 404, "body": {"error": str(exc.args[0]) if exc.args else "not found"}})
