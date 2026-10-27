import re

import pytest

import assistant
import engine
from domain import detect_exceptions, position, transfer_impact, validate_inventory
from models import Event, state_from_dict

LATE = "EX-TRANSFER_LATE-TR-5301"


@pytest.fixture
def state():
    return engine.new_state()


# ---------- inventory arithmetic ----------
def test_buckets_add_up_and_never_double_count(state):
    for sku, fid in [("JKT-CHR", "DC-ES-01"), ("SNK-WHT", "DC-DE-01"), ("OVS-OLV", "DC-ES-01"), ("BLT-BRN", "STORE-ES-01")]:
        p = position(state, sku, fid)
        assert p.on_hand == p.allocated + p.reserved + p.quarantined + p.available
    jacket = position(state, "JKT-CHR", "DC-ES-01")
    assert (jacket.allocated, jacket.reserved, jacket.available) == (1, 40, 29)  # OR-20482 line + TR-5304 loading
    overshirt = position(state, "OVS-OLV", "DC-ES-01")
    assert overshirt.available == 0 and overshirt.incoming == 420 and overshirt.in_transit == 420
    assert validate_inventory(state) == []


def test_dependent_transfer_does_not_reserve_stock_it_does_not_have(state):
    assert position(state, "OVS-OLV", "DC-ES-01").reserved == 0  # TR-5311/12 wait on TR-5301


# ---------- downstream impact ----------
def test_delay_impact_reaches_stores_and_orders(state):
    im = transfer_impact(state, "TR-5301")
    assert im.delay_h == 48
    assert [d[0] for d in im.dependents] == ["TR-5311", "TR-5312", "TR-5313"]
    assert im.stores_short == ["STORE-ES-01", "STORE-FR-01", "STORE-IT-01"]
    at_risk = {o.order_id for o in im.orders_at_risk}
    assert at_risk == {"OR-20482", "OR-20490", "OR-20491", "OR-20493", "OR-20494"}
    assert "OR-20492" not in at_risk  # promise Fri 30 Oct still met
    two_hop = next(o for o in im.orders if o.order_id == "OR-20494")
    assert two_hop.via == "TR-5312 ← TR-5301"


def test_priority_rules_are_transparent(state):
    found = {e.exception_id: e for e in detect_exceptions(state)}
    assert found[LATE].priority == "P1" and "48 h" in found[LATE].priority_reason
    assert found["EX-TRANSFER_EXCEPTION-TR-5310"].priority == "P3"
    assert found["EX-TRANSFER_LATE-TR-5306"].priority == "P2"  # 36 h delay, nothing depends on it


# ---------- events: milestones, transitions, idempotency ----------
def test_duplicate_event_is_ignored_without_side_effects(state):
    before = (len(state.notifications), state.transfers["TR-5301"].eta)
    original = next(e for e in state.events if e.event_id == "EV-1022")
    assert engine.process_event(state, original) == "duplicate ignored"
    assert (len(state.notifications), state.transfers["TR-5301"].eta) == before


def test_invalid_transitions_are_rejected(state):
    assert engine.manual_event(state, "transfer", "TR-5311", "TRANSFER_DEPARTED", "try").startswith("rejected: TR-5311 is waiting for TR-5301")
    assert engine.manual_event(state, "order", "OR-20482", "ORDER_SHIPPED", "try").startswith("rejected")
    assert engine.manual_event(state, "order", "OR-20481", "ORDER_PICKED", "try").startswith("rejected")
    assert state.transfers["TR-5311"].status == "Planned"


def test_order_lifecycle_moves_stock(state):
    before = position(state, "BAG-CNV", "DC-ES-01").on_hand
    for etype in ("ORDER_PACKED", "ORDER_SHIPPED", "ORDER_DELIVERED"):
        assert engine.manual_event(state, "order", "OR-20495", etype, etype) == "applied"
    assert state.orders["OR-20495"].status == "Delivered"
    assert position(state, "BAG-CNV", "DC-ES-01").on_hand == before - 1


def test_receipt_allocates_backorders_releases_dependents_and_flags_short_receipt(state):
    engine.process_event(state, Event("T1", "2026-10-29T07:20", "TRANSFER_ARRIVED", "transfer", "TR-5301", "test", "arrived"))
    engine.process_event(state, Event("T2", "2026-10-29T09:10", "TRANSFER_RECEIVED", "transfer", "TR-5301", "test", "short",
                                      {"received": {"OVS-OLV": 400, "TRS-STN": 260}}))
    assert state.transfers["TR-5301"].status == "Partially received"
    assert state.orders["OR-20491"].items[0].allocation == "allocated"
    assert state.transfers["TR-5311"].depends_on == "" and state.transfers["TR-5311"].planned_departure >= "2026-10-29T21:10"
    assert state.exceptions[LATE].status == "Resolved"
    assert state.exceptions["EX-SHORT_RECEIPT-TR-5301"].status == "Open"
    assert validate_inventory(state) == []


def test_customs_release_unblocks_onward_haulage(state):
    engine.process_event(state, Event("C1", "2026-10-27T12:30", "TRANSFER_CUSTOMS_RELEASED", "transfer", "TR-5302", "test", "released"))
    engine.process_event(state, Event("C2", "2026-10-27T12:45", "TRANSFER_RECEIVED", "transfer", "TR-5302", "test", "received"))
    assert state.transfers["TR-5309"].depends_on == ""
    assert position(state, "KNT-GRY", "PORT-BCN-01").reserved == 300


# ---------- communications ----------
def test_rules_create_the_right_messages(state):
    msgs = [n for n in state.notifications.values() if n.exception_id == LATE]
    by_rule = {}
    for n in msgs:
        by_rule.setdefault(n.rule_id, []).append(n)
    assert len(by_rule["STORE_REPLENISHMENT_DELAY"]) == 3
    assert len(by_rule["CUSTOMER_DELIVERY_UPDATE"]) == 5
    assert all(n.status == "Awaiting approval" for n in by_rule["CUSTOMER_DELIVERY_UPDATE"])
    sent = [n for n in by_rule["STORE_REPLENISHMENT_DELAY"] if n.status == "Simulated send"]
    failed = [n for n in by_rule["STORE_REPLENISHMENT_DELAY"] if n.status == "Failed"]
    assert len(sent) == 2 and failed[0].recipient_ref == "STORE-IT-01"
    assert engine.retry_notification(state, failed[0].notification_id) == "Simulated send"


def test_customer_messages_expose_no_internal_data(state):
    internal = re.compile(r"TR-\d|DC-|FAC-|Porto|Izmir|factory|Atlantic|breakdown|quarantin", re.I)
    for n in state.notifications.values():
        if n.audience == "Customer":
            assert not internal.search(n.body + n.subject), n.body


def test_no_duplicate_messages_when_rules_rerun(state):
    count = len(state.notifications)
    engine.refresh(state, "manual rerun")
    engine.refresh(state, "manual rerun")
    assert len(state.notifications) == count


def test_reallocation_fixes_orders_and_supersedes_their_drafts(state):
    moved = engine.reallocate_orders(state, LATE)
    assert len(moved) == 5
    im = transfer_impact(state, "TR-5301")
    assert {o.order_id for o in im.orders_at_risk} == {"OR-20494"}
    stale = [n for n in state.notifications.values() if n.recipient_ref == "OR-20491"]
    assert stale and all(n.status == "Superseded" for n in stale)
    assert validate_inventory(state) == []


def test_customer_approval_flow(state):
    nid = next(n.notification_id for n in state.notifications.values() if n.status == "Awaiting approval")
    assert engine.approve_and_send(state, nid, "Edited text") == "Simulated send"
    n = state.notifications[nid]
    assert n.approved_by == engine.OPERATOR and n.body == "Edited text"
    with pytest.raises(engine.Rejected):
        engine.approve_and_send(state, nid)


def test_emergency_transfer_reduces_store_shortage(state):
    before = next(s.shortage_units for s in transfer_impact(state, "TR-5301").stores if s.facility_id == "STORE-FR-01" and s.sku == "OVS-OLV")
    engine.emergency_replenishment(state, LATE, "3PL-FR-01", "STORE-FR-01", "OVS-OLV", 10)
    after = next(s.shortage_units for s in transfer_impact(state, "TR-5301").stores if s.facility_id == "STORE-FR-01" and s.sku == "OVS-OLV")
    assert before > 0 and after == 0
    assert position(state, "OVS-OLV", "3PL-FR-01").reserved == 10


def test_state_round_trips_through_json(state):
    engine.assign(state, LATE, "You")
    copy = state_from_dict(state.to_dict())
    assert copy.exceptions[LATE].owner == "You" and copy.transfers["TR-5301"].lines[0].qty == 420


def test_full_scenario_runs_without_rejections(state):
    outcomes = []
    while (r := engine.next_scripted_event(state)):
        outcomes.append(r)
    assert sum("duplicate ignored" in o for o in outcomes) == 1
    assert not [o for o in outcomes if "rejected" in o]
    assert validate_inventory(state) == []


# ---------- assistant ----------
def test_every_tool_spec_is_implemented_and_actions_never_execute(state):
    for spec in assistant.TOOL_SPECS:
        name = spec["function"]["name"]
        assert "unknown tool" not in str(assistant.run_tool(state, name, {}))
    result = assistant.run_tool(state, "propose_action", {"action": "reallocate_orders", "exception_id": LATE})
    assert result["executed"] is False
    assert all(i.allocation == "awaiting_inbound" for i in state.orders["OR-20491"].items)


def test_rule_based_answers_are_grounded_in_tool_calls(state, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reply = assistant.ask(state, "Which orders are affected by transfer TR-5301?", {})
    assert reply.tool_calls[0]["tool"] == "transfer_impact"
    assert "OR-20494" in reply.text and "OR-20492" in reply.text
    advice = assistant.ask(state, "What should I do?", {"exception_id": LATE})
    assert {p["action"] for p in advice.proposals} >= {"reallocate_orders", "emergency_replenishment"}


def test_assistant_without_a_selected_record_works_on_the_top_exception(state, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    drafts = assistant.ask(state, "Notify a store that its incoming transfer is delayed", {})
    assert drafts.tool_calls[0]["tool"] == "draft_messages" and "Madrid" in drafts.text
    ticket = assistant.ask(state, "Create an engineering ticket for a recurring allocation failure", {})
    assert ticket.tool_calls[0]["tool"] == "engineering_ticket"


def test_saved_state_from_an_older_seed_is_discarded(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setattr(engine, "STATE_FILE", path)
    old = engine.new_state().to_dict()
    old["seed_version"] = "older"
    path.write_text(__import__("json").dumps(old), encoding="utf8")
    fresh = engine.load_state()
    assert fresh.seed_version == engine.SEED_VERSION and not path.exists()
