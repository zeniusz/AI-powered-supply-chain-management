"""JSON-ready views of the demo state for the frontend. Derived values come from domain.py, never from the browser."""
from __future__ import annotations

from dataclasses import asdict

import assistant
import engine
from comms import delivery_mode
from domain import (OPEN_TRANSFER, PRIORITY_RULES, KIND_LABEL, all_positions, facility_name, order_projection, order_state_label, position,
                    sku_name, sort_key, transfer_impact)
from models import State, ts

DEPARTED = {"In transit", "Customs hold", "Arrived", "Exception"}
CUSTOMER_STAGES = {"Shipped": 2, "Delivered": 4, "Return in transit": 4, "Returned": 4}


def _age_h(state: State, since: str) -> float:
    return round((ts(state.now) - ts(since)).total_seconds() / 3600, 1)


def _exception(state: State, ex) -> dict:
    return {"id": ex.exception_id, "kind": ex.kind, "kind_label": KIND_LABEL[ex.kind], "title": ex.title, "priority": ex.priority,
            "priority_reason": ex.priority_reason, "status": ex.status, "owner": ex.owner, "detected_at": ex.detected_at,
            "age_h": _age_h(state, ex.detected_at), "record_type": ex.record_type, "record_id": ex.record_id, "facility_id": ex.facility_id,
            "facility": facility_name(state, ex.facility_id) if ex.facility_id else "", "orders": ex.affected_orders, "stores": ex.affected_stores,
            "assigned_at": ex.assigned_at, "resolved_at": ex.resolved_at, "resolution": ex.resolution}


def _transfer(state: State, t, open_ex: dict) -> dict:
    ex = open_ex.get(t.transfer_id)
    if ex:
        tone = "crit" if ex.priority == "P1" or t.status in ("Customs hold", "Exception") else "warn"
    elif t.depends_on:
        tone = "warn" if t.depends_on in open_ex else "idle"
    else:
        tone = "move" if t.status in ("In transit", "Arrived") else "idle"
    d = asdict(t)
    d.update({"source_name": facility_name(state, t.source), "destination_name": facility_name(state, t.destination), "tone": tone,
              "units": sum(l.qty for l in t.lines), "open": t.status in OPEN_TRANSFER, "waiting": bool(t.depends_on) or t.status in ("Planned", "Loading"),
              "exception_id": ex.exception_id if ex else ""})
    return d


def _facilities(state: State, open_ex: dict) -> list[dict]:
    tones: dict[str, str] = {}
    for ex in state.exceptions.values():
        if ex.status == "Resolved":
            continue
        ids = {ex.facility_id} | set(ex.affected_stores)
        if ex.record_type == "transfer":
            ids.add(state.transfers[ex.record_id].source)
        for fid in ids:
            if fid:
                tones[fid] = "crit" if ex.priority == "P1" or tones.get(fid) == "crit" else "warn"
    return [{**asdict(f), "tone": tones.get(f.facility_id, "ok")} for f in state.facilities.values()]


def _order(state: State, o) -> dict:
    proj = order_projection(state, o)
    closed = o.status in ("Delivered", "Returned", "Return in transit")
    risk = bool(o.issue) or (bool(proj) and not closed and ts(proj) > ts(o.promised_by))
    d = asdict(o)
    d.update({"state": order_state_label(o), "projected": proj, "risk": risk,
              "items": [{**asdict(i), "name": sku_name(state, i.sku), "image": state.skus[i.sku].image if i.sku in state.skus else ""} for i in o.items],
              "pickup_store_name": facility_name(state, o.pickup_store) if o.pickup_store else "", "units": sum(i.qty for i in o.items)})
    return d


def _positions(state: State) -> list[dict]:
    rows = []
    for p in all_positions(state):
        fac = state.facilities[p.facility_id]
        if not state.skus[p.sku].sellable or fac.facility_type not in ("Distribution centre", "3PL gateway", "Store"):
            continue
        problem = p.backordered > 0 or p.quarantined > 0 or bool(p.daily_demand and p.available <= p.safety_stock)
        rows.append({"sku": p.sku, "product": sku_name(state, p.sku), "facility_id": p.facility_id, "facility": fac.name, "facility_type": fac.facility_type,
                     "on_hand": p.on_hand, "allocated": p.allocated, "reserved": p.reserved, "quarantined": p.quarantined, "available": p.available,
                     "incoming": p.incoming, "in_transit": p.in_transit, "backordered": p.backordered, "daily_demand": p.daily_demand,
                     "cover_days": round(p.available / p.daily_demand, 1) if p.daily_demand else None, "problem": problem})
    return rows


def snapshot(state: State, config: dict) -> dict:
    open_ex = {e.record_id: e for e in state.exceptions.values() if e.status != "Resolved"}
    exceptions = sorted(state.exceptions.values(), key=sort_key)
    open_list = [e for e in exceptions if e.status != "Resolved"]
    pending = [n for n in state.notifications.values() if n.status == "Awaiting approval"]
    return {
        "now": state.now,
        "demo": {"cursor": state.script_cursor, "total": len(engine.SCRIPT), "auto_send": state.auto_send_internal, "metrics": engine.demo_metrics(state),
                 "assistant": assistant.provider_label(), "delivery": delivery_mode()},
        "config": config,
        "rules": PRIORITY_RULES,
        "kpis": {"open": len(open_list), "p1": sum(e.priority == "P1" for e in open_list),
                 "orders_at_risk": len({o for e in open_list for o in e.affected_orders}),
                 "stores_short": len({s for e in open_list for s in e.affected_stores}), "to_approve": len(pending),
                 "units_in_transit": sum(l.qty - l.received for t in state.transfers.values() if t.status in DEPARTED for l in t.lines if state.skus[l.sku].sellable)},
        "exceptions": [_exception(state, e) for e in exceptions],
        "transfers": [_transfer(state, t, open_ex) for t in sorted(state.transfers.values(), key=lambda t: t.transfer_id)],
        "facilities": _facilities(state, open_ex),
        "orders": [_order(state, o) for o in sorted(state.orders.values(), key=lambda o: o.order_id, reverse=True)],
        "positions": _positions(state),
        "skus": {k: {"name": v.name, "image": v.image, "sellable": v.sellable} for k, v in state.skus.items()},
        "notifications": [asdict(n) for n in sorted(state.notifications.values(), key=lambda n: n.notification_id, reverse=True)],
        "events": [asdict(e) for e in reversed(state.events)][:300],
        "audit": [asdict(a) for a in reversed(state.audit)][:300],
    }


def workspace(state: State, ex_id: str) -> dict:
    ex = state.exceptions[ex_id]
    a = assistant.assessment(state, ex_id)
    out = {"assessment": a, "evidence": [asdict(e) for e in state.events if e.event_id in ex.evidence], "actions": ex.facts.get("actions", []),
           "messages": [asdict(n) for n in state.notifications.values() if n.exception_id == ex_id and n.status != "Superseded"], "impact": None}
    related = {ex_id, ex.record_id} | {n["notification_id"] for n in out["messages"]} | set(ex.facts.get("dependents", []))
    out["history"] = [asdict(x) for x in reversed(state.audit) if x.record_id in related][:40]
    if ex.record_type == "transfer":
        t = state.transfers[ex.record_id]
        im = transfer_impact(state, t.transfer_id)
        out["impact"] = {
            "delay_h": im.delay_h, "ready_at": im.ready_at, "dependents": [{"id": d, "departure": dep, "arrival": arr} for d, dep, arr in im.dependents],
            "stores": [{"facility_id": s.facility_id, "store": facility_name(state, s.facility_id), "sku": s.sku, "transfer_id": s.transfer_id, "qty": s.qty,
                        "available": s.available, "daily_demand": s.daily_demand, "planned_arrival": s.planned_arrival, "new_arrival": s.new_arrival,
                        "stockout_at": s.stockout_at, "shortage": s.shortage_units} for s in im.stores],
            "orders": [{"order_id": o.order_id, "sku": o.sku, "qty": o.qty, "via": o.via, "promised_by": o.promised_by, "projected": o.projected_delivery,
                        "at_risk": o.at_risk} for o in im.orders],
            "gap": im.dc_gap,
            "stock": [{"sku": l.sku, **{k: getattr(position(state, l.sku, t.destination), k) for k in ("on_hand", "allocated", "quarantined", "available", "incoming", "backordered")}}
                      for l in t.lines if state.skus[l.sku].sellable],
        }
    return out


def tracking(state: State, order_id: str) -> dict | None:
    o = state.orders.get(order_id)
    if not o:
        return None
    stage = CUSTOMER_STAGES.get(o.status, 1)
    updated = any(n.recipient_ref == order_id and n.audience == "Customer" and n.status in ("Simulated send", "Sent") for n in state.notifications.values())
    return {"order_id": o.order_id, "stage": stage, "channel": o.channel, "expected_by": o.promised_by, "updated": updated, "carrier": o.carrier,
            "tracking_code": o.tracking_code, "collect_at": facility_name(state, o.pickup_store) if o.pickup_store else "",
            "items": [{"name": sku_name(state, i.sku), "size": i.size, "qty": i.qty, "image": state.skus[i.sku].image} for i in o.items],
            "timeline": [{"ts": e.ts, "text": e.customer_text} for e in reversed(state.events)
                         if e.record_id == order_id and e.customer_visible and e.outcome == "applied"]}
