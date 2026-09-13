"""Bounded, local video metrics using only the standard library."""
from collections import deque
from contextlib import contextmanager
import json
import math
from time import perf_counter


class PipelineMetrics:
    """Single-threaded interval counters; timings include failed calls."""

    STAGES = ("vehicle_tracking", "plate_detection", "ocr")

    def __init__(self, logger, camera_id, stream_id, interval_seconds=30,
                 sample_limit=512, clock=perf_counter):
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("Metrics interval must be finite and positive")
        if not isinstance(sample_limit, int) or sample_limit < 1:
            raise ValueError("Metrics sample limit must be a positive integer")
        self.logger = logger
        self.camera_id, self.stream_id = camera_id, stream_id
        self.interval_seconds, self.sample_limit = interval_seconds, sample_limit
        self.clock = clock
        self.started_at = clock()
        self._reset()

    def _reset(self):
        self.frames_received = self.frames_processed = self.frames_discarded = 0
        self.timings = {stage: dict(calls=0, errors=0, total_ms=0.0,
                                  samples=deque(maxlen=self.sample_limit))
                        for stage in self.STAGES}

    @contextmanager
    def measure(self, stage):
        timing = self.timings[stage]
        started = self.clock()
        try:
            yield
        except BaseException:
            timing["errors"] += 1
            raise
        finally:
            elapsed_ms = max(0.0, self.clock() - started) * 1000
            timing["calls"] += 1
            timing["total_ms"] += elapsed_ms
            timing["samples"].append(elapsed_ms)

    def report(self, final=False):
        now = self.clock()
        elapsed = max(0.0, now - self.started_at)
        if not final and elapsed < self.interval_seconds:
            return
        stages = {}
        for stage, timing in self.timings.items():
            samples = sorted(timing["samples"])
            stages[stage] = dict(
                calls=timing["calls"], errors=timing["errors"],
                mean_ms=round(timing["total_ms"] / timing["calls"], 3) if timing["calls"] else None,
                p95_ms=round(samples[math.ceil(0.95 * len(samples)) - 1], 3) if samples else None,
                sample_count=len(samples))
        payload = dict(event="pipeline_metrics", camera_id=self.camera_id,
                       stream_id=self.stream_id, final=final,
                       interval_seconds=round(elapsed, 3),
                       frames_received=self.frames_received,
                       frames_processed=self.frames_processed,
                       frames_discarded=self.frames_discarded,
                       received_fps=round(self.frames_received / elapsed, 3) if elapsed else 0.0,
                       processed_fps=round(self.frames_processed / elapsed, 3) if elapsed else 0.0,
                       stages=stages)
        self.logger.info("%s", json.dumps(payload, allow_nan=False))
        self.started_at = now
        self._reset()
