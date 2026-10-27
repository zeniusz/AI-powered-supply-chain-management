"""Typed records for the Threadline demo. Times are ISO strings ("2026-10-27T09:00") on the demo clock."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from typing import Any

TIME_FMT = "%Y-%m-%dT%H:%M"


def ts(value: str) -> datetime:
    return datetime.strptime(value[:16], TIME_FMT)


def iso(value: datetime) -> str:
    return value.strftime(TIME_FMT)


def shift(value: str, hours: float) -> str:
    return iso(ts(value) + timedelta(hours=hours))


def nice(value: str | None) -> str:
    """'2026-10-27T09:00' -> 'Tue 27 Oct 09:00'."""
    if not value:
        return "—"
    return ts(value).strftime("%a %d %b %H:%M")


@dataclass
class Facility:
    facility_id: str
    name: str
    facility_type: str  # Factory | Material supplier | Port | Distribution centre | 3PL gateway | Store
    city: str
    country: str
    lat: float
    lon: float
    contact: str = ""
    channel: str = "email"
    channel_ok: bool = True  # False simulates a misconfigured delivery channel


@dataclass
class Sku:
    sku: str
    name: str
    category: str
    price_eur: float
    image: str = ""
    unit: str = "units"
    sellable: bool = True


@dataclass
class StockRecord:
    """Stored stock facts. Allocated, reserved, available, incoming and in-transit are derived (see domain.py)."""
    sku: str
    facility_id: str
    on_hand: int
    quarantined: int = 0
    daily_demand: float = 0.0  # store sell-through, used for stockout projection
    safety_stock: int = 0


@dataclass
class TransferLine:
    sku: str
    qty: int
    received: int = 0


@dataclass
class Transfer:
    transfer_id: str
    kind: str  # Factory → DC, Port → DC, Inter-DC, DC → Store, Supplier → Factory, Factory → Port, Factory → 3PL
    source: str
    destination: str
    mode: str
    carrier: str
    lines: list[TransferLine]
    status: str  # Planned | Loading | In transit | Customs hold | Exception | Received | Partially received
    planned_departure: str
    planned_arrival: str
    actual_departure: str = ""
    actual_arrival: str = ""
    eta: str = ""  # current estimate; equals planned_arrival until an event changes it
    depends_on: str = ""  # upstream transfer whose stock this transfer needs before it can depart
    exception: str = ""
    reference: str = ""


@dataclass
class OrderItem:
    line_id: str
    sku: str
    qty: int
    size: str
    facility_id: str = ""  # fulfilling facility once allocated
    allocation: str = "allocated"  # allocated | awaiting_inbound | unallocated | shipped | delivered | returned
    awaiting_transfer: str = ""


@dataclass
class Order:
    order_id: str
    channel: str  # Online | Click & collect
    status: str  # Created | Allocated | Picked | Packed | Shipped | Delivered | Return in transit | Returned
    created_at: str
    promised_by: str
    customer_ref: str
    customer_name: str
    customer_email_masked: str
    city: str
    country: str
    dest_lat: float
    dest_lon: float
    items: list[OrderItem]
    carrier: str = ""
    tracking_code: str = ""
    shipped_at: str = ""
    delivered_at: str = ""
    last_scan_at: str = ""
    last_scan_location: str = ""
    pickup_store: str = ""
    issue: str = ""  # current blocking issue code, e.g. INTEGRATION_REJECTED


@dataclass
class Event:
    event_id: str
    ts: str
    event_type: str
    record_type: str  # transfer | order
    record_id: str
    source: str
    detail: str
    payload: dict[str, Any] = field(default_factory=dict)
    customer_visible: bool = False
    customer_text: str = ""
    outcome: str = "applied"  # applied | duplicate ignored | rejected: <reason>


@dataclass
class OpsException:
    exception_id: str
    kind: str  # TRANSFER_LATE | CUSTOMS_HOLD | TRANSFER_EXCEPTION | SHORT_RECEIPT | ALLOCATION_FAILED | CARRIER_DELAY | INTEGRATION_REJECTED
    record_type: str
    record_id: str
    title: str
    detected_at: str
    priority: str  # P1 | P2 | P3
    priority_reason: str
    status: str = "Open"  # Open | Investigating | Awaiting approval | Resolved
    owner: str = ""
    assigned_at: str = ""
    resolved_at: str = ""
    resolution: str = ""
    evidence: list[str] = field(default_factory=list)  # event ids
    facility_id: str = ""
    affected_orders: list[str] = field(default_factory=list)
    affected_stores: list[str] = field(default_factory=list)
    shortage_units: int = 0
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Notification:
    notification_id: str
    dedupe_key: str
    rule_id: str
    exception_id: str
    trigger_event: str
    audience: str  # Customer | Store | DC team | Customer service
    recipient: str
    recipient_ref: str  # facility id or order id
    channel: str
    subject: str
    body: str
    requires_approval: bool
    status: str  # Draft | Awaiting approval | Simulated send | Sent | Failed | Rejected | Superseded
    created_at: str
    reason: str
    attempts: int = 0
    last_error: str = ""
    sent_at: str = ""
    approved_by: str = ""
    history: list[str] = field(default_factory=list)


@dataclass
class AuditEntry:
    ts: str
    actor: str
    action: str
    record_id: str
    detail: str


@dataclass
class State:
    now: str
    facilities: dict[str, Facility]
    skus: dict[str, Sku]
    stock: list[StockRecord]
    transfers: dict[str, Transfer]
    orders: dict[str, Order]
    events: list[Event]
    exceptions: dict[str, OpsException] = field(default_factory=dict)
    notifications: dict[str, Notification] = field(default_factory=dict)
    audit: list[AuditEntry] = field(default_factory=list)
    processed_event_ids: list[str] = field(default_factory=list)
    script_cursor: int = 0
    auto_send_internal: bool = True
    seq: int = 0
    seed_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _build(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


def state_from_dict(d: dict) -> State:
    return State(
        now=d["now"],
        facilities={k: _build(Facility, v) for k, v in d["facilities"].items()},
        skus={k: _build(Sku, v) for k, v in d["skus"].items()},
        stock=[_build(StockRecord, s) for s in d["stock"]],
        transfers={k: Transfer(**{**v, "lines": [TransferLine(**l) for l in v["lines"]]}) for k, v in d["transfers"].items()},
        orders={k: Order(**{**v, "items": [OrderItem(**i) for i in v["items"]]}) for k, v in d["orders"].items()},
        events=[_build(Event, e) for e in d["events"]],
        exceptions={k: _build(OpsException, v) for k, v in d["exceptions"].items()},
        notifications={k: _build(Notification, v) for k, v in d["notifications"].items()},
        audit=[_build(AuditEntry, a) for a in d["audit"]],
        processed_event_ids=list(d.get("processed_event_ids", [])),
        script_cursor=d.get("script_cursor", 0),
        auto_send_internal=d.get("auto_send_internal", True),
        seq=d.get("seq", 0),
        seed_version=d.get("seed_version", ""),
    )
