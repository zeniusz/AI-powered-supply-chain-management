"""Fictional demo dataset. Every quantity, date and link here is synthetic and internally consistent.

The demo clock starts at DEMO_START. Base records describe the state at that moment; SEED_EVENTS are the history
that produced it (already applied). SCRIPT is the queue of future events released by "Next event".
"""
from __future__ import annotations

from models import Event, Facility, Order, OrderItem, Sku, State, StockRecord, Transfer, TransferLine

DEMO_START = "2026-10-27T09:00"
SEED_VERSION = "2026-10-27-eu-hub-barcelona-2"  # bump when seed data changes; older saved demo state is discarded


def _facilities() -> list[Facility]:
    F = Facility
    return [
        F("FAC-PT-01", "Porto Apparel Factory", "Factory", "Porto", "PT", 41.1579, -8.6291, "production.porto@threadline.example"),
        F("FAC-TR-01", "Izmir Garment Works", "Factory", "Izmir", "TR", 38.4237, 27.1428, "production.izmir@threadline.example"),
        F("FAC-IT-01", "Prato Materials Mill", "Material supplier", "Prato", "IT", 43.8777, 11.1020, "orders@prato-mill.example"),
        F("PORT-BCN-01", "Barcelona Port Terminal", "Port", "Barcelona", "ES", 41.3515, 2.1625, "customs.desk@threadline.example"),
        F("DC-ES-01", "Barcelona DC", "Distribution centre", "Barcelona", "ES", 41.3000, 2.0800, "Inbound team · Barcelona DC", "teams"),
        F("DC-DE-01", "Berlin DC", "Distribution centre", "Berlin", "DE", 52.4560, 13.5300, "Inbound team · Berlin DC", "teams"),
        F("3PL-FR-01", "Lyon 3PL Gateway", "3PL gateway", "Lyon", "FR", 45.7640, 4.8357, "ops@lyon-3pl.example"),
        F("STORE-ES-01", "Madrid Store", "Store", "Madrid", "ES", 40.4168, -3.7038, "madrid.store@threadline.example"),
        F("STORE-FR-01", "Paris Store", "Store", "Paris", "FR", 48.8566, 2.3522, "paris.store@threadline.example"),
        F("STORE-IT-01", "Milan Store", "Store", "Milan", "IT", 45.4642, 9.1900, "milan.store@threadline.example", "email", False),
        F("STORE-DE-01", "Berlin Mitte Store", "Store", "Berlin", "DE", 52.5310, 13.3847, "berlin.mitte@threadline.example"),
        F("STORE-GB-01", "London Store", "Store", "London", "GB", 51.5074, -0.1278, "london.store@threadline.example"),
        F("STORE-IE-01", "Dublin Store", "Store", "Dublin", "IE", 53.3498, -6.2603, "dublin.store@threadline.example"),
        F("STORE-NO-01", "Oslo Store", "Store", "Oslo", "NO", 59.9139, 10.7522, "oslo.store@threadline.example"),
        F("STORE-DK-01", "Copenhagen Store", "Store", "Copenhagen", "DK", 55.6761, 12.5683, "copenhagen.store@threadline.example"),
        F("STORE-AT-01", "Vienna Store", "Store", "Vienna", "AT", 48.2082, 16.3738, "vienna.store@threadline.example"),
        F("STORE-BE-01", "Brussels Store", "Store", "Brussels", "BE", 50.8503, 4.3517, "brussels.store@threadline.example"),
        F("STORE-PL-01", "Warsaw Store", "Store", "Warsaw", "PL", 52.2297, 21.0122, "warsaw.store@threadline.example"),
        F("STORE-SE-01", "Stockholm Store", "Store", "Stockholm", "SE", 59.3293, 18.0686, "stockholm.store@threadline.example"),
    ]


def _skus() -> list[Sku]:
    return [
        Sku("OVS-OLV", "Cotton utility overshirt · olive", "Shirts", 89.0, "overshirt_olive.webp"),
        Sku("TRS-STN", "Straight cotton trousers · stone", "Trousers", 79.0, "trousers_stone.webp"),
        Sku("JKT-CHR", "Lightweight utility jacket · charcoal", "Outerwear", 149.0, "outerwear_charcoal.webp"),
        Sku("KNT-GRY", "Merino crewneck · grey", "Knitwear", 99.0, "knit_crewneck_grey.webp"),
        Sku("SNK-WHT", "Leather low-top sneaker · off-white", "Footwear", 129.0, "sneaker_white.webp"),
        Sku("BAG-CNV", "Canvas weekend bag", "Bags", 119.0, "canvas_weekend_bag.webp"),
        Sku("BLT-BRN", "Leather belt · brown", "Accessories", 49.0, "leather_belt_brown.webp"),
        Sku("SHT-WHT", "Poplin shirt · white", "Shirts", 69.0, "poplin_shirt_white.webp"),
        Sku("PLO-ECR", "Piqué polo · ecru", "Shirts", 59.0, "polo_shirt_ecru.webp"),
        Sku("SCF-NVY", "Wool-blend scarf · navy", "Accessories", 45.0, "woven_scarf_navy.webp"),
        Sku("FAB-MER", "Merino-blend fabric", "Material", 0.0, "", "metres", False),
        Sku("TRM-ZIP", "Metal zip, 18 cm", "Material", 0.0, "", "units", False),
    ]


def _stock() -> list[StockRecord]:
    S = StockRecord  # (sku, facility, on_hand, quarantined, daily_demand, safety_stock)
    return [
        # Barcelona DC: out of overshirts and trousers until TR-5301 arrives; scarves quarantined (water damage).
        S("OVS-OLV", "DC-ES-01", 2, 2), S("TRS-STN", "DC-ES-01", 1, 1), S("JKT-CHR", "DC-ES-01", 70), S("KNT-GRY", "DC-ES-01", 1),
        S("PLO-ECR", "DC-ES-01", 30), S("SHT-WHT", "DC-ES-01", 52), S("BAG-CNV", "DC-ES-01", 18), S("BLT-BRN", "DC-ES-01", 40),
        S("SCF-NVY", "DC-ES-01", 6, 6), S("SNK-WHT", "DC-ES-01", 10),
        S("OVS-OLV", "DC-DE-01", 64), S("SNK-WHT", "DC-DE-01", 80), S("TRS-STN", "DC-DE-01", 22), S("KNT-GRY", "DC-DE-01", 25), S("JKT-CHR", "DC-DE-01", 15),
        S("OVS-OLV", "3PL-FR-01", 30), S("PLO-ECR", "3PL-FR-01", 120),
        # stores fed from Barcelona that TR-5301 affects
        S("OVS-OLV", "STORE-ES-01", 8, 0, 5, 4), S("TRS-STN", "STORE-ES-01", 10, 0, 2, 3), S("BLT-BRN", "STORE-ES-01", 18, 0, 1, 2), S("SHT-WHT", "STORE-ES-01", 9, 0, 2, 3),
        S("OVS-OLV", "STORE-FR-01", 8, 0, 4, 3), S("TRS-STN", "STORE-FR-01", 4, 0, 2, 2), S("KNT-GRY", "STORE-FR-01", 6, 0, 1, 2),
        S("TRS-STN", "STORE-IT-01", 6, 0, 3, 3), S("SHT-WHT", "STORE-IT-01", 4, 0, 2, 2),
        # the rest of the European store network
        S("SNK-WHT", "STORE-DE-01", 5, 0, 2, 2), S("OVS-OLV", "STORE-DE-01", 9, 0, 2, 2),
        S("OVS-OLV", "STORE-GB-01", 12, 0, 3, 3), S("JKT-CHR", "STORE-GB-01", 8, 0, 1, 2),
        S("KNT-GRY", "STORE-IE-01", 10, 0, 2, 3), S("SNK-WHT", "STORE-IE-01", 6, 0, 1, 2),
        S("OVS-OLV", "STORE-NO-01", 9, 0, 2, 3), S("JKT-CHR", "STORE-NO-01", 7, 0, 1, 2),
        S("SHT-WHT", "STORE-DK-01", 8, 0, 2, 3), S("KNT-GRY", "STORE-DK-01", 5, 0, 1, 2),
        S("TRS-STN", "STORE-AT-01", 9, 0, 2, 3), S("SHT-WHT", "STORE-AT-01", 7, 0, 1, 2),
        S("SHT-WHT", "STORE-BE-01", 12, 0, 2, 3), S("BLT-BRN", "STORE-BE-01", 9, 0, 1, 2),
        S("OVS-OLV", "STORE-PL-01", 10, 0, 3, 3), S("KNT-GRY", "STORE-PL-01", 8, 0, 2, 2),
        S("JKT-CHR", "STORE-SE-01", 6, 0, 1, 2), S("SNK-WHT", "STORE-SE-01", 7, 0, 1, 2),
    ]


def _transfers() -> list[Transfer]:
    T, L = Transfer, TransferLine
    return [
        T("TR-5301", "Factory → DC", "FAC-PT-01", "DC-ES-01", "Road linehaul", "Atlantic Linehaul", [L("OVS-OLV", 420), L("TRS-STN", 260)],
          "In transit", "2026-10-26T16:00", "2026-10-27T07:00", "2026-10-26T17:12", "", "2026-10-29T07:00", reference="PO-77104"),
        T("TR-5302", "Factory → Port", "FAC-TR-01", "PORT-BCN-01", "Sea freight", "Aegean Container Line", [L("KNT-GRY", 300)],
          "Customs hold", "2026-10-18T06:00", "2026-10-26T15:00", "2026-10-18T07:20", "2026-10-26T14:40", "2026-10-26T15:00",
          exception="Country-of-origin mismatch on commercial invoice", reference="PO-77081"),
        T("TR-5303", "Supplier → Factory", "FAC-IT-01", "FAC-PT-01", "Road", "Tuscany Freight", [L("FAB-MER", 1800)],
          "In transit", "2026-10-25T07:00", "2026-10-27T12:00", "2026-10-25T07:30", "", "2026-10-27T12:00", reference="MAT-3310"),
        T("TR-5304", "Inter-DC", "DC-ES-01", "DC-DE-01", "Road", "Euro Road Freight", [L("JKT-CHR", 40)],
          "Loading", "2026-10-27T11:00", "2026-10-29T03:00", "", "", "2026-10-29T03:00", reference="REB-1120"),
        T("TR-5305", "DC → Store", "DC-ES-01", "STORE-ES-01", "Van", "Threadline fleet", [L("BLT-BRN", 20, 20)],
          "Received", "2026-10-25T06:00", "2026-10-25T10:00", "2026-10-25T06:05", "2026-10-25T10:05", "2026-10-25T10:00", reference="REP-8801"),
        T("TR-5306", "Factory → 3PL", "FAC-PT-01", "3PL-FR-01", "Road", "Atlantic Linehaul", [L("PLO-ECR", 350)],
          "In transit", "2026-10-24T08:00", "2026-10-26T18:00", "2026-10-24T08:00", "", "2026-10-28T06:00", reference="PO-77092"),
        T("TR-5307", "DC → Store", "DC-DE-01", "STORE-DE-01", "Van", "Threadline fleet", [L("SNK-WHT", 24)],
          "Planned", "2026-10-29T06:00", "2026-10-29T10:00", "", "", "2026-10-29T10:00", reference="REP-8807"),
        T("TR-5308", "DC → Store", "DC-ES-01", "STORE-ES-01", "Road", "Threadline fleet", [L("SHT-WHT", 30)],
          "In transit", "2026-10-26T23:00", "2026-10-27T10:15", "2026-10-26T23:30", "", "2026-10-27T10:15", reference="REP-8808"),
        T("TR-5309", "Port → DC", "PORT-BCN-01", "DC-ES-01", "Road", "Euro Road Freight", [L("KNT-GRY", 300)],
          "Planned", "2026-10-27T08:00", "2026-10-27T18:00", "", "", "2026-10-27T18:00", depends_on="TR-5302", reference="PO-77081"),
        T("TR-5310", "Supplier → Factory", "FAC-IT-01", "FAC-TR-01", "Road", "Tuscany Freight", [L("TRM-ZIP", 2400)],
          "Exception", "2026-10-22T07:00", "2026-10-26T17:00", "2026-10-22T07:00", "2026-10-26T16:30", "2026-10-26T17:00",
          exception="Zip pull strength failed incoming QC; lot quarantined", reference="MAT-3318"),
        T("TR-5311", "DC → Store", "DC-ES-01", "STORE-ES-01", "Road", "Threadline fleet", [L("OVS-OLV", 24)],
          "Planned", "2026-10-28T06:00", "2026-10-28T16:00", "", "", "2026-10-28T16:00", depends_on="TR-5301", reference="REP-8811"),
        T("TR-5312", "DC → Store", "DC-ES-01", "STORE-FR-01", "Road", "Threadline fleet", [L("OVS-OLV", 18), L("TRS-STN", 12)],
          "Planned", "2026-10-28T08:00", "2026-10-29T05:00", "", "", "2026-10-29T05:00", depends_on="TR-5301", reference="REP-8812"),
        T("TR-5313", "DC → Store", "DC-ES-01", "STORE-IT-01", "Road", "Threadline fleet", [L("TRS-STN", 16)],
          "Planned", "2026-10-28T09:00", "2026-10-29T03:00", "", "", "2026-10-29T03:00", depends_on="TR-5301", reference="REP-8813"),
        T("TR-5314", "DC → Store", "DC-DE-01", "STORE-AT-01", "Road", "Euro Road Freight", [L("KNT-GRY", 10)],
          "In transit", "2026-10-27T05:00", "2026-10-27T17:00", "2026-10-27T05:10", "", "2026-10-27T17:00", reference="REP-8814"),
    ]


def _order(oid, channel, status, created, promised, ref, name, email, city, country, lat, lon, items, **kw) -> Order:
    return Order(oid, channel, status, created, promised, ref, name, email, city, country, lat, lon, items, **kw)


def _orders() -> list[Order]:
    I = OrderItem
    return [
        _order("OR-20481", "Online", "Delivered", "2026-10-24T10:12", "2026-10-26T20:00", "CU-1101", "Mathilde Laurent", "m***@example.test", "Paris", "FR", 48.8566, 2.3522,
               [I("1", "SHT-WHT", 1, "M", "DC-ES-01", "delivered")], carrier="Colissimo", tracking_code="TLN-FR-20481", shipped_at="2026-10-25T16:40", delivered_at="2026-10-26T13:05",
               last_scan_at="2026-10-26T13:05", last_scan_location="Delivered, Paris"),
        _order("OR-20482", "Online", "Created", "2026-10-26T09:14", "2026-10-28T20:00", "CU-1102", "Lucía Fernández", "l***@example.test", "Madrid", "ES", 40.4168, -3.7038,
               [I("1", "JKT-CHR", 1, "48", "DC-ES-01", "allocated"), I("2", "OVS-OLV", 1, "M", "", "awaiting_inbound", "TR-5301")]),
        _order("OR-20483", "Online", "Shipped", "2026-10-25T14:02", "2026-10-28T20:00", "CU-1103", "Aoife Murphy", "a***@example.test", "Dublin", "IE", 53.3498, -6.2603,
               [I("1", "PLO-ECR", 1, "L", "DC-ES-01", "shipped")], carrier="DHL Express", tracking_code="TLN-IE-20483", shipped_at="2026-10-26T17:30",
               last_scan_at="2026-10-27T07:42", last_scan_location="Dublin delivery hub"),
        _order("OR-20484", "Online", "Created", "2026-10-26T11:20", "2026-10-29T20:00", "CU-1104", "Freja Nielsen", "f***@example.test", "Copenhagen", "DK", 55.6761, 12.5683,
               [I("1", "SHT-WHT", 1, "L", "", "unallocated")], issue="INTEGRATION_REJECTED"),
        _order("OR-20485", "Online", "Shipped", "2026-10-24T18:30", "2026-10-27T18:00", "CU-1105", "Erik Hansen", "e***@example.test", "Oslo", "NO", 59.9139, 10.7522,
               [I("1", "SNK-WHT", 1, "43", "DC-ES-01", "shipped")], carrier="PostNord", tracking_code="TLN-NO-20485", shipped_at="2026-10-25T15:10",
               last_scan_at="2026-10-26T08:02", last_scan_location="Oslo sort centre"),
        _order("OR-20486", "Online", "Delivered", "2026-10-23T09:00", "2026-10-25T20:00", "CU-1106", "Inês Costa", "i***@example.test", "Lisbon", "PT", 38.7223, -9.1393,
               [I("1", "BAG-CNV", 1, "One size", "DC-ES-01", "delivered")], carrier="CTT", tracking_code="TLN-PT-20486", shipped_at="2026-10-24T15:00",
               delivered_at="2026-10-25T11:40", last_scan_at="2026-10-25T11:40", last_scan_location="Delivered, Lisbon"),
        _order("OR-20487", "Online", "Return in transit", "2026-10-20T08:30", "2026-10-22T20:00", "CU-1107", "Anders Lindqvist", "a***@example.test", "Stockholm", "SE", 59.3293, 18.0686,
               [I("1", "TRS-STN", 1, "32", "DC-ES-01", "delivered")], carrier="PostNord", tracking_code="TLN-SE-20487", shipped_at="2026-10-21T14:00",
               delivered_at="2026-10-22T10:30", last_scan_at="2026-10-26T15:30", last_scan_location="Return parcel accepted, Stockholm"),
        _order("OR-20488", "Online", "Created", "2026-10-26T16:45", "2026-10-29T20:00", "CU-1108", "Sofia Rossi", "s***@example.test", "Milan", "IT", 45.4642, 9.1900,
               [I("1", "SCF-NVY", 1, "One size", "", "unallocated")], issue="ALLOCATION_FAILED"),
        _order("OR-20489", "Click & collect", "Packed", "2026-10-26T12:10", "2026-10-27T17:00", "CU-1109", "Diego Martín", "d***@example.test", "Madrid", "ES", 40.4168, -3.7038,
               [I("1", "BLT-BRN", 1, "90", "STORE-ES-01", "allocated")], pickup_store="STORE-ES-01"),
        _order("OR-20490", "Online", "Created", "2026-10-26T13:30", "2026-10-29T20:00", "CU-1110", "Lukas Gruber", "l***@example.test", "Vienna", "AT", 48.2082, 16.3738,
               [I("1", "TRS-STN", 1, "34", "", "awaiting_inbound", "TR-5301"), I("2", "OVS-OLV", 1, "L", "", "awaiting_inbound", "TR-5301")]),
        _order("OR-20491", "Online", "Created", "2026-10-26T15:05", "2026-10-28T20:00", "CU-1111", "Lotte Peeters", "l***@example.test", "Brussels", "BE", 50.8503, 4.3517,
               [I("1", "OVS-OLV", 2, "M", "", "awaiting_inbound", "TR-5301")]),
        _order("OR-20492", "Online", "Created", "2026-10-26T17:40", "2026-10-31T20:00", "CU-1112", "Charlotte Evans", "c***@example.test", "London", "GB", 51.5074, -0.1278,
               [I("1", "TRS-STN", 1, "32", "", "awaiting_inbound", "TR-5301")]),
        _order("OR-20493", "Online", "Created", "2026-10-26T19:12", "2026-10-29T20:00", "CU-1113", "Jonas Weber", "j***@example.test", "Berlin", "DE", 52.5200, 13.4050,
               [I("1", "OVS-OLV", 1, "S", "", "awaiting_inbound", "TR-5301")]),
        _order("OR-20494", "Click & collect", "Created", "2026-10-26T20:02", "2026-10-29T12:00", "CU-1114", "Iris Moreau", "i***@example.test", "Paris", "FR", 48.8566, 2.3522,
               [I("1", "OVS-OLV", 1, "M", "", "awaiting_inbound", "TR-5312")], pickup_store="STORE-FR-01"),
        _order("OR-20495", "Online", "Picked", "2026-10-27T07:15", "2026-10-29T20:00", "CU-1115", "Julien Petit", "j***@example.test", "Paris", "FR", 48.8566, 2.3522,
               [I("1", "KNT-GRY", 1, "M", "DC-ES-01", "allocated"), I("2", "BAG-CNV", 1, "One size", "DC-ES-01", "allocated")]),
        _order("OR-20496", "Online", "Allocated", "2026-10-27T08:05", "2026-10-29T20:00", "CU-1116", "Katarzyna Nowak", "k***@example.test", "Warsaw", "PL", 52.2297, 21.0122,
               [I("1", "SNK-WHT", 1, "42", "DC-DE-01", "allocated"), I("2", "SHT-WHT", 1, "M", "DC-ES-01", "allocated")]),
        _order("OR-20497", "Online", "Created", "2026-10-26T10:40", "2026-10-31T20:00", "CU-1117", "Marta Soler", "m***@example.test", "Valencia", "ES", 39.4699, -0.3763,
               [I("1", "KNT-GRY", 1, "L", "", "awaiting_inbound", "TR-5309")]),
    ]


def _ev(eid, t, etype, rtype, rid, source, detail, payload=None, cust="", ):
    return Event(eid, t, etype, rtype, rid, source, detail, payload or {}, bool(cust), cust)


SEED_EVENTS = [
    _ev("EV-1001", "2026-10-24T10:12", "ORDER_CREATED", "order", "OR-20481", "Order management", "Order placed online.", cust="Order placed"),
    _ev("EV-1002", "2026-10-25T16:40", "ORDER_SHIPPED", "order", "OR-20481", "Warehouse", "Shipped from Barcelona DC with Colissimo.", cust="Shipped"),
    _ev("EV-1003", "2026-10-26T13:05", "ORDER_DELIVERED", "order", "OR-20481", "PostNord", "Delivered.", cust="Delivered"),
    _ev("EV-1010", "2026-10-25T05:00", "TRANSFER_DEPARTED", "transfer", "TR-5305", "Threadline fleet", "Belts left Barcelona DC."),
    _ev("EV-1011", "2026-10-25T10:05", "TRANSFER_RECEIVED", "transfer", "TR-5305", "Store system", "20 units received in full at Madrid Store."),
    _ev("EV-1020", "2026-10-26T17:12", "TRANSFER_DEPARTED", "transfer", "TR-5301", "Porto factory dispatch", "680 units loaded; trailer seal TL-44821."),
    _ev("EV-1021", "2026-10-27T03:40", "TRANSFER_CHECKPOINT", "transfer", "TR-5301", "Atlantic Linehaul", "Passed Zaragoza checkpoint on schedule."),
    _ev("EV-1022", "2026-10-27T08:10", "TRANSFER_ETA_UPDATED", "transfer", "TR-5301", "Atlantic Linehaul",
        "Tractor unit breakdown near Zaragoza. Replacement unit assigned; new ETA Thu 29 Oct 07:00.", {"new_eta": "2026-10-29T07:00"}),
    _ev("EV-1030", "2026-10-18T07:20", "TRANSFER_DEPARTED", "transfer", "TR-5302", "Izmir factory dispatch", "300 knitwear units loaded, container ACLU 448210."),
    _ev("EV-1031", "2026-10-26T14:40", "TRANSFER_ARRIVED", "transfer", "TR-5302", "Port terminal", "Container discharged at Barcelona terminal."),
    _ev("EV-1032", "2026-10-26T15:30", "TRANSFER_CUSTOMS_HOLD", "transfer", "TR-5302", "Customs broker",
        "Held: country-of-origin field on the commercial invoice does not match the packing list.", {"reason": "Country-of-origin mismatch on commercial invoice"}),
    _ev("EV-1040", "2026-10-25T07:30", "TRANSFER_DEPARTED", "transfer", "TR-5303", "Prato mill", "1,800 m merino-blend fabric dispatched."),
    _ev("EV-1050", "2026-10-24T08:00", "TRANSFER_DEPARTED", "transfer", "TR-5306", "Porto factory dispatch", "350 polos dispatched to Lyon."),
    _ev("EV-1051", "2026-10-26T16:20", "TRANSFER_ETA_UPDATED", "transfer", "TR-5306", "Atlantic Linehaul",
        "Road closure in the Pyrenees; rerouted. New ETA Wed 28 Oct 06:00.", {"new_eta": "2026-10-28T06:00"}),
    _ev("EV-1060", "2026-10-26T16:30", "TRANSFER_ARRIVED", "transfer", "TR-5310", "Izmir factory goods-in", "2,400 zips received."),
    _ev("EV-1061", "2026-10-26T18:10", "TRANSFER_QUALITY_HOLD", "transfer", "TR-5310", "Izmir QC",
        "Zip pull-strength test failed on 3 of 8 samples; lot quarantined.", {"reason": "Zip pull strength failed incoming QC; lot quarantined"}),
    _ev("EV-1071", "2026-10-27T05:10", "TRANSFER_DEPARTED", "transfer", "TR-5314", "Threadline fleet", "10 crewnecks left Berlin DC for Vienna."),
    _ev("EV-1070", "2026-10-26T23:30", "TRANSFER_DEPARTED", "transfer", "TR-5308", "Threadline fleet", "30 shirts left Barcelona DC for Madrid."),
    _ev("EV-1100", "2026-10-26T09:14", "ORDER_CREATED", "order", "OR-20482", "Order management", "Order placed online.", cust="Order placed"),
    _ev("EV-1101", "2026-10-26T09:15", "ORDER_ALLOCATED", "order", "OR-20482", "Inventory service", "JKT-CHR allocated at Barcelona DC; OVS-OLV backordered on TR-5301.", cust="We're preparing your order"),
    _ev("EV-1110", "2026-10-25T14:02", "ORDER_CREATED", "order", "OR-20483", "Order management", "Order placed online.", cust="Order placed"),
    _ev("EV-1111", "2026-10-26T17:30", "ORDER_SHIPPED", "order", "OR-20483", "Warehouse", "Shipped with DHL Express.", cust="Shipped"),
    _ev("EV-1112", "2026-10-27T07:42", "CARRIER_SCAN", "order", "OR-20483", "DHL Express", "At Dublin delivery hub.", {"location": "Dublin delivery hub"}, cust="At your local delivery depot"),
    _ev("EV-1120", "2026-10-26T11:20", "ORDER_CREATED", "order", "OR-20484", "Order management", "Order placed online.", cust="Order placed"),
    _ev("EV-1121", "2026-10-26T11:21", "INTEGRATION_REJECTED", "order", "OR-20484", "Carrier booking API",
        "Booking rejected: house number missing in delivery address (field address.houseNumber).", {"field": "address.houseNumber"}),
    _ev("EV-1130", "2026-10-25T15:10", "ORDER_SHIPPED", "order", "OR-20485", "Warehouse", "Shipped with PostNord.", cust="Shipped"),
    _ev("EV-1131", "2026-10-26T08:02", "CARRIER_SCAN", "order", "OR-20485", "PostNord", "Sorted at Oslo sort centre.", {"location": "Oslo sort centre"}, cust="Sorted at a regional centre"),
    _ev("EV-1140", "2026-10-26T15:30", "RETURN_REQUESTED", "order", "OR-20487", "Returns portal", "Return accepted at drop-off point, Stockholm.", cust="Return received at drop-off point"),
    _ev("EV-1150", "2026-10-26T16:46", "ALLOCATION_FAILED", "order", "OR-20488", "Inventory service",
        "No sellable SCF-NVY in the network: 6 units at Barcelona DC are quarantined (water damage)."),
    _ev("EV-1160", "2026-10-27T07:40", "ORDER_PICKED", "order", "OR-20495", "Warehouse", "Both items picked.", cust="We're packing your order"),
]

# Future events released one at a time by "Next event". EV-1022 is replayed on purpose to show duplicate handling.
SCRIPT = [
    _ev("EV-2001", "2026-10-27T10:20", "TRANSFER_ARRIVED", "transfer", "TR-5308", "Threadline fleet", "Truck arrived at Madrid Store."),
    _ev("EV-2002", "2026-10-27T10:40", "TRANSFER_RECEIVED", "transfer", "TR-5308", "Store system", "30 shirts received in full.", {"received": {"SHT-WHT": 30}}),
    _ev("EV-1022", "2026-10-27T08:10", "TRANSFER_ETA_UPDATED", "transfer", "TR-5301", "Atlantic Linehaul",
        "Tractor unit breakdown near Zaragoza. Replacement unit assigned; new ETA Thu 29 Oct 07:00.", {"new_eta": "2026-10-29T07:00"}),
    _ev("EV-2003", "2026-10-27T11:05", "CARRIER_SCAN", "order", "OR-20485", "PostNord", "Out for delivery, Oslo.", {"location": "Oslo delivery van"}, cust="Out for delivery"),
    _ev("EV-2004", "2026-10-27T11:20", "TRANSFER_DEPARTED", "transfer", "TR-5304", "Threadline fleet", "40 jackets left Barcelona DC for Berlin."),
    _ev("EV-2020", "2026-10-27T11:45", "ORDER_PACKED", "order", "OR-20495", "Warehouse", "Packed, label printed.", cust="Packed"),
    _ev("EV-2021", "2026-10-27T12:05", "TRANSFER_ARRIVED", "transfer", "TR-5303", "Tuscany Freight", "Fabric delivered to Porto factory."),
    _ev("EV-2022", "2026-10-27T12:25", "TRANSFER_RECEIVED", "transfer", "TR-5303", "Porto goods-in", "1,800 m fabric received.", {"received": {"FAB-MER": 1800}}),
    _ev("EV-2005", "2026-10-27T12:30", "TRANSFER_CUSTOMS_RELEASED", "transfer", "TR-5302", "Customs broker", "Corrected invoice accepted; container released."),
    _ev("EV-2006", "2026-10-27T12:45", "TRANSFER_RECEIVED", "transfer", "TR-5302", "Port terminal", "300 units available for onward haulage.", {"received": {"KNT-GRY": 300}}),
    _ev("EV-2007", "2026-10-27T13:10", "ORDER_DELIVERED", "order", "OR-20483", "DHL Parcel", "Delivered to customer.", cust="Delivered"),
    _ev("EV-2008", "2026-10-27T14:00", "TRANSFER_DEPARTED", "transfer", "TR-5309", "Euro Road Freight", "Knitwear collected at Barcelona terminal."),
    _ev("EV-2023", "2026-10-27T15:00", "ORDER_SHIPPED", "order", "OR-20495", "Warehouse", "Shipped with Colissimo.", cust="Shipped"),
    _ev("EV-2009", "2026-10-27T15:30", "RETURN_RECEIVED", "order", "OR-20487", "Barcelona DC returns", "Return parcel received; item moved to inspection.", {"facility": "DC-ES-01"}, cust="Return received"),
    _ev("EV-2010", "2026-10-27T16:10", "ORDER_DELIVERED", "order", "OR-20485", "PostNord", "Delivered to customer.", cust="Delivered"),
    _ev("EV-2030", "2026-10-27T17:10", "TRANSFER_ARRIVED", "transfer", "TR-5314", "Euro Road Freight", "Arrived at Vienna Store."),
    _ev("EV-2031", "2026-10-27T17:30", "TRANSFER_RECEIVED", "transfer", "TR-5314", "Store system", "10 crewnecks received in full.", {"received": {"KNT-GRY": 10}}),
    _ev("EV-2024", "2026-10-27T16:40", "ORDER_DELIVERED", "order", "OR-20489", "Madrid Store", "Collected by customer in store.", cust="Collected"),
    _ev("EV-2011", "2026-10-27T21:40", "TRANSFER_ARRIVED", "transfer", "TR-5309", "Euro Road Freight", "Arrived at Barcelona DC."),
    _ev("EV-2012", "2026-10-27T23:30", "TRANSFER_RECEIVED", "transfer", "TR-5309", "Warehouse", "300 knitwear units received.", {"received": {"KNT-GRY": 300}}),
    _ev("EV-2013", "2026-10-28T06:00", "TRANSFER_ARRIVED", "transfer", "TR-5306", "Atlantic Linehaul", "Arrived at Lyon 3PL."),
    _ev("EV-2025", "2026-10-28T07:10", "ORDER_DELIVERED", "order", "OR-20495", "Colissimo", "Delivered to customer.", cust="Delivered"),
    _ev("EV-2026", "2026-10-29T02:40", "TRANSFER_ARRIVED", "transfer", "TR-5304", "Euro Road Freight", "Arrived at Berlin DC."),
    _ev("EV-2027", "2026-10-29T03:20", "TRANSFER_RECEIVED", "transfer", "TR-5304", "Berlin WMS", "40 jackets received.", {"received": {"JKT-CHR": 40}}),
    _ev("EV-2014", "2026-10-28T07:30", "TRANSFER_RECEIVED", "transfer", "TR-5306", "3PL WMS", "350 polos received.", {"received": {"PLO-ECR": 350}}),
    _ev("EV-2028", "2026-10-29T06:05", "TRANSFER_DEPARTED", "transfer", "TR-5307", "Threadline fleet", "Sneakers left Berlin DC for Mitte store."),
    _ev("EV-2015", "2026-10-29T07:20", "TRANSFER_ARRIVED", "transfer", "TR-5301", "Atlantic Linehaul", "Trailer arrived at Barcelona DC."),
    _ev("EV-2016", "2026-10-29T09:10", "TRANSFER_RECEIVED", "transfer", "TR-5301", "Warehouse",
        "Received 400 of 420 overshirts (1 carton short) and 260 trousers.", {"received": {"OVS-OLV": 400, "TRS-STN": 260}}),
]


def build_seed() -> State:
    return State(
        seed_version=SEED_VERSION,
        now=DEMO_START,
        facilities={f.facility_id: f for f in _facilities()},
        skus={s.sku: s for s in _skus()},
        stock=_stock(),
        transfers={t.transfer_id: t for t in _transfers()},
        orders={o.order_id: o for o in _orders()},
        events=[Event(**{**e.__dict__}) for e in SEED_EVENTS],
        processed_event_ids=[e.event_id for e in SEED_EVENTS],
    )
