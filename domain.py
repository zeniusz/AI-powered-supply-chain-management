"""Deterministic business rules: inventory arithmetic, downstream impact, sourcing options and exception detection.

Inventory buckets at one facility (mutually exclusive parts of on-hand, so nothing is counted twice):
    on_hand     = allocated + reserved + quarantined + available
    allocated   = units on customer orders allocated here and not yet shipped
    reserved    = units on planned/loading outbound transfers from here (not dependent on inbound stock)
    quarantined = damaged / under inspection (stored figure)
    available   = on_hand - allocated - reserved - quarantined   (free to allocate)
Outside on-hand:
    incoming    = units on open inbound transfers (planned, loading, in transit, customs hold, arrived)
    in_transit  = the part of incoming that has physically departed
    projected   = available + incoming
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

from models import OpsException, Order, State, StockRecord, Transfer, iso, nice, shift, ts

OPEN_TRANSFER = {"Planned", "Loading", "In transit", "Customs hold", "Arrived", "Exception"}
DEPARTED = {"In transit", "Customs hold", "Arrived", "Exception"}
PRE_SHIP = {"Created", "Allocated", "Picked", "Packed"}
LATE_GRACE_H = 2  # a transfer is late once its ETA (or the clock) passes planned arrival by this much
DC_HANDLING_H = 12  # receiving + put-away before inbound stock can be picked
PICK_PACK_H = 4  # picking and packing an order from free stock
NEXT_DAY_REGION = {"ES", "PT", "FR", "IT", "DE", "BE", "NL", "AT", "DK"}  # parcel network with next-day delivery
HUB = "DC-ES-01"  # main distribution centre: inbound factory freight lands here
STORE_HANDLING_H = 2
CUSTOMS_ASSUMED_H = 24  # no release time is known during a hold; assume at least one more day
CARRIER_SCAN_GAP_H = 24
ROAD_KMH = 60
DISPATCH_PREP_H = 6


# ---------- lookups ----------
def stock_record(state: State, sku: str, facility_id: str, create: bool = False) -> StockRecord | None:
    for rec in state.stock:
        if rec.sku == sku and rec.facility_id == facility_id:
            return rec
    if create:
        rec = StockRecord(sku, facility_id, 0)
        state.stock.append(rec)
        return rec
    return None


def facility_name(state: State, facility_id: str) -> str:
    f = state.facilities.get(facility_id)
    return f.name if f else facility_id or "—"


def sku_name(state: State, sku: str) -> str:
    s = state.skus.get(sku)
    return s.name if s else sku


# ---------- inventory arithmetic ----------
@dataclass
class Position:
    sku: str
    facility_id: str
    on_hand: int = 0
    allocated: int = 0
    reserved: int = 0
    quarantined: int = 0
    available: int = 0
    incoming: int = 0
    in_transit: int = 0
    backordered: int = 0  # demand waiting on inbound stock to this facility
    daily_demand: float = 0.0
    safety_stock: int = 0

    @property
    def projected(self) -> int:
        return self.available + self.incoming


def allocated_qty(state: State, sku: str, facility_id: str) -> int:
    return sum(i.qty for o in state.orders.values() if o.status in PRE_SHIP for i in o.items
               if i.allocation == "allocated" and i.sku == sku and i.facility_id == facility_id)


def reserved_qty(state: State, sku: str, facility_id: str) -> int:
    return sum(l.qty for t in state.transfers.values() if t.source == facility_id and t.status in ("Planned", "Loading")
               and not t.depends_on for l in t.lines if l.sku == sku)


def position(state: State, sku: str, facility_id: str) -> Position:
    rec = stock_record(state, sku, facility_id)
    p = Position(sku, facility_id)
    if rec:
        p.on_hand, p.quarantined, p.daily_demand, p.safety_stock = rec.on_hand, rec.quarantined, rec.daily_demand, rec.safety_stock
    p.allocated = allocated_qty(state, sku, facility_id)
    p.reserved = reserved_qty(state, sku, facility_id)
    p.available = p.on_hand - p.allocated - p.reserved - p.quarantined
    for t in state.transfers.values():
        if t.destination == facility_id and t.status in OPEN_TRANSFER:
            for l in t.lines:
                if l.sku == sku:
                    p.incoming += l.qty - l.received
                    if t.status in DEPARTED:
                        p.in_transit += l.qty - l.received
    awaiting = {t.transfer_id for t in state.transfers.values() if t.destination == facility_id}
    p.backordered = sum(i.qty for o in state.orders.values() for i in o.items
                        if i.allocation == "awaiting_inbound" and i.sku == sku and i.awaiting_transfer in awaiting)
    return p


def all_positions(state: State) -> list[Position]:
    keys = {(r.sku, r.facility_id) for r in state.stock}
    for t in state.transfers.values():
        if t.status in OPEN_TRANSFER:
            keys |= {(l.sku, t.destination) for l in t.lines}
    return [position(state, s, f) for s, f in sorted(keys, key=lambda k: (k[1], k[0]))]


def validate_inventory(state: State) -> list[str]:
    """Invariant check: no bucket may be negative."""
    problems = []
    for p in all_positions(state):
        for name in ("on_hand", "allocated", "reserved", "quarantined", "available", "incoming"):
            if getattr(p, name) < 0:
                problems.append(f"{p.sku} at {p.facility_id}: {name} is {getattr(p, name)}")
    return problems


# ---------- network distances and lead times ----------
def distance_km(state: State, a: str, b: str) -> float:
    fa, fb = state.facilities[a], state.facilities[b]
    lat1, lon1, lat2, lon2 = map(math.radians, [fa.lat, fa.lon, fb.lat, fb.lon])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h)) * 1.25  # road factor


def road_hours(state: State, a: str, b: str) -> float:
    return round(distance_km(state, a, b) / ROAD_KMH, 1)


def carrier_hours(state: State, facility_id: str, order: Order) -> int:
    """Parcel transit from a facility to the customer: next day within the core network, two days otherwise."""
    if order.channel == "Click & collect":
        return 0
    src = state.facilities[facility_id].country
    return 24 if src == order.country or {src, order.country} <= NEXT_DAY_REGION else 48


# ---------- transfer timing ----------
def transfer_delay_h(state: State, t: Transfer) -> float:
    if t.status == "Customs hold":
        expected = max(ts(state.now) + timedelta(hours=CUSTOMS_ASSUMED_H), ts(t.planned_arrival))
        return (expected - ts(t.planned_arrival)).total_seconds() / 3600
    eta = ts(t.eta or t.planned_arrival)
    if not t.actual_arrival and ts(state.now) > ts(t.planned_arrival) and ts(state.now) > eta:
        eta = ts(state.now)
    return max(0.0, (eta - ts(t.planned_arrival)).total_seconds() / 3600)


def expected_ready(state: State, t: Transfer) -> str:
    """When the transfer's stock can be used at its destination."""
    if t.status in ("Received", "Partially received"):
        return t.actual_arrival
    if t.status == "Customs hold":
        arrival = iso(max(ts(state.now) + timedelta(hours=CUSTOMS_ASSUMED_H), ts(t.planned_arrival)))
    else:
        arrival = t.eta or t.planned_arrival
        if not t.actual_arrival and ts(state.now) > ts(arrival):
            arrival = state.now
    handling = DC_HANDLING_H if state.facilities[t.destination].facility_type in ("Distribution centre", "3PL gateway") else STORE_HANDLING_H
    return shift(arrival, handling)


def delayed_schedule(state: State, dependent: Transfer, upstream_ready: str) -> tuple[str, str]:
    """A dependent transfer cannot depart before its upstream stock is ready."""
    duration = (ts(dependent.planned_arrival) - ts(dependent.planned_departure)).total_seconds() / 3600
    depart = max(ts(dependent.planned_departure), ts(upstream_ready))
    return iso(depart), iso(depart + timedelta(hours=duration))


# ---------- downstream impact ----------
@dataclass
class StoreImpact:
    facility_id: str
    transfer_id: str
    sku: str
    qty: int
    available: int
    daily_demand: float
    planned_arrival: str
    new_arrival: str
    stockout_at: str
    shortage_units: int


@dataclass
class OrderImpact:
    order_id: str
    sku: str
    qty: int
    via: str
    promised_by: str
    projected_delivery: str
    at_risk: bool


@dataclass
class Impact:
    transfer_id: str
    delay_h: float
    ready_at: str
    dependents: list[tuple[str, str, str]] = field(default_factory=list)  # (transfer id, new departure, new arrival)
    stores: list[StoreImpact] = field(default_factory=list)
    orders: list[OrderImpact] = field(default_factory=list)
    dc_gap: dict[str, int] = field(default_factory=dict)  # sku -> units needed downstream that the destination cannot cover now

    @property
    def orders_at_risk(self) -> list[OrderImpact]:
        return [o for o in self.orders if o.at_risk]

    @property
    def store_shortage(self) -> int:
        return sum(s.shortage_units for s in self.stores)

    @property
    def stores_short(self) -> list[str]:
        return sorted({s.facility_id for s in self.stores if s.shortage_units > 0})


def _store_impact(state: State, dep: Transfer, sku: str, qty: int, new_arrival: str) -> StoreImpact:
    pos = position(state, sku, dep.destination)
    other_incoming = sum(l.qty - l.received for t in state.transfers.values()
                         if t.destination == dep.destination and t.status in OPEN_TRANSFER and not t.depends_on
                         and ts(t.eta or t.planned_arrival) <= ts(new_arrival) for l in t.lines if l.sku == sku)
    cover = max(0, pos.available + other_incoming)
    now = ts(state.now)
    if pos.daily_demand <= 0:
        return StoreImpact(dep.destination, dep.transfer_id, sku, qty, pos.available, 0, dep.planned_arrival, new_arrival, "", 0)
    stockout = now + timedelta(days=cover / pos.daily_demand)
    gap_h = (ts(new_arrival) - stockout).total_seconds() / 3600
    shortage = math.ceil(pos.daily_demand * gap_h / 24) if gap_h > 0 else 0
    return StoreImpact(dep.destination, dep.transfer_id, sku, qty, pos.available, pos.daily_demand, dep.planned_arrival, new_arrival, iso(stockout), shortage)


def _order_impacts(state: State, transfer_id: str, ready_at: str, via: str) -> list[OrderImpact]:
    out = []
    for o in state.orders.values():
        for item in o.items:
            if item.allocation == "awaiting_inbound" and item.awaiting_transfer == transfer_id:
                facility = state.transfers[transfer_id].destination
                projected = shift(ready_at, carrier_hours(state, facility, o))
                out.append(OrderImpact(o.order_id, item.sku, item.qty, via, o.promised_by, projected, ts(projected) > ts(o.promised_by)))
    return out


def transfer_impact(state: State, transfer_id: str) -> Impact:
    t = state.transfers[transfer_id]
    ready = expected_ready(state, t)
    impact = Impact(transfer_id, round(transfer_delay_h(state, t), 1), ready)
    impact.orders += _order_impacts(state, transfer_id, ready, transfer_id)
    for dep in sorted(state.transfers.values(), key=lambda x: x.transfer_id):
        if dep.depends_on != transfer_id or dep.status not in ("Planned", "Loading"):
            continue
        new_dep, new_arr = delayed_schedule(state, dep, ready)
        impact.dependents.append((dep.transfer_id, new_dep, new_arr))
        if state.facilities[dep.destination].facility_type == "Store":
            for line in dep.lines:
                impact.stores.append(_store_impact(state, dep, line.sku, line.qty, new_arr))
        store_ready = shift(new_arr, STORE_HANDLING_H)
        impact.orders += _order_impacts(state, dep.transfer_id, store_ready, f"{dep.transfer_id} ← {transfer_id}")
    demand: dict[str, int] = {}
    for o in impact.orders:
        if o.via == transfer_id:
            demand[o.sku] = demand.get(o.sku, 0) + o.qty
    for dep_id, _, _ in impact.dependents:
        for line in state.transfers[dep_id].lines:
            demand[line.sku] = demand.get(line.sku, 0) + line.qty
    for sku, need in demand.items():
        gap = need - max(0, position(state, sku, t.destination).available)
        if gap > 0:
            impact.dc_gap[sku] = gap
    return impact


# ---------- sourcing options ----------
@dataclass
class SourceOption:
    facility_id: str
    sku: str
    available: int
    covers: int
    lead_h: float
    arrives: str


def source_options(state: State, sku: str, destination: str, need: int) -> list[SourceOption]:
    """Facilities (DCs and 3PL) holding free stock, ordered by arrival time at the destination."""
    out = []
    for fid, f in state.facilities.items():
        if fid == destination or f.facility_type not in ("Distribution centre", "3PL gateway"):
            continue
        avail = position(state, sku, fid).available
        if avail <= 0:
            continue
        lead = DISPATCH_PREP_H + road_hours(state, fid, destination)
        out.append(SourceOption(fid, sku, avail, min(avail, need), lead, shift(state.now, lead)))
    return sorted(out, key=lambda o: (o.lead_h, -o.covers))


def reallocation_candidates(state: State, impact: Impact) -> list[tuple[OrderImpact, str, str]]:
    """At-risk direct backorders that another DC could still deliver on time: (order, facility, projected delivery)."""
    out = []
    claimed: dict[tuple[str, str], int] = {}
    for oi in sorted(impact.orders_at_risk, key=lambda x: x.promised_by):
        order = state.orders[oi.order_id]
        if order.channel != "Online":
            continue
        best = None
        for opt in source_options(state, oi.sku, state.transfers[impact.transfer_id].destination, oi.qty):
            left = opt.available - claimed.get((opt.facility_id, oi.sku), 0)
            if left < oi.qty:
                continue
            projected = shift(state.now, PICK_PACK_H + carrier_hours(state, opt.facility_id, order))
            if ts(projected) <= ts(order.promised_by) and (best is None or ts(projected) < ts(best[1])):
                best = (opt.facility_id, projected)
        if best:
            claimed[(best[0], oi.sku)] = claimed.get((best[0], oi.sku), 0) + oi.qty
            out.append((oi, best[0], best[1]))
    return out


# ---------- exception detection ----------
EVIDENCE_TYPES = {
    "TRANSFER_LATE": {"TRANSFER_ETA_UPDATED", "TRANSFER_DEPARTED", "TRANSFER_CHECKPOINT"},
    "CUSTOMS_HOLD": {"TRANSFER_CUSTOMS_HOLD", "TRANSFER_ARRIVED"},
    "TRANSFER_EXCEPTION": {"TRANSFER_QUALITY_HOLD", "TRANSFER_ARRIVED"},
    "SHORT_RECEIPT": {"TRANSFER_RECEIVED"},
    "CARRIER_DELAY": {"CARRIER_SCAN", "CARRIER_DELAY", "ORDER_SHIPPED"},
    "INTEGRATION_REJECTED": {"INTEGRATION_REJECTED"},
    "ALLOCATION_FAILED": {"ALLOCATION_FAILED"},
}
KIND_LABEL = {
    "TRANSFER_LATE": "Transfer delayed", "CUSTOMS_HOLD": "Customs hold", "TRANSFER_EXCEPTION": "Quality hold",
    "SHORT_RECEIPT": "Short receipt", "CARRIER_DELAY": "Carrier delay", "INTEGRATION_REJECTED": "Order rejected",
    "ALLOCATION_FAILED": "Allocation failed",
}
PRIORITY_RULES = [
    "P1: a customer promise or store stockout falls within 48 h of now, or a promise has already passed.",
    "P2: other downstream impact, or a transfer delay of 24 h or more.",
    "P3: everything else.",
    "Within a priority: more affected orders first, then oldest first.",
]


def _evidence(state: State, kind: str, record_id: str) -> list[str]:
    wanted = EVIDENCE_TYPES.get(kind, set())
    return [e.event_id for e in state.events if e.record_id == record_id and e.event_type in wanted and e.outcome == "applied"]


def _detected_at(state: State, evidence: list[str]) -> str:
    times = [e.ts for e in state.events if e.event_id in evidence]
    return max(times) if times else state.now


def _transfer_priority(state: State, impact: Impact) -> tuple[str, str]:
    horizon = ts(state.now) + timedelta(hours=48)
    urgent_orders = [o for o in impact.orders_at_risk if ts(o.promised_by) <= horizon]
    urgent_stores = [s for s in impact.stores if s.shortage_units > 0 and ts(s.stockout_at) <= horizon]
    if urgent_orders or urgent_stores:
        bits = []
        if urgent_orders:
            bits.append(f"{len(urgent_orders)} customer promise(s) due within 48 h")
        if urgent_stores:
            bits.append(f"{len({s.facility_id for s in urgent_stores})} store(s) stock out within 48 h")
        return "P1", " and ".join(bits)
    if impact.orders or impact.stores:
        return "P2", "Downstream orders or store replenishment depend on this transfer"
    if impact.delay_h >= 24:
        return "P2", f"Delay of {impact.delay_h:.0f} h"
    return "P3", "No downstream dependency found"


def _order_priority(state: State, order: Order) -> tuple[str, str]:
    hours = (ts(order.promised_by) - ts(state.now)).total_seconds() / 3600
    if hours <= 24:
        return "P1", "Promise passed" if hours < 0 else f"Promise due in {hours:.0f} h"
    if hours <= 72:
        return "P2", f"Promise due in {hours:.0f} h"
    return "P3", f"Promise due in {hours / 24:.0f} days"


def _transfer_exception(state: State, kind: str, t: Transfer, title: str) -> OpsException:
    impact = transfer_impact(state, t.transfer_id)
    priority, reason = _transfer_priority(state, impact)
    if kind == "SHORT_RECEIPT":
        stranded = [o for o in state.orders.values() if o.issue == "ALLOCATION_FAILED" and any(e.record_id == o.order_id and t.transfer_id in e.detail for e in state.events)]
        priority, reason = ("P2", "Orders left without stock") if stranded else ("P3", "Shortfall absorbed; no order left without stock")
    evidence = _evidence(state, kind, t.transfer_id)
    return OpsException(
        exception_id=f"EX-{kind}-{t.transfer_id}", kind=kind, record_type="transfer", record_id=t.transfer_id, title=title,
        detected_at=_detected_at(state, evidence), priority=priority, priority_reason=reason, evidence=evidence,
        facility_id=t.destination, affected_orders=sorted({o.order_id for o in impact.orders_at_risk}),
        affected_stores=impact.stores_short, shortage_units=impact.store_shortage + sum(o.qty for o in impact.orders_at_risk),
        facts={"delay_h": impact.delay_h, "ready_at": impact.ready_at, "eta": t.eta, "dependents": [d[0] for d in impact.dependents]},
    )


def _order_exception(state: State, kind: str, o: Order, title: str) -> OpsException:
    priority, reason = _order_priority(state, o)
    evidence = _evidence(state, kind, o.order_id)
    facility = next((i.facility_id for i in o.items if i.facility_id), "")
    return OpsException(
        exception_id=f"EX-{kind}-{o.order_id}", kind=kind, record_type="order", record_id=o.order_id, title=title,
        detected_at=_detected_at(state, evidence), priority=priority, priority_reason=reason, evidence=evidence,
        facility_id=facility, affected_orders=[o.order_id], shortage_units=sum(i.qty for i in o.items),
    )


def detect_exceptions(state: State) -> list[OpsException]:
    """Evaluate every rule against current state. Exception ids are stable so repeated runs update, not duplicate."""
    found: list[OpsException] = []
    now = ts(state.now)
    for t in state.transfers.values():
        route = f"{state.facilities[t.source].city} → {facility_name(state, t.destination)}"
        if t.status == "Customs hold":
            found.append(_transfer_exception(state, "CUSTOMS_HOLD", t, f"{t.transfer_id} held at customs · {route}"))
        elif t.status == "Exception":
            found.append(_transfer_exception(state, "TRANSFER_EXCEPTION", t, f"{t.transfer_id} quality hold · {route}"))
        elif t.status == "Partially received":
            short = sum(l.qty - l.received for l in t.lines)
            found.append(_transfer_exception(state, "SHORT_RECEIPT", t, f"{t.transfer_id} received {short} units short · {route}"))
        elif t.status in ("Planned", "Loading", "In transit") and not t.actual_arrival and not t.depends_on:
            # Transfers waiting on upstream stock are reported through the upstream exception instead.
            delay = transfer_delay_h(state, t)
            if delay >= LATE_GRACE_H and (t.status == "In transit" or now > ts(t.planned_departure)):
                found.append(_transfer_exception(state, "TRANSFER_LATE", t, f"{t.transfer_id} delayed {delay:.0f} h · {route}"))
    for o in state.orders.values():
        if o.issue == "INTEGRATION_REJECTED":
            found.append(_order_exception(state, "INTEGRATION_REJECTED", o, f"{o.order_id} rejected by carrier booking"))
        elif o.issue == "ALLOCATION_FAILED":
            found.append(_order_exception(state, "ALLOCATION_FAILED", o, f"{o.order_id} could not be allocated"))
        elif o.status == "Shipped" and o.channel == "Online" and o.last_scan_at:
            gap = (now - ts(o.last_scan_at)).total_seconds() / 3600
            if gap > CARRIER_SCAN_GAP_H:
                found.append(_order_exception(state, "CARRIER_DELAY", o, f"{o.order_id} no carrier scan for {gap:.0f} h"))
    return found


def sort_key(ex: OpsException) -> tuple:
    return ({"P1": 0, "P2": 1, "P3": 2}[ex.priority], -len(ex.affected_orders), ex.detected_at)


def order_state_label(order: Order) -> str:
    if order.issue == "INTEGRATION_REJECTED":
        return "Rejected"
    if order.issue == "ALLOCATION_FAILED":
        return "Allocation failed"
    if order.status == "Created" and any(i.allocation == "awaiting_inbound" for i in order.items):
        return "Awaiting stock"
    return order.status


def order_projection(state: State, order: Order) -> str:
    """Projected delivery for an open order from its slowest item; '' when not computable."""
    if order.status in ("Delivered", "Return in transit", "Returned"):
        return order.delivered_at
    if order.status == "Shipped":
        return order.promised_by
    worst = None
    for item in order.items:
        if item.allocation == "awaiting_inbound":
            t = state.transfers[item.awaiting_transfer]
            if t.depends_on:
                ready = shift(delayed_schedule(state, t, expected_ready(state, state.transfers[t.depends_on]))[1], STORE_HANDLING_H)
            else:
                ready = expected_ready(state, t)
            cand = shift(ready, carrier_hours(state, t.destination, order))
        elif item.allocation == "allocated":
            cand = shift(state.now, PICK_PACK_H + carrier_hours(state, item.facility_id, order))
        else:
            return ""
        worst = cand if worst is None or ts(cand) > ts(worst) else worst
    return worst or ""


def describe_window(value: str) -> str:
    return nice(value)
