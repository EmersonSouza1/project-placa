"""Integration checks against a running API/PostgreSQL. Creates isolated test visits."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = os.environ.get("API_URL", "http://localhost:5080").rstrip("/")


def request(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as result:
            body = result.read()
            return result.status, json.loads(body) if body else None
    except HTTPError as error:
        return error.code, error.read().decode()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.dock = "test-" + str(uuid4())
        self.start = datetime.now(timezone.utc)
        self.entry = dict(event_id=str(uuid4()), visit_id=str(uuid4()), camera_id="test-camera",
                          dock_id=self.dock, stream_id=str(uuid4()), track_id=1, event_type="entered",
                          occurred_at=self.start.isoformat(), plate=None, plate_confidence=None)

    def end(self, **changes):
        return dict(self.entry, **(dict(event_id=str(uuid4()), event_type="exited",
                    occurred_at=(self.start + timedelta(seconds=42)).isoformat()) | changes))

    def stays(self):
        status, rows = request("/dock-stays?dock_id=" + self.dock)
        self.assertEqual(status, 200)
        return rows

    def test_entry_exit_and_duplicate(self):
        self.assertEqual(request("/dock-events", self.entry)[0], 201)
        code, duplicate = request("/dock-events", self.entry)
        self.assertEqual(code, 200)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(request("/dock-events", self.end(plate="ABC1D23", plate_confidence=0.92))[0], 201)
        stay = self.stays()[0]
        self.assertEqual(stay["status"], "completed")
        self.assertEqual(stay["duration_seconds"], 42)
        self.assertEqual(stay["plate"], "ABC1D23")
        self.assertEqual(len(request("/dock-events?dock_id=" + self.dock)[1]), 2)

    def test_out_of_order_projection(self):
        self.assertEqual(request("/dock-events", self.end())[0], 201)
        self.assertEqual(self.stays()[0]["status"], "awaiting_start")
        self.assertEqual(request("/dock-events", self.entry)[0], 201)
        self.assertEqual(self.stays()[0]["duration_seconds"], 42)

    def test_loss_has_no_confirmed_duration(self):
        request("/dock-events", self.entry)
        self.assertEqual(request("/dock-events", self.end(event_type="tracking_lost"))[0], 201)
        self.assertEqual(self.stays()[0]["status"], "interrupted")
        self.assertIsNone(self.stays()[0]["duration_seconds"])

    def test_start_inside_has_no_full_duration(self):
        self.entry["event_type"] = "observed_inside"
        self.assertEqual(request("/dock-events", self.entry)[0], 201)
        self.assertEqual(request("/dock-events", self.end())[0], 201)
        self.assertIsNone(self.stays()[0]["duration_seconds"])

    def test_conflicts_do_not_change_raw_events(self):
        request("/dock-events", self.entry)
        self.assertEqual(request("/dock-events", dict(self.entry, track_id=2))[0], 409)
        self.assertEqual(request("/dock-events", self.end(camera_id="different"))[0], 409)
        self.assertEqual(request("/dock-events", self.end(occurred_at=(self.start-timedelta(seconds=1)).isoformat()))[0], 409)
        self.assertEqual(len(request("/dock-events?dock_id=" + self.dock)[1]), 1)
        self.assertEqual(self.stays()[0]["status"], "open")

    def test_concurrent_duplicate_delivery(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(lambda _: request("/dock-events", self.entry)[0], range(6)))
        self.assertEqual(sorted(statuses), [200, 200, 200, 200, 200, 201])

    def test_validation(self):
        for changes in [dict(plate="BAD", plate_confidence=0.9), dict(plate_confidence=0.9),
                        dict(event_type="unknown"), dict(track_id=-1), dict(camera_id="")]:
            self.assertEqual(request("/dock-events", self.entry | changes)[0], 400)
        self.assertEqual(self.stays(), [])


if __name__ == "__main__":
    unittest.main()
