"""Offline regression checks for overnight supervision; fixtures stay in temporary directories."""
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import crawl
import overnight as night


class OvernightTests(unittest.TestCase):
    def fixture(self, data):
        (data / "interim").mkdir()
        (data / "state").mkdir()
        dest = night.DESTINATIONS[0]
        counts = {"booking_hotels": 30, "agoda_hotels": 20, "trip_attractions": 25,
                  "trip_flights": 1, "vinpearl": 2}
        for src, count in counts.items():
            rows = [{"key": str(i), "plan": {"destination": dest.name},
                     "recordType": "vinpearl_hotel" if i == 0 else "vinpearl_tour"} for i in range(count)]
            (data / "interim" / f"{src}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        with sqlite3.connect(data / "state" / "crawl_state.sqlite") as conn:
            conn.execute("CREATE TABLE items(source, status, attempts)")
            conn.execute("CREATE TABLE discovery(source, key, found)")
            conn.executemany("INSERT INTO discovery VALUES(?,?,?)", [
                ("booking_hotels", f"search:{dest.booking_query}:30:2026-10-15", 30),
                ("agoda_hotels", f"city:{dest.agoda_city}:20", 20),
                ("trip_attractions", f"list:{dest.trip_city}:25", 25),
            ])
        products = [{"productId": str(i), "name": "fixture", "description": "test fixture",
                     "taxonomy": ("hotel", "flight", "attraction", "combo")[i % 4],
                     "destination": dest.name, "attributes": {}} for i in range(20)]
        (data / "products.jsonl").write_text("\n".join(json.dumps(p) for p in products))

    def test_catalog_checks_do_not_equate_exit_zero_with_complete(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(night, "DESTINATIONS", night.DESTINATIONS[:1]), patch.object(night, "TARGET_MIN", 20):
            data = Path(tmp)
            self.fixture(data)
            self.assertTrue(night.inspect(data, "2026-10-15")["checks_passed"])
            (data / "interim" / "trip_flights.jsonl").unlink()
            result = night.inspect(data, "2026-10-15")
            self.assertFalse(result["checks_passed"])
            self.assertTrue(any("trip_flights" in x for x in result["issues"]))

    def test_discovery_without_saved_records_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(night, "DESTINATIONS", night.DESTINATIONS[:1]), patch.object(night, "TARGET_MIN", 20):
            data = Path(tmp)
            self.fixture(data)
            path = data / "interim" / "booking_hotels.jsonl"
            path.write_text(path.read_text().splitlines()[0])
            gaps = night.inspect(data, "2026-10-15")["sources"]["booking_hotels"]["coverage_shortfalls"]
            self.assertIn("đã lưu 1/30", gaps[0])

    def test_exhausted_failures_are_reported_without_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            self.fixture(data)
            with sqlite3.connect(data / "state" / "crawl_state.sqlite") as conn:
                conn.execute("INSERT INTO items VALUES('trip_flights','failed',3)")
            result = night.inspect(data, "2026-10-15")
            self.assertFalse(result["checks_passed"])
            self.assertEqual(result["sources"]["trip_flights"]["retryable"], 0)
            self.assertTrue(any("failed=1" in x for x in result["issues"]))

    def test_all_generated_commands_are_accepted_by_crawler(self):
        for src in night.SOURCES:
            for rediscover in (False, True):
                args = night.source_args(src, Path("/tmp/unused-overnight-fixture"), "2026-10-15", "2026-10-15,2026-09-29", rediscover)
                parsed = crawl.build_parser().parse_args(args[1:])
                self.assertEqual(parsed.cmd, src.replace("_", "-"))

    def test_deadline_does_not_launch_a_child(self):
        with patch.object(night.subprocess, "Popen") as start:
            self.assertEqual(night.run_step(["unused"], time.time() - 1), 124)
            start.assert_not_called()

    def test_timeout_signals_only_own_child_and_preserves_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / "interrupted"
            script = Path(tmp) / "child.py"
            script.write_text("import time\nfrom pathlib import Path\ntry:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    Path(" + repr(str(flag)) + ").write_text('saved')\n")
            self.assertEqual(night.run_step([str(script)], time.time() + 2, minutes=0.01), 124)
            self.assertEqual(flag.read_text(), "saved")

    def test_failure_in_one_source_does_not_skip_other_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            seen = []
            def inspect(*args):
                return {"checks_passed": False, "sources": {s: {"records": 0, "retryable": 0, "coverage_shortfalls": []} for s in night.SOURCES}}
            def step(args, *other):
                if "--data-dir" in args and args[0].endswith("crawl.py"):
                    seen.append(args[3])
                return 1
            with patch.object(night, "inspect", side_effect=inspect), patch.object(night, "report", side_effect=inspect), patch.object(night, "run_step", side_effect=step), patch.object(night.time, "sleep", side_effect=KeyboardInterrupt):
                self.assertEqual(night.main(["--data-dir", str(data), "--checkin", "2026-10-15"]), 130)
            self.assertEqual(seen[:5], [s.replace("_", "-") for s in night.SOURCES])


if __name__ == "__main__":
    unittest.main()
