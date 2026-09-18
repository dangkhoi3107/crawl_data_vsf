"""Offline tests: observed DOM fixture plus explicitly synthetic edge cases."""
import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import crawl
from collectors import booking_flights as bf
from collectors.common import BrowserOptions, Paths, RawCache, StateDB

FIXTURE = Path(__file__).parent / "tests/fixtures/booking-flight-detail.html"


def payload():
    url = bf.search_url("SGN", "HAN", "2026-10-17")
    return {"kind": "detail", "html": FIXTURE.read_text(), "context": bf.context_from_url(url),
            "url": url, "searchUrl": url, "observedAt": "2026-09-18T09:00:00Z",
            "evidenceKey": "detail-fixture", "cardText": "VietJet Aviation Eco",
            "priceBreakdownText": "Total VND1,223,323.00 Includes taxes and fees"}


class BookingFlightsTests(unittest.TestCase):
    def test_months_expand_every_day_and_dedupe(self):
        days = bf.flight_dates("2026-10,2026-11", "2026-10-17", date(2026, 9, 18))
        self.assertEqual(len(days), 61)
        self.assertEqual(days[-1], date(2026, 11, 30))
        self.assertEqual(len(bf.flight_dates("2028-02", today=date(2027, 1, 1))), 29)
        self.assertEqual(len(bf.flight_dates("2026-09", today=date(2026, 9, 18))), 13)
        with self.assertRaises(ValueError):
            bf.flight_dates(dates="2026-09-17", today=date(2026, 9, 18))

    def test_context_changes_queue_identity_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = Paths(Path(tmp)).ensure()
            state = StateDB(paths)
            try:
                opts = bf.Options(BrowserOptions(), routes=[("SGN", "HAN")], dates=[date(2026, 10, 17), date(2026, 10, 18)])
                urls = bf.plan_jobs(state, opts)
                self.assertEqual(len(set(urls)), 2)
                state.mark(bf.SOURCE, urls[0], "done")
                bf.plan_jobs(state, opts)
                self.assertEqual(state.pending(bf.SOURCE, 3), [urls[1]])
                self.assertNotEqual(urls[0], bf.search_url("SGN", "HAN", "2026-10-17", adults=2))
                self.assertTrue(bf.in_scope(urls[0], opts))
                self.assertFalse(bf.in_scope(bf.search_url("HAN", "SGN", "2026-10-17"), opts))
            finally:
                state.close()

    def test_observed_detail_parser_uses_total_not_upsell(self):
        offer = bf.parse_detail(payload())
        self.assertEqual(offer["totalPrice"], 1223323)
        self.assertEqual(offer["segments"][0]["flightNumber"], "VJ138")
        self.assertEqual(offer["departureAt"], "2026-10-17T13:05:00+07:00")
        self.assertEqual(offer["segments"][0]["durationMinutes"], 130)
        self.assertEqual(offer["observedAt"], "2026-09-18T09:00:00Z")
        self.assertTrue(offer["taxesIncluded"])
        self.assertTrue(offer["nonstop"])

    def test_missing_price_and_unknown_currency_fail_closed(self):
        for replacement in ("", "$45.99", "VND0"):
            p = payload()
            p["html"] = p["html"].replace("VND1,223,323.00", replacement)
            with self.assertRaises(ValueError):
                bf.parse_detail(p)

    def test_missing_number_or_wrong_date_is_not_an_offer(self):
        for old, new in (("VJ138", ""), ("Oct 17", "Oct 18"), ("HAN ·", "DAD ·")):
            p = payload()
            p["html"] = p["html"].replace(old, new)
            with self.assertRaises(ValueError):
                bf.parse_detail(p)

    def test_overnight_and_year_boundary_require_explicit_date(self):
        start = bf.timestamp("Thu, Dec 31 · 11:05 PM", date(2026, 12, 31))
        end = bf.timestamp("Fri, Jan 1 · 1:15 AM", start.date())
        self.assertEqual((end - start).total_seconds(), 130 * 60)
        with self.assertRaises(ValueError):
            bf.timestamp("1:15 AM", start.date())

    def test_connection_preserves_itinerary_price(self):
        p = payload()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(p["html"], "lxml")
        leg = soup.find(attrs={"data-testid": "timeline_leg_0"})
        second = copy.copy(leg)
        second["data-testid"] = "timeline_leg_1"
        leg.find(attrs={"data-testid": "timeline_location_airport_arrival"}).string = "DAD · Da Nang"
        second.find(attrs={"data-testid": "timeline_location_airport_departure"}).string = "DAD · Da Nang"
        second.find(attrs={"data-testid": "timeline_location_timestamp_departure"}).string = "Sat, Oct 17 · 5:00 PM"
        second.find(attrs={"data-testid": "timeline_location_timestamp_arrival"}).string = "Sat, Oct 17 · 6:20 PM"
        second.find(attrs={"data-testid": "timeline_leg_info_flight_number_and_class"}).string = "VJ508 · Economy"
        leg.parent.append(second)
        p["html"] = str(soup)
        offer = bf.parse_detail(p)
        self.assertEqual(len(offer["segments"]), 2)
        self.assertFalse(offer["nonstop"])
        self.assertEqual(offer["totalPrice"], 1223323)
        self.assertNotIn("price", offer["segments"][0])

    def test_sanitize_removes_sessions_scripts_and_forms(self):
        clean = bf.sanitize_fragment('<div data-testid="upt_price" onclick="secret">VND100</div><script>secret</script><a href="/?sid=secret">public</a><input value="secret">')
        self.assertNotIn("secret", clean)
        self.assertIn("upt_price", clean)
        self.assertNotIn("sid=", bf.clean_url(payload()["url"] + "&sid=secret&label=tracker"))

    def test_reparse_keeps_observation_time_and_page_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = Paths(Path(tmp)).ensure()
            cache = RawCache(paths, bf.SOURCE)
            p = payload()
            cache.write_json(p["evidenceKey"], p)
            rec = {"recordType": "booking_flight_search", "key": "search:original", "context": p["context"],
                   "crawledAt": p["observedAt"], "offers": [bf.parse_detail(p)]}
            cache.write_json("result-fixture", rec)
            self.assertEqual(bf.reparse(paths)["reparsed"], 1)
            out = paths.interim / "booking_flights.jsonl"
            restored = json.loads(out.read_text())
            self.assertEqual(restored["key"], rec["key"])
            self.assertEqual(restored["offers"][0]["observedAt"], p["observedAt"])
            before = out.read_text()
            p["html"] = "changed DOM"
            cache.write_json(p["evidenceKey"], p)
            self.assertEqual(bf.reparse(paths)["failed"], 1)
            self.assertEqual(out.read_text(), before)

    def test_cli_commands(self):
        parser = crawl.build_parser()
        args = parser.parse_args(["booking-flights", "--routes", "SGN-HAN", "--months", "2026-10,2026-11"])
        self.assertEqual(args.adults, 1)
        self.assertEqual(parser.parse_args(["reparse", "booking-flights"]).source, "booking-flights")

    def test_catalog_preserves_ids_and_links_price_to_booking(self):
        import normalise as n
        offer = bf.parse_detail(payload())
        route = n.make_product(name="old route", taxonomy="flight", destination="Hà Nội", description="old",
                               sourceRef="trip:route:sgn-han", attributes={"level": "route", "originAirports": ["SGN"], "destinationAirports": ["HAN"]})
        flight = n.make_product(name="old flight", taxonomy="flight", destination="Hà Nội", description="old",
                                sourceRef="trip:flight:SGN-HAN:VJ138", attributes={"level": "flight", "flightNumber": "VJ138", "originAirport": "SGN", "destinationAirport": "HAN"})
        rows = [{"key": "search:x", "crawledAt": offer["observedAt"], "offers": [offer]}]
        result = n.merge_booking_flight_products([route, flight], rows, now=datetime(2026, 9, 18, 10, tzinfo=timezone.utc))
        self.assertEqual([x["productId"] for x in result], [route["productId"], flight["productId"]])
        r, f = result
        self.assertEqual(f["attributes"]["parentProductId"], r["productId"])
        self.assertEqual(f["attributes"]["bookingUrl"], offer["bookingUrl"])
        self.assertEqual(f["attributes"]["fieldSources"]["unitPrice"], "booking.com")
        self.assertEqual(f["unitPrice"], 1223323)
        self.assertTrue(f["available"])
        self.assertFalse(r["attributes"]["bookable"])
        self.assertIsNone(f["availableFrom"])
        stale = n.merge_booking_flight_products([], rows, now=datetime(2026, 9, 20, tzinfo=timezone.utc))
        self.assertTrue(all(not x["available"] for x in stale))

    def test_latest_quote_wins_before_minimum_price_and_dates_survive(self):
        import normalise as n
        old = bf.parse_detail(payload())
        new = copy.deepcopy(old)
        new.update(totalPrice=1500000, observedAt="2026-09-18T10:00:00Z", offerId="booking:offer:new")
        tomorrow = copy.deepcopy(old)
        tomorrow["context"]["departureDate"] = "2026-10-18"
        tomorrow["departureAt"] = tomorrow["departureAt"].replace("10-17", "10-18")
        tomorrow["arrivalAt"] = tomorrow["arrivalAt"].replace("10-17", "10-18")
        tomorrow["segments"][0]["departureAt"] = tomorrow["departureAt"]
        tomorrow["segments"][0]["arrivalAt"] = tomorrow["arrivalAt"]
        rows = [{"key": "old", "offers": [old]}, {"key": "new", "offers": [new]}, {"key": "tomorrow", "offers": [tomorrow]}]
        out = n.merge_booking_flight_products([], rows, now=datetime(2026, 9, 18, 11, tzinfo=timezone.utc))
        flight = next(x for x in out if x["attributes"]["level"] == "flight")
        self.assertEqual(flight["unitPrice"], 1500000)
        self.assertEqual(flight["attributes"]["datesSeen"], ["2026-10-17", "2026-10-18"])


if __name__ == "__main__":
    unittest.main()
