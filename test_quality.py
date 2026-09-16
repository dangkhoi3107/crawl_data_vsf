"""Offline regressions for source parsing, venue matching and catalog corrections."""
import copy
import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

import normalise as n
from collectors.agoda_hotels import parse_agoda_html
from collectors.venues import Venue, VenueMatcher


class QualityTests(unittest.TestCase):
    def test_agoda_reads_source_description_and_address_without_jsonld(self):
        html = '''<h1>Khách sạn thử nghiệm</h1>
        <span data-element-name="property-short-description">Khách sạn có hồ bơi và Wi-Fi.</span>
        <span data-selenium="hotel-address-map">15 Ng&amp;#244; Quyền, Hà Nội</span>
        <span data-element-name="cheapest-room-price-property-nav-bar" data-element-cheapest-room-price="1200000">1.200.000 ₫</span>'''
        p = parse_agoda_html(html, "https://www.agoda.com/vi-vn/test/hotel/hanoi-vn.html",
                             {"fetchedAt": "2026-09-15T00:00:00Z"})
        self.assertEqual(p["description"], "Khách sạn có hồ bơi và Wi-Fi.")
        self.assertIn("Ngô Quyền", p["address"]["street"])
        self.assertEqual(p["minPrice"], 1200000)
        self.assertEqual(p["crawledAt"], "2026-09-15T00:00:00Z")
        self.assertIsNone(p["latitude"])

    def test_agoda_keeps_missing_price_and_description_when_source_has_neither(self):
        p = parse_agoda_html("<h1>Test Hotel</h1>", "https://www.agoda.com/vi-vn/test/hotel/hanoi-vn.html")
        self.assertFalse(p["description"])
        self.assertIsNone(p["minPrice"])

    def test_booking_rooms_have_language_for_their_actual_description(self):
        prop, rooms = n.booking_hotel({"hotelId": 1, "name": "Khách sạn thử nghiệm", "descriptionShort": "Khách sạn nằm ở trung tâm thành phố.",
                                      "rooms": [{"roomId": "a", "name": "Phòng giường đôi hướng biển", "maxOccupancy": 2}]}, {})
        self.assertEqual(prop["attributes"]["descriptionLang"], "vi")
        self.assertEqual(rooms[0]["attributes"]["descriptionLang"], "vi")

    def test_audience_city_does_not_prevent_matching_actual_ticket_venue(self):
        venue = Venue("nam-hoi-an", "VinWonders Nam Hội An", "Hội An", aliases=["vinwonders nam hoi an"],
                      latitude=15.78878, longitude=108.410788, status="auto", source="osm:W1")
        name = "[Ưu Đãi Người Đà Nẵng] [Mua 2 Tặng 1] Vé vào cửa tiêu chuẩn"
        p = {"name": name, "destination": "Đà Nẵng", "attributes": {},
             "_meta": {"imageUrlSlug": "vinwonders-nam-hoi-an-ve-vao-cua"}}
        n.assign_venue_locations([p], [venue])
        self.assertEqual(p["destination"], "Hội An")
        self.assertEqual(p["attributes"]["latitude"], 15.78878)
        # Listing-only records may have an image URL but no imageUrlSlug field.
        listing = n.vinpearl_tour_product({"name": name, "tourCode": "TEST", "destinationName": "Quảng Nam",
                                          "images": ["https://example.org/tours/id_vinwonders-nam-hoi-an-ve-vao-cua.jpg"]}, date(2026, 9, 16))
        n.assign_venue_locations([listing], [venue])
        self.assertEqual(listing["attributes"]["venue"], venue.name)
        self.assertEqual(listing["attributes"]["latitude"], 15.78878)
        # A real venue name in brackets must still protect against a wrong island/city.
        wrong = Venue("grand-world-hanoi", "Mega Grand World Hà Nội", "Hà Nội", aliases=["grand world"])
        self.assertIsNone(VenueMatcher([wrong]).match(name="[Grand World Phú Quốc] Vé trải nghiệm")[0])

    def test_nearby_apartments_with_different_names_are_kept_separate(self):
        def hotel(pid, name, src):
            return {"productId": pid, "name": name, "destination": "Quy Nhơn", "attributes": {"latitude": 13.756, "longitude": 109.216},
                    "_meta": {"src": src}}
        a = hotel("a", "FLC Sea Tower Quy Nhon Apartment", "booking")
        b = hotel("b", "FLC Sea Tower - The Beach Quy Nhon", "agoda")
        self.assertEqual(len(n.cluster_hotels([a, b], 88)[0]), 2)
        b["name"] = a["name"]
        self.assertEqual(len(n.cluster_hotels([a, b], 88)[0]), 1)

    def test_destination_corrections_are_scoped_and_preserve_source_fields(self):
        p = {"sourceRef": "trip:attraction:1", "destination": "Đà Lạt", "name": "Mũi Kê Gà", "description": "Nội dung nguồn",
             "unitPrice": None, "attributes": {"latitude": 10.695261, "longitude": 107.99156}}
        untouched = copy.deepcopy(p)
        untouched["sourceRef"] = "trip:attraction:2"
        before = copy.deepcopy(untouched)
        self.assertEqual(n.apply_destination_overrides([p, untouched], {p["sourceRef"]: ("Phan Thiết", "source evidence")}), 1)
        self.assertEqual(untouched, before)
        self.assertEqual(p["attributes"]["originalDestination"], "Đà Lạt")
        self.assertEqual(p["description"], before["description"])
        self.assertIsNone(p["unitPrice"])
        self.assertEqual(p["attributes"]["latitude"], before["attributes"]["latitude"])

    def test_quality_report_is_read_only_and_updates_missing_fields(self):
        p = {"name": "Test", "taxonomy": "attraction", "destination": "Hà Nội", "sourceRef": "test:1", "unitPrice": None,
             "description": None, "attributes": {}}
        before = copy.deepcopy(p)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            n.write_quality_review([p], path)
            with path.open(encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertIn("thiếu giá", rows[0]["issues"])
            self.assertIn("thiếu mô tả", rows[0]["issues"])
            self.assertEqual(p, before)


if __name__ == "__main__":
    unittest.main()
