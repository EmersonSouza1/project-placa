"""Bounded capture handoff; only the producer touches OpenCV reads/release."""
from collections import deque
from dataclasses import dataclass
from threading import Condition, Event, Thread
from time import monotonic, time

from .sampling import FileTimeline, FrameSampler


def queue_capacity(value):
    try:
        capacity = int(value)
    except (TypeError, ValueError):
        raise ValueError("FRAME_QUEUE_SIZE must be a positive integer") from None
    if str(capacity) != str(value).strip() or capacity <= 0:
        raise ValueError("FRAME_QUEUE_SIZE must be a positive integer")
    return capacity


@dataclass(frozen=True)
class CapturedFrame:
    image: object
    timestamp: float
    session: int


class StreamReader:
    """One producer per connection; file queues block, live queues keep recent frames."""

    def __init__(self, capture, cv, live, stop, capacity, process_fps, session,
                 logger, camera_id, wall_clock=time, sample_clock=monotonic):
        self.capture, self.cv, self.live, self.stop = capture, cv, live, stop
        self.capacity = queue_capacity(capacity)
        self.sampler = FrameSampler(process_fps)
        self.session, self.logger, self.camera_id = session, logger, camera_id
        self.wall_clock, self.sample_clock = wall_clock, sample_clock
        self.cancel = Event()
        self.condition = Condition()
        self.queue = deque()
        self.finished = False
        self.failed = False
        self.received = self.discarded = self.queue_discarded = self.peak = 0
        self.last_timestamp = wall_clock()
        self.thread = Thread(target=self._run, name="video-capture", daemon=True)

    def start(self):
        self.thread.start()

    def _stopped(self):
        return self.cancel.is_set() or self.stop.is_set()

    def _frames(self):
        timeline = None if self.live else FileTimeline(self.capture.get(self.cv.CAP_PROP_FPS))
        started_at = self.wall_clock()
        first = True
        while not self._stopped():
            try:
                ok, frame = self.capture.read()
            except self.cv.error:
                ok, frame = False, None
            if ok:
                with self.condition:
                    self.received += 1
            if self._stopped() or not ok or frame is None or not frame.size:
                if ok:
                    with self.condition:
                        self.discarded += 1
                return
            height, width = frame.shape[:2]
            if not height or not width:
                with self.condition:
                    self.discarded += 1
                return
            if first:
                self.logger.info("First frame received camera_id=%s width=%s height=%s",
                                 self.camera_id, width, height)
                first = False
            if self.live:
                timestamp = self.wall_clock()
                sample_time = self.sample_clock()
            else:
                try:
                    position_ms = self.capture.get(self.cv.CAP_PROP_POS_MSEC)
                except self.cv.error:
                    position_ms = float("nan")
                sample_time = timeline.advance(position_ms)
                timestamp = started_at + sample_time
            self.last_timestamp = timestamp
            if not self.sampler.accept(sample_time):
                with self.condition:
                    self.discarded += 1
                continue
            yield CapturedFrame(frame, timestamp, self.session)

    def _drop(self, count):
        self.discarded += count
        self.queue_discarded += count

    def _put(self, packet):
        with self.condition:
            while not self.live and len(self.queue) >= self.capacity and not self._stopped():
                self.condition.wait(0.1)
            if self._stopped():
                self._drop(1)
                return False
            if len(self.queue) >= self.capacity:
                self.queue.popleft()
                self._drop(1)
            self.queue.append(packet)
            self.peak = max(self.peak, len(self.queue))
            self.condition.notify_all()
            return True

    def _run(self):
        try:
            for packet in self._frames():
                if not self._put(packet):
                    break
        except Exception:
            # Native/library exception text can contain authenticated source URLs.
            self.failed = True
        finally:
            try:
                self.capture.release()
            except Exception:
                self.failed = True
            with self.condition:
                self.finished = True
                self.condition.notify_all()

    def get(self, timeout=0.2):
        with self.condition:
            self.condition.wait_for(
                lambda: self.queue or self.finished or self._stopped(), timeout)
            if self._stopped() or not self.queue:
                return None
            if self.live:
                self._drop(len(self.queue) - 1)
                packet = self.queue.pop()
                self.queue.clear()
            else:
                packet = self.queue.popleft()
            self.condition.notify_all()
            return packet

    def snapshot(self):
        """Drain counters atomically; the inference thread owns PipelineMetrics."""
        with self.condition:
            result = dict(received=self.received, discarded=self.discarded,
                          queue_discarded=self.queue_discarded, size=len(self.queue),
                          peak=self.peak, capacity=self.capacity)
            self.received = self.discarded = self.queue_discarded = 0
            self.peak = len(self.queue)
            return result

    def close(self, timeout=6):
        self.cancel.set()
        with self.condition:
            self._drop(len(self.queue))
            self.queue.clear()
            self.condition.notify_all()
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            self.stop.set()
            raise RuntimeError("Capture worker did not stop within its timeout")
