"""Adapter tests use only the standard library, never a camera or model."""
from contextlib import ExitStack
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from dock_vision.domain import ZoneProcessor
from dock_vision.pipeline import run_video, validate_source


SOURCE = "rtsp://test-user:test-secret@camera.local:554/cam/realmonitor?channel=1&subtype=1"
POLYGON = [[0.3, 0.3], [0.8, 0.3], [0.8, 0.9], [0.3, 0.9]]


def frame(position="inside"):
    return SimpleNamespace(shape=(100, 200, 3), size=60000, position=position)


class Boxes(list):
    @property
    def id(self):
        return [1] if self else None


def tracked(image, **kwargs):
    boxes = Boxes()
    if image.position is not None:
        # Non-square image detects accidental width/height swaps in normalization.
        bounds = [80, 10, 120, 60] if image.position == "inside" else [10, 0, 30, 10]
        boxes.append(SimpleNamespace(id=Mock(item=Mock(return_value=1)),
                                     xyxy=[Mock(tolist=Mock(return_value=bounds))]))
    return [SimpleNamespace(boxes=boxes)]


class Capture:
    def __init__(self, images=(), opened=True, fps=1, end=None):
        self.images = iter(images)
        self.opened, self.fps, self.end = opened, fps, end
        self.release = Mock()

    def isOpened(self):
        return self.opened

    def get(self, _):
        return self.fps

    def read(self):
        try:
            image = next(self.images)
        except StopIteration:
            if self.end:
                self.end()
            return False, None
        if isinstance(image, Exception):
            raise image
        return True, image


class SourceTests(unittest.TestCase):
    def test_authenticated_urls_preserved(self):
        for source in (SOURCE, SOURCE.replace("rtsp:", "rtsps:"),
                       "rtsp://camera.local/stream", "rtsp://[::1]:554/stream"):
            with self.subTest(source=source):
                self.assertTrue(validate_source(source))

    def test_invalid_source_precedes_inference_imports_and_hides_secrets(self):
        sources = ("", "missing.mp4", "rtsp:///stream", "rtsp://test-user:test-secret@:554/x",
                   "rtsp://camera:abc/x", "rtsp://camera:65536/x", "rtsp://camera:0/x",
                   "rtsp://[invalid/x", "rtsp://camera name/x", r"rtsp\://camera/x")
        for source in sources:
            with self.subTest(source=source), patch.dict(os.environ, VIDEO_SOURCE=source), \
                    patch.dict(sys.modules, {"cv2": None, "ultralytics": None}):
                with self.assertRaises(ValueError) as error:
                    run_video(None, None, Event())
                self.assertNotIn("test-secret", str(error.exception))
                self.assertNotIn("test-user", str(error.exception))

    def test_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4"
            path.touch()
            self.assertFalse(validate_source(str(path)))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.zone = ZoneProcessor("camera-01", "dock-01", POLYGON)
        self.events = []
        self.stop = Event()
        self.wait = self.stack.enter_context(patch.object(self.stop, "wait", side_effect=self.finish_wait))
        self.clock = SimpleNamespace(now=100.0)
        self.stack.enter_context(patch("dock_vision.pipeline.time", SimpleNamespace(time=lambda: self.clock.now)))
        self.cv = SimpleNamespace(CAP_FFMPEG=1, CAP_PROP_OPEN_TIMEOUT_MSEC=2,
                                  CAP_PROP_READ_TIMEOUT_MSEC=3, CAP_PROP_FPS=4,
                                  error=type("CaptureError", (Exception,), {}), VideoCapture=Mock())
        self.models = []

        def new_model(_):
            model = Mock(track=Mock(side_effect=tracked))
            self.models.append(model)
            return model

        self.yolo = Mock(side_effect=new_model)
        self.stack.enter_context(patch.dict(sys.modules, {"cv2": self.cv,
                                 "ultralytics": SimpleNamespace(YOLO=self.yolo)}))
        self.stack.enter_context(patch.dict(os.environ, {"VIDEO_SOURCE": SOURCE,
                                                       "OCR_ENABLED": "false"}, clear=True))
        self.reader = self.stack.enter_context(patch("dock_vision.pipeline.PlateReader"))

    def finish_wait(self, seconds):
        self.stop.set()
        return True

    def run_capture(self, captures, source=SOURCE):
        self.cv.VideoCapture.side_effect = captures
        with patch.dict(os.environ, VIDEO_SOURCE=source), self.assertLogs("dock_vision.pipeline", "INFO") as logs:
            run_video(self.zone, self.events.append, self.stop)
        for secret in (SOURCE, "test-user", "test-secret"):
            self.assertNotIn(secret, "\n".join(logs.output))
        return logs.output

    def test_open_failure_retries_and_stop_prevents_new_attempt(self):
        capture = Capture(opened=False)
        logs = self.run_capture([capture])
        self.assertIn("Camera unavailable camera_id=camera-01", logs[0])
        self.assertEqual(self.events, [])
        self.assertEqual(self.cv.VideoCapture.call_count, 1)
        self.cv.VideoCapture.assert_called_with(SOURCE, 1, [2, 5000, 3, 5000])
        capture.release.assert_called_once()
        self.wait.assert_called_once_with(3)

    def test_native_open_error_does_not_expose_url(self):
        logs = self.run_capture([self.cv.error(SOURCE)])
        self.assertIn("Camera unavailable", logs[0])
        self.assertEqual(self.events, [])

    def test_invalid_frames_never_reach_inference(self):
        for invalid in (None, SimpleNamespace(size=0), self.cv.error(SOURCE)):
            with self.subTest(invalid=type(invalid).__name__):
                self.stop.clear()
                capture = Capture([invalid])
                logs = self.run_capture([capture])
                self.assertFalse(any("First frame" in log for log in logs))
                self.models[-1].track.assert_not_called()
                capture.release.assert_called_once()
                self.assertEqual(self.events, [])

    def test_file_entry_exit_uses_media_time_and_no_replay(self):
        # At 2 FPS each confirmation needs three consecutive frames.
        capture = Capture([frame(p) for p in ["outside"] * 3 + ["inside"] * 3 + ["outside"] * 3], fps=2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4"
            path.touch()
            logs = self.run_capture([capture], str(path))
        self.assertEqual([e["event_type"] for e in self.events], ["entered", "exited"])
        entry, exit_event = self.events
        self.assertEqual(entry["visit_id"], exit_event["visit_id"])
        self.assertNotEqual(entry["event_id"], exit_event["event_id"])
        self.assertIsNone(entry["plate"])
        self.assertEqual(datetime.fromisoformat(exit_event["occurred_at"]).timestamp() -
                         datetime.fromisoformat(entry["occurred_at"]).timestamp(), 1.5)
        self.assertEqual(sum("First frame" in log for log in logs), 1)
        self.assertIn("width=200 height=100", logs[0])
        self.assertEqual(self.cv.VideoCapture.call_count, 1)
        self.reader.assert_not_called()
        self.wait.assert_not_called()
        capture.release.assert_called_once()

    def timed_capture(self, positions, **kwargs):
        capture = Capture([frame(p) for p in positions], **kwargs)
        read = capture.read

        def next_frame():
            self.clock.now += 1
            return read()

        capture.read = next_frame
        return capture

    def test_reconnect_reused_track_has_new_visit_and_same_stream(self):
        first = self.timed_capture(["inside", "inside"])
        second = self.timed_capture(["inside", "inside"])
        self.wait.side_effect = [False, True]
        logs = self.run_capture([first, second])
        self.assertEqual([e["event_type"] for e in self.events],
                         ["observed_inside", "tracking_lost", "observed_inside", "tracking_lost"])
        self.assertEqual(self.events[0]["visit_id"], self.events[1]["visit_id"])
        self.assertEqual(self.events[2]["visit_id"], self.events[3]["visit_id"])
        self.assertNotEqual(self.events[0]["visit_id"], self.events[2]["visit_id"])
        self.assertEqual(len({e["stream_id"] for e in self.events}), 1)
        self.assertEqual(len({e["track_id"] for e in self.events}), 1)
        self.assertEqual(len(self.models), 2)
        self.assertEqual(sum("First frame" in log for log in logs), 2)
        self.assertEqual(self.zone.tracks, {})
        first.release.assert_called_once()
        second.release.assert_called_once()

    def test_missing_detections_interrupt_once(self):
        self.run_capture([self.timed_capture(["inside", "inside"] + [None] * 6)])
        self.assertEqual([e["event_type"] for e in self.events], ["observed_inside", "tracking_lost"])

    def test_stop_during_capture_does_not_reconnect(self):
        capture = self.timed_capture(["inside", "inside"], end=self.stop.set)
        self.run_capture([capture])
        self.assertEqual([e["event_type"] for e in self.events], ["observed_inside", "tracking_lost"])
        self.wait.assert_not_called()
        self.assertEqual(len(self.models), 1)
        capture.release.assert_called_once()

    def test_ocr_enriches_later_event(self):
        self.reader.return_value.read.return_value = [("ABC1234", 0.9)]
        with patch.dict(os.environ, OCR_ENABLED="true"):
            self.run_capture([self.timed_capture(["outside"] * 2 + ["inside"] * 8 + ["outside"] * 2)])
        entry, exit_event = self.events
        self.assertIsNone(entry["plate"])
        self.assertEqual(exit_event["plate"], "ABC1234")
        self.assertEqual(self.reader.return_value.read.call_count, 2)

    def test_ocr_failure_keeps_tracking(self):
        self.reader.return_value.read.side_effect = RuntimeError("OCR failed")
        with patch.dict(os.environ, OCR_ENABLED="true"):
            self.run_capture([self.timed_capture(["outside"] * 2 + ["inside"] * 4 + ["outside"] * 2)])
        self.assertEqual([e["event_type"] for e in self.events], ["entered", "exited"])
        self.assertIsNone(self.events[-1]["plate"])

    def test_file_fps_fallback(self):
        capture = Capture([frame()] * 26, fps=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4"
            path.touch()
            self.run_capture([capture], str(path))
        self.assertEqual([e["event_type"] for e in self.events], ["observed_inside", "tracking_lost"])
        self.assertEqual(datetime.fromisoformat(self.events[0]["occurred_at"]).timestamp(), 101)


class MainTests(unittest.TestCase):
    def test_default_simulation_and_file_completion_keep_delivery_active(self):
        from dock_vision import __main__ as worker

        for mode in (None, "video"):
            with self.subTest(mode=mode), ExitStack() as stack:
                env = {} if mode is None else {"SOURCE_MODE": mode}
                stack.enter_context(patch.dict(os.environ, env, clear=True))
                stack.enter_context(patch.dict(sys.modules, {"cv2": None, "ultralytics": None, "paddleocr": None}))
                stack.enter_context(patch.object(worker.signal, "signal"))
                stop = Mock()
                stop.wait.side_effect = [False, True]
                stack.enter_context(patch.object(worker.threading, "Event", return_value=stop))
                stack.enter_context(patch.object(worker.Path, "read_text", return_value='{"polygon": ' + str(POLYGON) + '}'))
                outbox = stack.enter_context(patch.object(worker, "Outbox")).return_value
                simulation = stack.enter_context(patch.object(worker, "run_simulation"))
                video = stack.enter_context(patch("dock_vision.pipeline.run_video"))
                worker.main()
                selected, other = (simulation, video) if mode is None else (video, simulation)
                selected.assert_called_once()
                self.assertEqual(selected.call_args.args[1], outbox.enqueue)
                other.assert_not_called()
                outbox.start.assert_called_once()
                outbox.close.assert_called_once()
                self.assertEqual(stop.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
