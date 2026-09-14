"""Bounded, visit-oriented plate capture policy."""
from dataclasses import dataclass
import math


def plate_capture_config(max_attempts_value, window_seconds_value):
    try:
        max_attempts = int(max_attempts_value)
    except (TypeError, ValueError):
        raise ValueError("PLATE_CAPTURE_MAX_ATTEMPTS must be an integer") from None
    try:
        window_seconds = float(window_seconds_value)
    except (TypeError, ValueError):
        raise ValueError("PLATE_CAPTURE_WINDOW_SECONDS must be a number") from None
    if not 1 <= max_attempts <= 100:
        raise ValueError("PLATE_CAPTURE_MAX_ATTEMPTS must be between 1 and 100")
    if not math.isfinite(window_seconds) or not 0 < window_seconds <= 300:
        raise ValueError("PLATE_CAPTURE_WINDOW_SECONDS must be greater than 0 and at most 300")
    return max_attempts, window_seconds


@dataclass
class CaptureState:
    started_at: float
    attempts: int = 0


class PlateCapturePolicy:
    def __init__(self, max_attempts, window_seconds):
        self.max_attempts, self.window_seconds = max_attempts, window_seconds
        self.states = {}

    def should_capture(self, visit_id, timestamp, has_consensus):
        if not visit_id or has_consensus:
            return False
        state = self.states.setdefault(visit_id, CaptureState(timestamp))
        if timestamp - state.started_at > self.window_seconds or state.attempts >= self.max_attempts:
            return False
        state.attempts += 1
        return True

    def retain(self, active_visit_ids):
        active = set(active_visit_ids)
        self.states = {visit_id: state for visit_id, state in self.states.items() if visit_id in active}
