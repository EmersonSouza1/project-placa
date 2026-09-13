import json
from threading import Event
import unittest
from unittest.mock import Mock, patch

from dock_vision.ocr_test import Confirmation, best_plate, publish_observation


class OcrTestTests(unittest.TestCase):
    def test_formats_confidence_and_unrelated_text(self):
        results = [{"rec_texts": ["BRASIL", "abc-1234", "XYZ1D23", "ABC1234", "ABC1234"],
                    "rec_scores": [0.99, 0.9, 0.8, float("nan"), 0.6]}]
        self.assertEqual(best_plate(results), ("ABC1234", 0.9))
        self.assertIsNone(best_plate([{"rec_texts": ["BRASIL"], "rec_scores": [0.99]}]))
        self.assertIsNone(best_plate([]))

    def test_confirmation_requires_distinct_recent_frames_same_connection(self):
        gate = Confirmation()
        candidate = ("ABC1234", 0.9)
        self.assertIsNone(gate.update(candidate, 1, 1))
        self.assertIsNone(gate.update(candidate, 1, 1))
        self.assertEqual(gate.update(candidate, 2, 1), candidate)
        self.assertIsNone(gate.update(candidate, 20, 1))
        self.assertIsNone(gate.update(candidate, 21, 2))
        self.assertIsNone(gate.update(None, 22, 2))
        self.assertIsNone(gate.update(candidate, 23, 2))
        self.assertIsNone(gate.update(("XYZ1D23", 0.9), 24, 2))

    def test_payload_uses_frame_timestamp_and_no_visit(self):
        with patch("dock_vision.ocr_test.urlopen") as send:
            publish_observation("http://api/ocr-observations", "camera-01", ("ABC1234", 0.9), 100)
        request = send.call_args.args[0]
        self.assertEqual(json.loads(request.data), dict(camera_id="camera-01", plate="ABC1234",
                         confidence=0.9, detected_at="1970-01-01T00:01:40+00:00"))
        self.assertEqual(request.full_url, "http://api/ocr-observations")
        self.assertEqual(send.call_args.kwargs["timeout"], 5)

    def test_test_mode_bypasses_zone_outbox_and_plate_detector(self):
        from dock_vision import __main__ as worker
        with patch.dict("os.environ", {"SOURCE_MODE": "ocr_test"}, clear=True), \
                patch.object(worker.signal, "signal"), \
                patch.object(worker, "Outbox") as outbox, \
                patch.object(worker, "ZoneProcessor") as zone, \
                patch("dock_vision.ocr_test.run_ocr_test") as run:
            worker.main()
        run.assert_called_once()
        self.assertIsInstance(run.call_args.args[0], Event)
        outbox.assert_not_called()
        zone.assert_not_called()


if __name__ == "__main__":
    unittest.main()
