"""Threadline Operations API and static frontend. Run: uvicorn server:app --port 8601 (or python server.py)."""
from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import assistant
import engine
import tiles
import views
from models import shift

ROOT = Path(__file__).parent
app = FastAPI(title="Threadline Operations", docs_url="/api/docs", redoc_url=None)
LOCK = threading.RLock()
STATE = engine.load_state()


class Note(BaseModel):
    note: str = ""


class Owner(BaseModel):
    owner: str = engine.OPERATOR


class Action(BaseModel):
    action: str
    args: dict[str, Any] = {}


class Body(BaseModel):
    body: str | None = None


class Flag(BaseModel):
    enabled: bool


class TransferEvent(BaseModel):
    transfer_id: str
    kind: str
    hours: int = 24


class OrderEvent(BaseModel):
    order_id: str
    kind: str


class Replay(BaseModel):
    event_id: str


class Question(BaseModel):
    question: str
    context: dict[str, str] = {}


@app.exception_handler(engine.Rejected)
async def rejected(_, exc: engine.Rejected):
    return JSONResponse({"error": str(exc)}, status_code=409)


@app.exception_handler(KeyError)
async def missing(_, exc: KeyError):
    return JSONResponse({"error": f"{exc.args[0]} not found"}, status_code=404)


def mutate(fn, *args) -> dict:
    """Run a state change under the lock, persist it, and return the result message with a fresh snapshot."""
    with LOCK:
        result = fn(STATE, *args)
        engine.save_state(STATE)
        return {"message": result if isinstance(result, str) else "Done", "state": snapshot()}


def snapshot() -> dict:
    return views.snapshot(STATE, {"tiles": tiles.config()})


@app.get("/api/state")
def get_state():
    with LOCK:
        return snapshot()


@app.get("/api/exceptions/{ex_id}")
def get_workspace(ex_id: str):
    with LOCK:
        return views.workspace(STATE, ex_id)


@app.post("/api/exceptions/{ex_id}/assign")
def assign(ex_id: str, body: Owner):
    return mutate(lambda s: (engine.assign(s, ex_id, body.owner), "Assigned to you")[1])


@app.post("/api/exceptions/{ex_id}/resolve")
def resolve(ex_id: str, body: Note):
    return mutate(lambda s: (engine.resolve(s, ex_id, body.note), "Exception resolved")[1])


@app.post("/api/exceptions/{ex_id}/actions")
def run_action(ex_id: str, body: Action):
    def do(s):
        a = body.args
        if body.action == "reallocate_orders":
            return f"Reallocated {len(engine.reallocate_orders(s, ex_id))} order lines"
        if body.action == "repromise_orders":
            return f"New promise dates set for {len(engine.repromise_orders(s, ex_id))} orders"
        if body.action == "emergency_replenishment":
            tid = engine.emergency_replenishment(s, ex_id, a["source"], a["store"], a["sku"], int(a["qty"]))
            return f"Emergency transfer {tid} created"
        if body.action == "resubmit_order":
            engine.resubmit_order(s, s.exceptions[ex_id].record_id)
            return "Order resubmitted"
        raise engine.Rejected(f"unsupported action {body.action}")
    return mutate(do)


@app.post("/api/notifications/{nid}/send")
def send(nid: str, body: Body):
    return mutate(lambda s: f"{nid}: {engine.approve_and_send(s, nid, body.body).lower()}")


@app.post("/api/notifications/{nid}/reject")
def reject(nid: str, body: Note):
    return mutate(lambda s: (engine.reject_notification(s, nid, body.note), f"{nid} rejected")[1])


@app.post("/api/notifications/{nid}/retry")
def retry(nid: str):
    return mutate(lambda s: f"{nid}: {engine.retry_notification(s, nid).lower()}")


@app.post("/api/orders/{order_id}/resubmit")
def resubmit(order_id: str):
    return mutate(lambda s: (engine.resubmit_order(s, order_id), "Order resubmitted")[1])


@app.post("/api/orders/{order_id}/restock")
def restock(order_id: str):
    return mutate(lambda s: (engine.restock_return(s, order_id), "Return restocked")[1])


@app.post("/api/demo/next")
def next_event():
    """Release the next scenario event and report what it touched and what changed, so the UI can jump to it."""
    with LOCK:
        before_audit, before_events = len(STATE.audit), len(STATE.events)
        message = engine.next_scripted_event(STATE) or "Scenario complete"
        engine.save_state(STATE)
        event = asdict(STATE.events[-1]) if len(STATE.events) > before_events else None
        changes = [asdict(a) for a in STATE.audit[before_audit:]]
        return {"message": message, "event": event, "changes": changes, "state": snapshot()}


@app.post("/api/demo/reset")
def reset():
    global STATE
    with LOCK:
        STATE = engine.reset_state()
        engine.save_state(STATE)
        return {"message": "Demo data reset", "state": snapshot()}


@app.post("/api/demo/auto-send")
def auto_send(body: Flag):
    return mutate(lambda s: (engine.set_auto_send(s, body.enabled), "Policy updated")[1])


@app.post("/api/simulate/transfer")
def sim_transfer(body: TransferEvent):
    def do(s):
        t = s.transfers[body.transfer_id]
        if body.kind == "delay":
            base = max(t.eta or t.planned_arrival, s.now)
            return engine.manual_event(s, "transfer", t.transfer_id, "TRANSFER_ETA_UPDATED", f"Carrier reports a {body.hours} h delay.",
                                       {"new_eta": shift(base, body.hours)})
        types = {"customs_hold": "TRANSFER_CUSTOMS_HOLD", "customs_released": "TRANSFER_CUSTOMS_RELEASED", "departed": "TRANSFER_DEPARTED",
                 "arrived": "TRANSFER_ARRIVED", "received": "TRANSFER_RECEIVED"}
        if body.kind not in types:
            raise engine.Rejected(f"unknown event {body.kind}")
        return engine.manual_event(s, "transfer", t.transfer_id, types[body.kind], f"{body.kind.replace('_', ' ').capitalize()} (simulated).",
                                   {"reason": "Documents under review"} if body.kind == "customs_hold" else {})
    return mutate(do)


@app.post("/api/simulate/order")
def sim_order(body: OrderEvent):
    types = {"scan": "CARRIER_SCAN", "delay": "CARRIER_DELAY", "picked": "ORDER_PICKED", "packed": "ORDER_PACKED", "shipped": "ORDER_SHIPPED",
             "delivered": "ORDER_DELIVERED"}
    texts = {"scan": "Sorted at a regional centre", "shipped": "Shipped", "delivered": "Delivered"}

    def do(s):
        if body.kind not in types:
            raise engine.Rejected(f"unknown event {body.kind}")
        return engine.manual_event(s, "order", body.order_id, types[body.kind], f"{body.kind.capitalize()} (simulated).",
                                   {"location": "Regional sort centre"} if body.kind == "scan" else {}, texts.get(body.kind, ""))
    return mutate(do)


@app.post("/api/simulate/replay")
def replay(body: Replay):
    def do(s):
        original = next((e for e in s.events if e.event_id == body.event_id), None)
        if original is None:
            raise engine.Rejected(f"unknown event {body.event_id}")
        return engine.process_event(s, original)
    return mutate(do)


@app.post("/api/assistant")
def ask(body: Question):
    with LOCK:
        reply = assistant.ask(STATE, body.question, body.context)
        ex_id = body.context.get("exception_id", "")
        proposals = [{**p, "exception_id": p.get("exception_id") or ex_id} for p in reply.proposals]
        engine.audit(STATE, "Assistant", "Question answered", ex_id or "—", f"{body.question} ({reply.provider}, {len(reply.tool_calls)} tool calls)")
        engine.save_state(STATE)
        return {"text": reply.text, "provider": reply.provider, "proposals": proposals,
                "tools": [{"tool": c["tool"], "args": c["args"], "result": c["result"]} for c in reply.tool_calls]}


@app.get("/api/track/{order_id}")
def track(order_id: str):
    with LOCK:
        data = views.tracking(STATE, order_id)
    return data if data else JSONResponse({"error": "We couldn't find that order."}, status_code=404)


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
class NoCacheStatic(StaticFiles):
    """Frontend files are small and edited often; always revalidate."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", NoCacheStatic(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8601)
