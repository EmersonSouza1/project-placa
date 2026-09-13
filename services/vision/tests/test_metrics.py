"""Metrics tests use fake clocks/inference and only the standard library."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from dock_vision.metrics import PipelineMetrics
from dock_vision.pipeline import PlateReader


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.log = Mock()
        self.metrics = PipelineMetrics(self.log, "camera-01", "stream-01",
                                       interval_seconds=30, sample_limit=3,
                                       clock=lambda: self.now)

    def payload(self):
        return json.loads(self.log.info.call_args.args[1])

    def test_interval_rates_reset_and_final_empty_report(self):
        self.metrics.frames_received = 6
        self.metrics.frames_processed = 4
        self.metrics.frames_discarded = 2
        self.now = 29
        self.metrics.report()
        self.log.info.assert_not_called()
        self.now = 30
        self.metrics.report()
        summary = self.payload()
        self.assertEqual(summary["frames_received"], 6)
        self.assertEqual(summary["frames_processed"], 4)
        self.assertEqual(summary["frames_discarded"], 2)
        self.assertEqual(summary["received_fps"], 0.2)
        self.assertEqual(summary["processed_fps"], 0.133)
        self.assertFalse(summary["final"])
        self.metrics.report(final=True)
        summary = self.payload()
        self.assertTrue(summary["final"])
        self.assertEqual(summary["frames_received"], 0)
        self.assertEqual(summary["processed_fps"], 0)
        self.assertIsNone(summary["stages"]["ocr"]["p95_ms"])

    def test_mean_uses_all_calls_p95_uses_bounded_recent_samples(self):
        for seconds in (100, 1, 2, 3):
            with self.metrics.measure("vehicle_tracking"):
                self.now += seconds
        self.assertEqual(len(self.metrics.timings["vehicle_tracking"]["samples"]), 3)
        self.metrics.report(final=True)
        stage = self.payload()["stages"]["vehicle_tracking"]
        self.assertEqual(stage, dict(calls=4, errors=0, mean_ms=26500,
                                     p95_ms=3000, sample_count=3))
        self.assertEqual(self.metrics.timings["vehicle_tracking"]["calls"], 0)

    def test_p95_uses_nearest_rank(self):
        metrics = PipelineMetrics(self.log, "camera", "stream",
                                  sample_limit=20, clock=lambda: self.now)
        for seconds in range(1, 21):
            with metrics.measure("ocr"):
                self.now += seconds
        metrics.report(final=True)
        self.assertEqual(self.payload()["stages"]["ocr"]["p95_ms"], 19000)

    def test_failed_call_is_measured_and_exception_propagates(self):
        with self.assertRaisesRegex(RuntimeError, "inference failed"):
            with self.metrics.measure("ocr"):
                self.now += 0.5
                raise RuntimeError("inference failed")
        self.metrics.report(final=True)
        stage = self.payload()["stages"]["ocr"]
        self.assertEqual(stage["calls"], 1)
        self.assertEqual(stage["errors"], 1)
        self.assertEqual(stage["mean_ms"], 500)
        self.assertNotIn("inference failed", self.log.info.call_args.args[1])

    def test_invalid_limits_rejected(self):
        for interval in (0, -1, float("nan"), float("inf")):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                PipelineMetrics(self.log, "camera", "stream", interval_seconds=interval)
        for limit in (0, -1, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                PipelineMetrics(self.log, "camera", "stream", sample_limit=limit)

    def make_reader(self, recognition):
        reader = PlateReader.__new__(PlateReader)
        reader.device = "cpu"
        reader.metrics = self.metrics
        box = SimpleNamespace(xyxy=[Mock(tolist=Mock(return_value=[0, 0, 10, 10]))])

        def detect(*args, **kwargs):
            self.now += 0.1
            return [SimpleNamespace(boxes=[box])]

        reader.detector = Mock(predict=Mock(side_effect=detect))
        reader.reader = Mock(predict=Mock(side_effect=recognition))
        return reader

    def test_plate_reader_measures_lazy_ocr_and_detector_separately(self):
        def recognize(**kwargs):
            self.now += 0.2
            yield {"rec_text": "ABC1234", "rec_score": 0.9}
            self.now += 0.3

        reader = self.make_reader(recognize)
        self.assertEqual(reader.read(FakeImage(), [0, 0, 10, 10]), [("ABC1234", 0.9)])
        self.metrics.report(final=True)
        stages = self.payload()["stages"]
        self.assertEqual(stages["plate_detection"]["mean_ms"], 100)
        self.assertEqual(stages["ocr"]["mean_ms"], 500)
        self.assertEqual(stages["ocr"]["calls"], 1)

    def test_lazy_ocr_failure_and_empty_crop(self):
        def recognize(**kwargs):
            self.now += 0.2
            raise RuntimeError("lazy inference failed")
            yield  # Make this a generator so failure occurs during iteration.

        reader = self.make_reader(recognize)
        empty = FakeImage()
        empty.size = 0
        self.assertEqual(reader.read(empty, [0, 0, 10, 10]), [])
        reader.detector.predict.assert_not_called()
        with self.assertRaises(RuntimeError):
            reader.read(FakeImage(), [0, 0, 10, 10])
        self.metrics.report(final=True)
        self.assertEqual(self.payload()["stages"]["ocr"]["errors"], 1)
        self.assertEqual(self.payload()["stages"]["ocr"]["mean_ms"], 200)


class FakeImage:
    shape = (20, 20, 3)
    size = 1200

    def __getitem__(self, key):
        return self


if __name__ == "__main__":
    unittest.main()
