"""Bounded candidate storage scoped to a visit and track."""
from dataclasses import dataclass, field


def capture_manager_config(max_frames_value, interval_ms_value):
    try:
        maximum = int(max_frames_value)
        interval_ms = int(interval_ms_value)
    except (TypeError, ValueError):
        raise ValueError("PLATE_CAPTURE_MAX_FRAMES and PLATE_CAPTURE_INTERVAL_MS must be integers") from None
    if not 1 <= maximum <= 20 or not 0 <= interval_ms <= 60000:
        raise ValueError("Invalid plate candidate limits")
    return maximum, interval_ms / 1000


@dataclass
class CandidateBatch:
    track_id: int
    candidates: list = field(default_factory=list)
    last_captured_at: float | None = None


class CaptureManager:
    def __init__(self, maximum, minimum_interval_seconds):
        self.maximum = maximum
        self.minimum_interval = minimum_interval_seconds
        self.batches = {}

    def add(self, visit_id, track_id, captured_at, candidate):
        if not visit_id:
            return False
        batch = self.batches.get(visit_id)
        if batch is None:
            batch = self.batches[visit_id] = CandidateBatch(track_id)
        if batch.track_id != track_id:
            raise ValueError("A visit cannot change track identity")
        if len(batch.candidates) >= self.maximum:
            return False
        if batch.last_captured_at is not None and captured_at - batch.last_captured_at < self.minimum_interval:
            return False
        batch.candidates.append(candidate)
        batch.last_captured_at = captured_at
        return True

    def pop(self, visit_id):
        batch = self.batches.pop(visit_id, None)
        return [] if batch is None else batch.candidates

    def release_inactive(self, active_visit_ids):
        active = set(active_visit_ids)
        self.batches = {visit_id: batch for visit_id, batch in self.batches.items() if visit_id in active}
