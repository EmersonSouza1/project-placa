"""Real-thread capture tests use events, not timing-dependent sleeps."""
import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from dock_vision.stream_reader import CapturedFrame, StreamReader, queue_capacity


class StreamReaderTests(unittest.TestCase):
    def make_stream(self, images=(), live=True, capacity=2, stop=None):
        self.stop = stop or Event()
        self.cv = SimpleNamespace(CAP_PROP_FPS=4, CAP_PROP_POS_MSEC=5,
                                 error=type("CaptureError", (Exception,), {}))
        self.now = 100.0
        iterator = iter(images)

        def read():
            self.now += 1
            try:
                return True, next(iterator)
            except StopIteration:
                return False, None

        self.capture = Mock(read=Mock(side_effect=read), get=Mock(return_value=0))
        stream = StreamReader(self.capture, self.cv, live, self.stop, capacity, 3,
                              7, Mock(), "camera", wall_clock=lambda: self.now,
                              sample_clock=lambda: self.now)
        return stream

    def image(self, identifier):
        return SimpleNamespace(size=100, shape=(10, 10, 3), identifier=identifier)

    def await_finished(self, stream):
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(lambda: stream.finished, timeout=2))

    def test_overload_is_bounded_and_latest_retains_metadata(self):
        stream = self.make_stream([self.image(i) for i in range(100)], capacity=3)
        stream.start()
        try:
            self.await_finished(stream)
            packet = stream.get()
            self.assertEqual(packet.image.identifier, 99)
            self.assertEqual(packet.timestamp, 200)
            self.assertEqual(packet.session, 7)
            snapshot = stream.snapshot()
            self.assertEqual(snapshot["received"], 100)
            self.assertEqual(snapshot["discarded"], 99)
            self.assertEqual(snapshot["queue_discarded"], 99)
            self.assertEqual(snapshot["peak"], 3)
            self.assertEqual(snapshot["size"], 0)
            self.assertEqual(stream.snapshot()["received"], 0)
        finally:
            stream.close()
        self.capture.release.assert_called_once()

    def test_close_full_file_queue_unblocks_producer(self):
        stream = self.make_stream([self.image(i) for i in range(20)], live=False, capacity=1)
        # Use advancing media time to make every frame eligible.
        self.capture.get.side_effect = lambda prop: 1 if prop == 4 else self.now * 1000
        waiting = Event()
        original_put = stream._put

        def put(packet):
            if packet.image.identifier == 1:
                waiting.set()
            return original_put(packet)

        stream._put = put
        stream.start()
        try:
            self.assertTrue(waiting.wait(2))
        finally:
            stream.close()
        self.assertFalse(stream.thread.is_alive())
        snapshot = stream.snapshot()
        self.assertEqual(snapshot["peak"], 1)
        self.assertEqual(snapshot["received"], snapshot["discarded"])
        self.capture.release.assert_called_once()

    def test_file_queue_keeps_order_without_dropping(self):
        stream = self.make_stream([self.image(i) for i in range(12)], live=False, capacity=2)
        self.capture.get.side_effect = lambda prop: 1 if prop == 4 else self.now * 1000
        stream.start()
        result = []
        try:
            while True:
                packet = stream.get(timeout=2)
                if packet is None:
                    self.assertTrue(stream.finished)
                    break
                result.append(packet.image.identifier)
        finally:
            stream.close()
        self.assertEqual(result, list(range(12)))
        self.assertEqual(stream.snapshot()["discarded"], 0)

    def test_stop_while_waiting_for_file_space_releases_capture(self):
        stream = self.make_stream([self.image(i) for i in range(10)], live=False, capacity=1)
        self.capture.get.side_effect = lambda prop: 1 if prop == 4 else self.now * 1000
        queued = Event()
        original_put = stream._put

        def put(packet):
            if packet.image.identifier == 1:
                queued.set()
            return original_put(packet)

        stream._put = put
        stream.start()
        try:
            self.assertTrue(queued.wait(2))
            self.stop.set()
            self.await_finished(stream)
        finally:
            stream.close()
        self.assertFalse(stream.thread.is_alive())
        self.capture.release.assert_called_once()

    def test_close_during_read_discards_returned_frame(self):
        stream = self.make_stream()
        reading, finish_read = Event(), Event()

        def read():
            reading.set()
            if not finish_read.wait(2):
                raise RuntimeError("Test read was not released")
            return True, self.image(1)

        self.capture.read.side_effect = read
        stream.start()
        try:
            self.assertTrue(reading.wait(2))
            stream.cancel.set()
            finish_read.set()
        finally:
            finish_read.set()
            stream.close()
        snapshot = stream.snapshot()
        self.assertEqual(snapshot["received"], 1)
        self.assertEqual(snapshot["discarded"], 1)
        self.assertIsNone(stream.get())
        self.capture.release.assert_called_once()

    def test_failure_is_sanitized_and_releases_capture(self):
        stream = self.make_stream()
        self.capture.read.side_effect = RuntimeError("rtsp://private:secret@camera")
        stream.start()
        try:
            self.await_finished(stream)
            self.assertTrue(stream.failed)
            self.assertIsNone(stream.get())
        finally:
            stream.close()
        stream.logger.exception.assert_not_called()
        self.capture.release.assert_called_once()

    def test_native_read_error_closes_connection_without_fatal_error(self):
        stream = self.make_stream()
        self.capture.read.side_effect = self.cv.error("rtsp://private:secret@camera")
        stream.start()
        try:
            self.await_finished(stream)
            self.assertFalse(stream.failed)
            self.assertIsNone(stream.get())
        finally:
            stream.close()
        self.capture.release.assert_called_once()

    def test_close_timeout_stops_pipeline_and_does_not_release_from_consumer(self):
        stream = self.make_stream()
        stream.thread = Mock(is_alive=Mock(return_value=True))
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            stream.close(timeout=0.01)
        self.assertTrue(self.stop.is_set())
        self.capture.release.assert_not_called()
        stream.thread.join.assert_called_once_with(timeout=0.01)

    def test_capacity_validation(self):
        self.assertEqual(queue_capacity("5"), 5)
        for value in ("0", "-1", "1.5", "nan", "bad", ""):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "FRAME_QUEUE_SIZE"):
                queue_capacity(value)

    def test_connections_do_not_share_queue(self):
        first = self.make_stream([self.image(1)])
        first.start()
        self.await_finished(first)
        first.close()
        second = self.make_stream([self.image(2)])
        second.session = 8
        second.start()
        try:
            self.await_finished(second)
            self.assertIsNone(first.get())
            self.assertEqual(second.get().session, 8)
        finally:
            second.close()


if __name__ == "__main__":
    unittest.main()
