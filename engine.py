"""Event processing, operator actions, audit trail and demo persistence. All state changes go through here."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from comms import deliver, sync_notifications
from domain import (HUB, DC_HANDLING_H, DISPATCH_PREP_H, delayed_schedule, detect_exceptions, position, reallocation_candidates, road_hours, stock_record,
                    transfer_impact, validate_inventory)
from models import AuditEntry, Event, OpsException, State, Transfer, TransferLine, nice, shift, state_from_dict, ts
from seed import SCRIPT, SEED_VERSION, build_seed

STATE_FILE = Path(__file__).parent / ".demo_state.json"
OPERATOR = "You"


class Rejected(Exception):
    """An event or action that would create an invalid state."""


# ---------- bookkeeping ----------
def _next_id(state: State, prefix: str) -> str:
    state.seq += 1
    return f"{prefix}-{state.seq:04d}"


def audit(state: State, actor: str, action: str, record_id: str, detail: str) -> None:
    state.audit.append(AuditEntry(state.now, actor, action, record_id, detail))


def refresh(state: State, trigger: str) -> None:
    """Re-run exception rules, then the communication rules for every exception that changed or is open."""
    detected = {ex.exception_id: ex for ex in detect_exceptions(state)}
    for ex_id, new in detected.items():
        old = state.exceptions.get(ex_id)
        if old is None:
            state.exceptions[ex_id] = new
            audit(state, "System", "Exception detected", ex_id, f"{new.title} ({new.priority}: {new.priority_reason})")
            continue
        if old.status == "Resolved":
            old.status, old.resolved_at, old.resolution = "Open", "", ""
            audit(state, "System", "Exception reopened", ex_id, new.title)
        if old.priority != new.priority:
            audit(state, "System", "Priority changed", ex_id, f"{old.priority} → {new.priority}: {new.priority_reason}")
        keep = {"status": old.status, "owner": old.owner, "assigned_at": old.assigned_at, "detected_at": old.detected_at,
                "facts": {**new.facts, **{k: v for k, v in old.facts.items() if k in ("repromised", "actions")}}}
        state.exceptions[ex_id] = replace(new, **keep)
    for ex_id, ex in state.exceptions.items():
        if ex_id not in detected and ex.status != "Resolved":
            ex.status, ex.resolved_at, ex.resolution = "Resolved", state.now, f"Condition cleared by {trigger}"
            audit(state, "System", "Exception resolved", ex_id, ex.resolution)
    for ex in state.exceptions.values():
        for n in sync_notifications(state, ex, trigger, lambda: _next_id(state, "NT")):
            audit(state, "Rules engine", "Notification created", n.notification_id, f"{n.rule_id} → {n.recipient}: {n.reason}")
            if not n.requires_approval and state.auto_send_internal:
                deliver(state, n, "auto-send policy")
                audit(state, "System", f"Notification {n.status.lower()}", n.notification_id, n.last_error or n.subject)


def new_state() -> State:
    state = build_seed()
    refresh(state, "initial data load")
    return state


def load_state() -> State:
    if STATE_FILE.exists():
        try:
            saved = state_from_dict(json.loads(STATE_FILE.read_text(encoding="utf8")))
            if saved.seed_version == SEED_VERSION:
                return saved
            STATE_FILE.unlink(missing_ok=True)  # saved by an older version of the sample data
        except Exception:
            STATE_FILE.unlink(missing_ok=True)
    return new_state()


def save_state(state: State) -> None:
    STATE_FILE.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf8")


def reset_state() -> State:
    STATE_FILE.unlink(missing_ok=True)
    state = new_state()
    audit(state, OPERATOR, "Demo reset", "—", "Sample data restored")
    return state


# ---------- events ----------
def _require(cond: bool, reason: str) -> None:
    if not cond:
        raise Rejected(reason)


def _apply_transfer(state: State, e: Event, t: Transfer) -> None:
    kind = e.event_type
    if kind == "TRANSFER_DEPARTED":
        _require(t.status in ("Planned", "Loading"), f"{t.transfer_id} is {t.status}, not ready to depart")
        _require(not t.depends_on, f"{t.transfer_id} is waiting for {t.depends_on}")
        for line in t.lines:
            rec = stock_record(state, line.sku, t.source)
            if rec is not None:
                _require(rec.on_hand >= line.qty, f"only {rec.on_hand} {line.sku} on hand at {t.source}")
                rec.on_hand -= line.qty
        t.status, t.actual_departure = "In transit", e.ts
    elif kind == "TRANSFER_CHECKPOINT":
        _require(t.status == "In transit", f"{t.transfer_id} is {t.status}")
    elif kind == "TRANSFER_ETA_UPDATED":
        _require(t.status in ("Planned", "Loading", "In transit", "Customs hold"), f"{t.transfer_id} is already {t.status}")
        _require(bool(e.payload.get("new_eta")), "new_eta missing")
        t.eta = e.payload["new_eta"]
    elif kind == "TRANSFER_CUSTOMS_HOLD":
        _require(t.status in ("In transit", "Arrived"), f"{t.transfer_id} is {t.status}")
        t.status, t.exception = "Customs hold", e.payload.get("reason", e.detail)
    elif kind == "TRANSFER_CUSTOMS_RELEASED":
        _require(t.status == "Customs hold", f"{t.transfer_id} is not on customs hold")
        t.status, t.exception = ("Arrived" if t.actual_arrival else "In transit"), ""
    elif kind == "TRANSFER_QUALITY_HOLD":
        _require(t.status in ("In transit", "Arrived"), f"{t.transfer_id} is {t.status}")
        t.status, t.exception = "Exception", e.payload.get("reason", e.detail)
    elif kind == "TRANSFER_ARRIVED":
        _require(t.status == "In transit", f"{t.transfer_id} is {t.status}")
        t.status, t.actual_arrival = "Arrived", e.ts
    elif kind == "TRANSFER_RECEIVED":
        _require(t.status in ("Arrived", "In transit"), f"{t.transfer_id} is {t.status}")
        received = e.payload.get("received", {})
        t.actual_arrival = t.actual_arrival or e.ts
        for line in t.lines:
            got = int(received.get(line.sku, line.qty))
            _require(0 <= got <= line.qty, f"received quantity {got} for {line.sku} is outside 0–{line.qty}")
            line.received = got
            stock_record(state, line.sku, t.destination, create=True).on_hand += got
        t.status = "Received" if all(l.received == l.qty for l in t.lines) else "Partially received"
        _allocate_backorders(state, t)
        for dep in state.transfers.values():
            if dep.depends_on == t.transfer_id:
                new_dep, new_arr = delayed_schedule(state, dep, shift(e.ts, DC_HANDLING_H))
                dep.depends_on = ""
                if new_dep != dep.planned_departure:
                    dep.planned_departure, dep.planned_arrival, dep.eta = new_dep, new_arr, new_arr
                audit(state, "System", "Dependency released", dep.transfer_id,
                      f"{t.transfer_id} received; stock reserved, dispatch planned {nice(dep.planned_departure)}")
    else:
        raise Rejected(f"unknown transfer event {kind}")


def _allocate_backorders(state: State, t: Transfer) -> None:
    """Customer orders waiting on this transfer get first claim on the received stock, earliest promise first."""
    waiting = sorted(((o, i) for o in state.orders.values() for i in o.items
                      if i.allocation == "awaiting_inbound" and i.awaiting_transfer == t.transfer_id), key=lambda x: x[0].promised_by)
    for order, item in waiting:
        if position(state, item.sku, t.destination).available >= item.qty:
            item.allocation, item.facility_id, item.awaiting_transfer = "allocated", t.destination, ""
            audit(state, "System", "Backorder allocated", order.order_id, f"{item.qty} × {item.sku} at {t.destination} from {t.transfer_id}")
        else:
            item.allocation, item.awaiting_transfer = "unallocated", ""
            order.issue = "ALLOCATION_FAILED"
            audit(state, "System", "Allocation failed", order.order_id, f"{t.transfer_id} did not bring enough {item.sku}")
        if all(i.allocation == "allocated" for i in order.items):
            order.status = "Allocated"


def _apply_order(state: State, e: Event) -> None:
    o = state.orders[e.record_id]
    kind = e.event_type
    if kind == "ORDER_PICKED":
        _require(o.status == "Allocated" or (o.status == "Created" and all(i.allocation == "allocated" for i in o.items)), f"{o.order_id} is not fully allocated")
        o.status = "Picked"
    elif kind == "ORDER_PACKED":
        _require(o.status == "Picked", f"{o.order_id} is {o.status}")
        o.status = "Packed"
    elif kind == "ORDER_SHIPPED":
        _require(o.status in ("Allocated", "Picked", "Packed"), f"{o.order_id} is {o.status}")
        _require(all(i.allocation == "allocated" for i in o.items), f"{o.order_id} has items without stock")
        for i in o.items:
            stock_record(state, i.sku, i.facility_id, create=True).on_hand -= i.qty
            i.allocation = "shipped"
        o.status, o.shipped_at, o.last_scan_at, o.last_scan_location = "Shipped", e.ts, e.ts, "Handed to carrier"
    elif kind == "CARRIER_SCAN":
        _require(o.status == "Shipped", f"{o.order_id} is {o.status}")
        o.last_scan_at, o.last_scan_location = e.ts, e.payload.get("location", e.detail)
        if o.issue == "CARRIER_DELAY":
            o.issue = ""
    elif kind == "CARRIER_DELAY":
        _require(o.status == "Shipped", f"{o.order_id} is {o.status}")
        o.issue = "CARRIER_DELAY"
    elif kind == "ORDER_DELIVERED":
        collected = o.channel == "Click & collect" and o.status == "Packed"
        _require(o.status == "Shipped" or collected, f"{o.order_id} is {o.status}")
        if collected:
            for i in o.items:
                stock_record(state, i.sku, i.facility_id, create=True).on_hand -= i.qty
        o.status, o.delivered_at, o.last_scan_at, o.last_scan_location, o.issue = "Delivered", e.ts, e.ts, f"Delivered, {o.city}", ""
        for i in o.items:
            i.allocation = "delivered"
    elif kind == "RETURN_REQUESTED":
        _require(o.status == "Delivered", f"{o.order_id} is {o.status}")
        o.status = "Return in transit"
    elif kind == "RETURN_RECEIVED":
        _require(o.status == "Return in transit", f"{o.order_id} is {o.status}")
        facility = e.payload.get("facility", HUB)
        for i in o.items:
            rec = stock_record(state, i.sku, facility, create=True)
            rec.on_hand += i.qty
            rec.quarantined += i.qty
            i.allocation = "returned"
        o.status = "Returned"
    elif kind in ("INTEGRATION_REJECTED", "ALLOCATION_FAILED"):
        _require(o.status == "Created", f"{o.order_id} is {o.status}")
        o.issue = kind
    else:
        raise Rejected(f"unknown order event {kind}")


def process_event(state: State, event: Event) -> str:
    """Apply one incoming event exactly once. Returns the outcome recorded in the event log."""
    e = replace(event, payload=dict(event.payload))
    if e.event_id in state.processed_event_ids:
        e.outcome = "duplicate ignored"
        state.events.append(e)
        audit(state, "Event bus", "Duplicate event ignored", e.record_id, f"{e.event_id} {e.event_type} was already processed")
        return e.outcome
    state.now = max(state.now, e.ts)
    try:
        if e.record_type == "transfer":
            _require(e.record_id in state.transfers, f"unknown transfer {e.record_id}")
            _apply_transfer(state, e, state.transfers[e.record_id])
        else:
            _require(e.record_id in state.orders, f"unknown order {e.record_id}")
            _apply_order(state, e)
        problems = validate_inventory(state)
        _require(not problems, "; ".join(problems))
    except Rejected as exc:
        e.outcome = f"rejected: {exc}"
        state.events.append(e)
        state.processed_event_ids.append(e.event_id)
        audit(state, "Event bus", "Event rejected", e.record_id, f"{e.event_id} {e.event_type}: {exc}")
        return e.outcome
    state.events.append(e)
    state.processed_event_ids.append(e.event_id)
    audit(state, "Event bus", "Event applied", e.record_id, f"{e.event_id} {e.event_type}: {e.detail}")
    refresh(state, e.event_id)
    return e.outcome


def _progress_operator_transfers(state: State, until: str) -> None:
    """Emergency transfers raised in the demo have no scripted events; move them along their plan as the clock passes."""
    for t in list(state.transfers.values()):
        if not t.reference.startswith("Raised for"):
            continue
        steps = [("TRANSFER_DEPARTED", t.planned_departure, "Express partner collected the goods."),
                 ("TRANSFER_ARRIVED", t.planned_arrival, "Arrived at store."),
                 ("TRANSFER_RECEIVED", shift(t.planned_arrival, 0.5), "Received in full.")]
        for kind, when, detail in steps:
            eid = f"EV-A-{t.transfer_id}-{kind.split('_')[1]}"
            if when <= until and eid not in state.processed_event_ids:
                process_event(state, Event(eid, when, kind, "transfer", t.transfer_id, "Express partner (simulated)", detail))


def next_scripted_event(state: State) -> str | None:
    if state.script_cursor >= len(SCRIPT):
        return None
    event = SCRIPT[state.script_cursor]
    state.script_cursor += 1
    _progress_operator_transfers(state, event.ts)
    outcome = process_event(state, event)
    return f"{event.event_id} {event.event_type} {event.record_id}: {outcome}"


def manual_event(state: State, record_type: str, record_id: str, event_type: str, detail: str, payload: dict | None = None,
                 customer_text: str = "") -> str:
    event = Event(_next_id(state, "EV-M"), state.now, event_type, record_type, record_id, "Demo event simulator", detail,
                  payload or {}, bool(customer_text), customer_text)
    return process_event(state, event)


# ---------- operator actions ----------
def _exception(state: State, ex_id: str) -> OpsException:
    if ex_id not in state.exceptions:
        raise Rejected(f"unknown exception {ex_id}")
    return state.exceptions[ex_id]


def _record_action(state: State, ex: OpsException, text: str) -> None:
    ex.facts.setdefault("actions", []).append(f"{state.now} · {text}")
    if ex.status in ("Open", "Assigned"):
        ex.status = "Action in progress"


def assign(state: State, ex_id: str, owner: str) -> None:
    ex = _exception(state, ex_id)
    ex.owner, ex.assigned_at = owner, ex.assigned_at or state.now
    if ex.status == "Open":
        ex.status = "Assigned"
    audit(state, OPERATOR, "Exception assigned", ex_id, f"Owner: {owner}")


def resolve(state: State, ex_id: str, note: str) -> None:
    ex = _exception(state, ex_id)
    _require(bool(note.strip()), "a resolution note is required")
    ex.status, ex.resolved_at, ex.resolution = "Resolved", state.now, note.strip()
    ex.assigned_at = ex.assigned_at or state.now
    audit(state, OPERATOR, "Exception resolved", ex_id, note.strip())
    sync_notifications(state, ex, f"{ex_id} resolved", lambda: _next_id(state, "NT"))


def reallocate_orders(state: State, ex_id: str) -> list[str]:
    """Move at-risk backorders to another DC that can still meet the promise."""
    ex = _exception(state, ex_id)
    impact = transfer_impact(state, ex.record_id)
    moved = []
    for oi, facility, projected in reallocation_candidates(state, impact):
        order = state.orders[oi.order_id]
        for item in order.items:
            if item.allocation == "awaiting_inbound" and item.awaiting_transfer == ex.record_id and item.sku == oi.sku:
                _require(position(state, item.sku, facility).available >= item.qty, f"{facility} no longer has {item.qty} {item.sku}")
                item.allocation, item.facility_id, item.awaiting_transfer = "allocated", facility, ""
                moved.append(f"{order.order_id} {item.sku} → {facility} (delivers by {nice(projected)})")
        if all(i.allocation == "allocated" for i in order.items):
            order.status = "Allocated"
    _require(bool(moved), "no order can be moved to another DC and still meet its promise")
    _record_action(state, ex, "Reallocated " + "; ".join(moved))
    audit(state, OPERATOR, "Orders reallocated", ex_id, "; ".join(moved))
    refresh(state, f"{ex_id} reallocation")
    return moved


def emergency_replenishment(state: State, ex_id: str, source: str, store: str, sku: str, qty: int) -> str:
    ex = _exception(state, ex_id)
    _require(qty > 0, "quantity must be positive")
    _require(position(state, sku, source).available >= qty, f"{source} has only {position(state, sku, source).available} {sku} available")
    tid = f"TR-{6000 + state.seq + 1}"
    state.seq += 1
    depart = shift(state.now, DISPATCH_PREP_H)
    arrive = shift(depart, road_hours(state, source, store))
    state.transfers[tid] = Transfer(tid, "Emergency → Store", source, store, "Road", "Express partner", [TransferLine(sku, qty)], "Planned",
                                    depart, arrive, eta=arrive, reference=f"Raised for {ex_id}")
    _record_action(state, ex, f"Emergency transfer {tid}: {qty} × {sku} {source} → {store}, arrives {nice(arrive)}")
    audit(state, OPERATOR, "Emergency transfer created", tid, f"{qty} × {sku} from {source} to {store} for {ex_id}")
    refresh(state, f"{tid} created")
    return tid


def repromise_orders(state: State, ex_id: str) -> list[str]:
    """Set new promise dates (end of the projected day) for orders still at risk; customer updates follow by rule."""
    ex = _exception(state, ex_id)
    impact = transfer_impact(state, ex.record_id)
    changed = []
    repromised = ex.facts.setdefault("repromised", {})
    for oid in sorted({o.order_id for o in impact.orders_at_risk}):
        projected = max(o.projected_delivery for o in impact.orders_at_risk if o.order_id == oid)
        new_promise = ts(projected).replace(hour=20, minute=0).strftime("%Y-%m-%dT%H:%M")
        if new_promise < projected:
            new_promise = shift(new_promise, 24)
        order = state.orders[oid]
        repromised.setdefault(oid, order.promised_by)
        order.promised_by = new_promise
        changed.append(f"{oid} → {nice(new_promise)}")
    _require(bool(changed), "no orders are at risk")
    _record_action(state, ex, "New promise dates: " + "; ".join(changed))
    audit(state, OPERATOR, "Orders re-promised", ex_id, "; ".join(changed))
    refresh(state, f"{ex_id} re-promise")
    return changed


def resubmit_order(state: State, order_id: str) -> str:
    """Clear an integration rejection after the address is confirmed and allocate from the nearest free stock."""
    o = state.orders[order_id]
    _require(o.issue == "INTEGRATION_REJECTED", f"{order_id} has no rejected booking")
    o.issue = ""
    for item in o.items:
        if item.allocation == "unallocated":
            _require(position(state, item.sku, HUB).available >= item.qty, f"no free {item.sku} at {state.facilities[HUB].name}")
            item.allocation, item.facility_id = "allocated", HUB
    o.status = "Allocated"
    audit(state, OPERATOR, "Order resubmitted", order_id, "Address confirmed with customer; booking resubmitted (simulated)")
    refresh(state, f"{order_id} resubmitted")
    return o.status


def restock_return(state: State, order_id: str, facility: str = HUB) -> None:
    o = state.orders[order_id]
    _require(o.status == "Returned", f"{order_id} is {o.status}")
    for i in o.items:
        rec = stock_record(state, i.sku, facility)
        _require(rec is not None and rec.quarantined >= i.qty, f"no {i.sku} in inspection at {facility}")
        rec.quarantined -= i.qty
        i.allocation = "restocked"
    audit(state, OPERATOR, "Return restocked", order_id, f"Inspected and moved to sellable stock at {facility}")
    refresh(state, f"{order_id} restocked")


# ---------- communications ----------
def approve_and_send(state: State, nid: str, body: str | None = None) -> str:
    n = state.notifications[nid]
    _require(n.status in ("Awaiting approval", "Draft"), f"{nid} is {n.status}")
    if body is not None and body != n.body:
        n.body = body
        n.history.append(f"{state.now} · edited by {OPERATOR}")
    if n.requires_approval:
        n.approved_by = OPERATOR
        n.history.append(f"{state.now} · approved by {OPERATOR}")
    deliver(state, n, OPERATOR)
    audit(state, OPERATOR, "Notification approved" if n.requires_approval else "Notification sent", nid, f"{n.status}: {n.subject}")
    return n.status


def reject_notification(state: State, nid: str, reason: str) -> None:
    n = state.notifications[nid]
    _require(n.status in ("Awaiting approval", "Draft", "Failed"), f"{nid} is {n.status}")
    n.status = "Rejected"
    n.history.append(f"{state.now} · rejected by {OPERATOR}: {reason or 'no reason given'}")
    audit(state, OPERATOR, "Notification rejected", nid, reason or "—")


def retry_notification(state: State, nid: str) -> str:
    n = state.notifications[nid]
    _require(n.status == "Failed", f"{nid} is {n.status}")
    deliver(state, n, OPERATOR)
    audit(state, OPERATOR, "Notification retried", nid, n.status)
    return n.status


def set_auto_send(state: State, enabled: bool) -> None:
    state.auto_send_internal = enabled
    audit(state, OPERATOR, "Policy changed", "auto-send", "Internal notifications send automatically" if enabled else "All notifications wait for review")


def demo_metrics(state: State) -> dict:
    def hours(a: str, b: str) -> float:
        return (ts(b) - ts(a)).total_seconds() / 3600
    assigned = [hours(e.detected_at, e.assigned_at) for e in state.exceptions.values() if e.assigned_at]
    resolved = [hours(e.detected_at, e.resolved_at) for e in state.exceptions.values() if e.resolved_at]
    return {
        "assign_h": round(sum(assigned) / len(assigned), 1) if assigned else None,
        "resolve_h": round(sum(resolved) / len(resolved), 1) if resolved else None,
        "resolved": len(resolved),
        "open": sum(1 for e in state.exceptions.values() if e.status != "Resolved"),
    }
