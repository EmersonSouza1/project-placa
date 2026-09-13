"""Frame selection and file timestamps without camera or inference dependencies."""
import math


class FrameSampler:
    """Select at most one frame per time slot, without replaying missed slots."""

    def __init__(self, fps):
        try:
            self.fps = float(fps)
        except (TypeError, ValueError):
            raise ValueError("PROCESS_FPS must be finite and greater than zero") from None
        if not math.isfinite(self.fps) or not 0 < self.fps <= 1000:
            raise ValueError("PROCESS_FPS must be finite and in (0, 1000]")
        self.origin = None
        self.last_slot = -1

    def accept(self, timestamp):
        if self.origin is None:
            self.origin = timestamp
        slot = math.floor((timestamp - self.origin) * self.fps + 1e-7)
        if slot <= self.last_slot:
            return False
        self.last_slot = slot
        return True


class FileTimeline:
    """Prefer advancing media positions; otherwise advance using validated FPS."""

    def __init__(self, fps):
        self.step = 1 / fps if math.isfinite(fps) and 0 < fps < 1000 else 1 / 25
        self.elapsed = None
        self.origin = None

    def advance(self, position_ms):
        position = position_ms / 1000
        if self.elapsed is None:
            self.elapsed = 0.0
            if math.isfinite(position) and position >= 0:
                self.origin = position
            return self.elapsed
        fallback = self.elapsed + self.step
        if math.isfinite(position) and position >= 0:
            if self.origin is None:
                self.origin = position - fallback
            candidate = position - self.origin
            self.elapsed = candidate if candidate > self.elapsed else fallback
        else:
            self.elapsed = fallback
        return self.elapsed
