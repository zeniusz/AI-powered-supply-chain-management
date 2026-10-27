"""Communication rules engine: which exception informs whom, with what message, and how it is delivered.

A rule turns an open exception into zero or more notifications. Each notification has a dedupe key built from
the rule, exception, recipient and the facts the message states (for example the new ETA). Processing the same
event twice therefore yields the same keys and no new messages; a changed fact supersedes the unsent draft.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from domain import HUB, Impact, facility_name, sku_name, transfer_impact
from models import Notification, OpsException, State, nice, ts

PENDING = {"Draft", "Awaiting approval", "Failed"}
CS_TEAM = "Customer service · Benelux & DE"


@dataclass
class Draft:
    rule_id: str
    audience: str
    recipient: str
    recipient_ref: str
    channel: str
    subject: str
    body: str
    requires_approval: bool
    fingerprint: str
    reason: str


RULES = {
    "STORE_REPLENISHMENT_DELAY": ("Store", "A store replenishment depends on a delayed or held transfer", False),
    "DC_INBOUND_DELAY": ("DC team", "The destination DC must re-plan receiving and dependent dispatches", False),
    "CS_BRIEFING": ("Customer service", "Customer orders are at risk or need manual follow-up", False),
    "CUSTOMER_DELIVERY_UPDATE": ("Customer", "A customer delivery estimate changed", True),
    "CUSTOMER_CARRIER_DELAY": ("Customer", "A shipped parcel has no carrier progress", True),
}


def _day(value: str) -> str:
    return ts(value).strftime("%A %d %B")


def _store_drafts(state: State, ex: OpsException, impact: Impact) -> list[Draft]:
    out = []
    by_store: dict[str, list] = {}
    for s in impact.stores:
        by_store.setdefault(s.facility_id, []).append(s)
    for store_id, rows in by_store.items():
        store = state.facilities[store_id]
        lines = []
        for r in rows:
            line = f"- {sku_name(state, r.sku)} ({r.sku}): {r.qty} units on {r.transfer_id}, now expected {nice(r.new_arrival)} (was {nice(r.planned_arrival)})."
            if r.shortage_units:
                line += f" You have {r.available} available and sell about {r.daily_demand:g}/day, so stock runs out around {nice(r.stockout_at)}: roughly {r.shortage_units} units of demand uncovered."
            lines.append(line)
        body = (f"Hello {store.city} team,\n\nYour replenishment is delayed because {ex.record_id} into {facility_name(state, state.transfers[ex.record_id].destination)} "
                f"is running about {impact.delay_h:.0f} h late.\n\n" + "\n".join(lines) +
                "\n\nOperations is reviewing an emergency transfer and will confirm by message. No action is needed from you yet.\n\nThreadline Operations")
        fp = "|".join(f"{r.sku}:{r.new_arrival}:{r.shortage_units}" for r in rows)
        out.append(Draft("STORE_REPLENISHMENT_DELAY", "Store", store.contact, store_id, store.channel,
                         f"Delayed replenishment · {store.name}", body, False, fp,
                         f"{ex.record_id} delay pushes {', '.join(sorted({r.transfer_id for r in rows}))} to {nice(rows[0].new_arrival)}"))
    return out


def _dc_draft(state: State, ex: OpsException, impact: Impact) -> list[Draft]:
    t = state.transfers[ex.record_id]
    dc = state.facilities[t.destination]
    if dc.facility_type != "Distribution centre":
        return []
    units = sum(l.qty - l.received for l in t.lines)
    deps = ", ".join(f"{d} (now departs {nice(dep)})" for d, dep, _ in impact.dependents) or "none"
    body = (f"{t.transfer_id} from {facility_name(state, t.source)} ({units} units, ref {t.reference}) is now expected to be usable from {nice(impact.ready_at)} "
            f"instead of {nice(t.planned_arrival)}.\nCause: {ex.title}.\nRe-plan receiving labour accordingly. Dependent dispatches: {deps}.")
    return [Draft("DC_INBOUND_DELAY", "DC team", dc.contact, dc.facility_id, dc.channel, f"Inbound change · {t.transfer_id}", body, False,
                  impact.ready_at, f"Destination DC of {t.transfer_id}")]


def _cs_draft(state: State, ex: OpsException, orders: list[tuple[str, str, str]]) -> list[Draft]:
    if not orders:
        return []
    rows = "\n".join(f"- {oid}: promised {nice(promise)}, now projected {nice(proj)}" for oid, promise, proj in orders)
    body = (f"{ex.title}.\nOrders affected:\n{rows}\n\nCustomer updates are drafted in Communications and need approval before sending. "
            "Please hold proactive contact until then.")
    fp = "|".join(f"{o}:{p}" for o, _, p in orders)
    return [Draft("CS_BRIEFING", "Customer service", CS_TEAM, "CS", "email", f"Orders at risk · {ex.record_id}", body, False, fp,
                  f"{len(orders)} order(s) at risk from {ex.record_id}")]


def _customer_draft(state: State, ex: OpsException, order_id: str, new_date: str, rule: str = "CUSTOMER_DELIVERY_UPDATE") -> Draft:
    o = state.orders[order_id]
    first = o.customer_name.split()[0]
    items = ", ".join(sku_name(state, i.sku).split(" · ")[0].lower() for i in o.items if i.allocation in ("awaiting_inbound", "unallocated", "allocated"))
    if o.channel == "Click & collect":
        promise = f"We now expect it to be ready for collection at {facility_name(state, o.pickup_store)} on {_day(new_date)}."
    else:
        promise = f"We now expect to deliver it by {_day(new_date)}."
    body = (f"Hi {first},\n\nPart of your order {o.order_id} ({items}) is taking longer to reach us than planned. {promise}\n\n"
            "You don't need to do anything. We'll send tracking details as soon as it ships.\n\nThreadline customer care")
    return Draft(rule, "Customer", o.customer_email_masked, order_id, "email", f"An update on your order {o.order_id}", body, True,
                 new_date, f"Delivery estimate moved from {nice(o.promised_by)} to {nice(new_date)}")


def _carrier_customer_draft(state: State, ex: OpsException) -> Draft:
    o = state.orders[ex.record_id]
    body = (f"Hi {o.customer_name.split()[0]},\n\nYour parcel for order {o.order_id} is taking longer than expected. The last update from "
            f"{o.carrier} was on {ts(o.last_scan_at).strftime('%A %d %B')}. We're checking with them and will update you as soon as it moves again.\n\n"
            "Threadline customer care")
    return Draft("CUSTOMER_CARRIER_DELAY", "Customer", o.customer_email_masked, o.order_id, "email", f"Your parcel {o.tracking_code}", body, True,
                 o.last_scan_at, f"No carrier scan since {nice(o.last_scan_at)}")


def drafts_for(state: State, ex: OpsException) -> list[Draft]:
    """The complete set of messages this exception should have right now."""
    if ex.kind in ("TRANSFER_LATE", "CUSTOMS_HOLD", "SHORT_RECEIPT"):
        impact = transfer_impact(state, ex.record_id)
        out = _store_drafts(state, ex, impact) + _dc_draft(state, ex, impact)
        repromised = ex.facts.get("repromised", {})
        customer_dates: dict[str, str] = {}
        for o in impact.orders_at_risk:  # an order's date is set by its slowest item
            customer_dates[o.order_id] = max(customer_dates.get(o.order_id, o.projected_delivery), o.projected_delivery)
        for oid in repromised:
            customer_dates[oid] = state.orders[oid].promised_by
        cs_rows = [(oid, repromised.get(oid, state.orders[oid].promised_by), d) for oid, d in sorted(customer_dates.items())]
        out += _cs_draft(state, ex, cs_rows)
        out += [_customer_draft(state, ex, oid, d) for oid, d in sorted(customer_dates.items())]
        return out
    if ex.kind == "CARRIER_DELAY":
        return [_carrier_customer_draft(state, ex)]
    if ex.kind == "ALLOCATION_FAILED":
        o = state.orders[ex.record_id]
        sku = o.items[0].sku
        body = (f"{o.order_id} could not be allocated: no sellable {sku_name(state, sku)} in the network (stock at {facility_name(state, HUB)} is quarantined). "
                f"Promise: {nice(o.promised_by)}. Contact the customer to offer an alternative colour or cancel the line.")
        return [Draft("CS_BRIEFING", "Customer service", CS_TEAM, "CS", "email", f"Allocation failed · {o.order_id}", body, False, o.order_id,
                      "Order cannot be fulfilled from current stock")]
    if ex.kind == "INTEGRATION_REJECTED":
        o = state.orders[ex.record_id]
        body = (f"{o.order_id}: carrier booking rejected because the delivery address has no house number. "
                f"Contact the customer to confirm the address before {nice(o.promised_by)}, then resubmit the order.")
        return [Draft("CS_BRIEFING", "Customer service", CS_TEAM, "CS", "email", f"Address check needed · {o.order_id}", body, False, o.order_id,
                      "Order blocked by integration validation")]
    return []


# ---------- delivery ----------
def delivery_mode() -> str:
    return "webhook" if os.getenv("THREADLINE_NOTIFY_WEBHOOK_URL") else "simulated"


def deliver(state: State, n: Notification, actor: str) -> None:
    """Simulated by default. With THREADLINE_NOTIFY_WEBHOOK_URL set, internal messages are POSTed there; customer messages stay simulated."""
    n.attempts += 1
    stamp = state.now
    if delivery_mode() == "webhook" and n.audience != "Customer":
        try:
            req = urllib.request.Request(os.environ["THREADLINE_NOTIFY_WEBHOOK_URL"], method="POST", headers={"Content-Type": "application/json"},
                                         data=json.dumps({"to": n.recipient, "subject": n.subject, "body": n.body, "id": n.notification_id}).encode())
            with urllib.request.urlopen(req, timeout=8):
                pass
            n.status, n.sent_at, n.last_error = "Sent", stamp, ""
            n.history.append(f"{stamp} · sent via webhook by {actor}")
        except Exception as exc:
            n.status, n.last_error = "Failed", f"{type(exc).__name__}: {str(exc)[:120]}"
            n.history.append(f"{stamp} · webhook delivery failed: {n.last_error}")
        return
    facility = state.facilities.get(n.recipient_ref)
    if facility is not None and not facility.channel_ok and n.attempts == 1:
        n.status, n.last_error = "Failed", f"Mail server rejected {n.recipient}: mailbox not provisioned (simulated)"
        n.history.append(f"{stamp} · attempt {n.attempts} failed: {n.last_error}")
        return
    n.status, n.sent_at, n.last_error = "Simulated send", stamp, ""
    n.history.append(f"{stamp} · simulated send by {actor} (attempt {n.attempts}); nothing left this machine")


def sync_notifications(state: State, ex: OpsException, trigger: str, next_id) -> list[Notification]:
    """Create missing notifications for an exception, supersede stale unsent ones. Returns the new notifications."""
    wanted = {}
    for d in drafts_for(state, ex) if ex.status != "Resolved" else []:
        key = f"{d.rule_id}|{ex.exception_id}|{d.recipient_ref}|{d.fingerprint}"
        wanted[key] = d
    existing = {n.dedupe_key: n for n in state.notifications.values() if n.exception_id == ex.exception_id}
    for key, n in existing.items():
        if key not in wanted and n.status in PENDING:
            n.status = "Superseded"
            n.history.append(f"{state.now} · superseded: facts changed or exception resolved")
    created = []
    for key, d in wanted.items():
        if key in existing:
            continue
        n = Notification(next_id(), key, d.rule_id, ex.exception_id, trigger, d.audience, d.recipient, d.recipient_ref, d.channel, d.subject, d.body,
                         d.requires_approval, "Awaiting approval" if d.requires_approval else "Draft", state.now, d.reason)
        n.history.append(f"{state.now} · created by rule {d.rule_id} from {trigger}")
        state.notifications[n.notification_id] = n
        created.append(n)
    return created
