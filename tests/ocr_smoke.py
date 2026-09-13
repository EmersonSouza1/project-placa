"""Diagnostic contract check; publishes a synthetic snapshot. Restart API after use."""
from datetime import datetime, timedelta, timezone
import os
import unittest

from api_smoke import request


class OcrApiTests(unittest.TestCase):
    def test_health_snapshot_validation_and_ordering(self):
        now = datetime.now(timezone.utc)
        observation = dict(camera_id="test-ocr-camera", plate="ABC1D23", confidence=0.9,
                           detected_at=now.isoformat())
        self.assertEqual(request("/ocr-observations", observation)[0], 204)
        code, health = request("/health")
        self.assertEqual(code, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["last_plate_detection"]["plate"], "ABC1D23")
        self.assertEqual(datetime.fromisoformat(health["last_plate_detection"]["detected_at"]), now)
        older = dict(observation, plate="XYZ1234", detected_at=(now-timedelta(seconds=5)).isoformat())
        self.assertEqual(request("/ocr-observations", older)[0], 204)
        self.assertEqual(request("/health")[1]["last_plate_detection"]["plate"], "ABC1D23")
        for fields in (dict(plate="BRASIL"), dict(plate=None), dict(confidence=0.6),
                       dict(camera_id=""), dict(detected_at=(now+timedelta(days=1)).isoformat())):
            self.assertEqual(request("/ocr-observations", dict(observation, **fields))[0], 400)
        for path in ("/dock-events?dock_id=test-ocr-camera", "/dock-stays?dock_id=test-ocr-camera"):
            self.assertEqual(request(path)[1], [])


if __name__ == "__main__":
    unittest.main()
