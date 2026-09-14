"""Pure zone/plate logic: no model, camera, database or network dependency."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import re
from uuid import uuid4


def normalize_plate(text: str) -> str | None:
    # Do not silently replace ambiguous letters/digits and invent a plate.
    plate = re.sub(r"[\s-]", "", text.upper())
    return plate if re.fullmatch(r"[A-Z]{3}(?:[0-9]{4}|[0-9][A-Z][0-9]{2})", plate) else None


@dataclass
class PlateVotes:
    minimum_observations: int = 2
    minimum_confidence: float = 0.7
    votes: dict[str, list[float]] = field(default_factory=dict)

    def add(self, text: str, confidence: float):
        plate = normalize_plate(text)
        if plate and math.isfinite(confidence) and self.minimum_confidence <= confidence <= 1:
            # Bounded memory per track; sum, count. At most 64 distinct hypotheses.
            if plate not in self.votes and len(self.votes) >= 64:
                return
            vote = self.votes.setdefault(plate, [0.0, 0])
            vote[0] += confidence
            vote[1] += 1

    def best(self) -> tuple[str | None, float | None]:
        eligible = [(text, total, count) for text, (total, count) in self.votes.items()
                    if count >= self.minimum_observations]
        if not eligible:
            return None, None
        text, total, count = max(eligible, key=lambda v: (v[1], v[2], v[0]))
        return text, round(total / count, 4)


def point_in_polygon(point, polygon) -> bool:
    """Ray casting, including the boundary. Coordinates are normalized 0..1."""
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) < 1e-10 and min(ax, bx) <= x <= max(ax, bx) and min(ay, by) <= y <= max(ay, by):
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


@dataclass
class Track:
    last_seen: float
    stable: bool | None = None
    candidate: bool | None = None
    candidate_since: float = 0
    visit_id: str | None = None
    plates: PlateVotes = field(default_factory=PlateVotes)


class ZoneProcessor:
    def __init__(self, camera_id, dock_id, polygon, confirmation_seconds=1.0,
                 lost_after_seconds=5.0, minimum_plate_observations=2,
                 minimum_plate_confidence=0.7, stream_id=None):
        if len(polygon) < 3 or any(len(p) != 2 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in polygon):
            raise ValueError("Zone must contain at least 3 normalized points")
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
        if abs(area) < 1e-8:
            raise ValueError("Zone must have a nonzero area")
        if not 0 < confirmation_seconds < lost_after_seconds:
            raise ValueError("Require 0 < confirmation_seconds < lost_after_seconds")
        if minimum_plate_observations < 1 or not 0 <= minimum_plate_confidence <= 1:
            raise ValueError("Invalid plate aggregation settings")
        self.camera_id, self.dock_id, self.polygon = camera_id, dock_id, polygon
        self.confirmation = confirmation_seconds
        self.lost_after = lost_after_seconds
        self.minimum_observations = minimum_plate_observations
        self.minimum_confidence = minimum_plate_confidence
        self.stream_id = stream_id or str(uuid4())
        self.tracks: dict[int, Track] = {}

    def event(self, track_id, track, kind, timestamp):
        plate, confidence = track.plates.best()
        return dict(event_id=str(uuid4()), visit_id=track.visit_id,
                    camera_id=self.camera_id, dock_id=self.dock_id,
                    stream_id=self.stream_id, track_id=track_id, event_type=kind,
                    occurred_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    plate=plate, plate_confidence=confidence)

    def update(self, track_id, point, timestamp, readings=()):
        track = self.tracks.setdefault(track_id, Track(timestamp, plates=PlateVotes(
            self.minimum_observations, self.minimum_confidence)))
        track.last_seen = timestamp
        for text, confidence in readings:
            track.plates.add(text, confidence)
        inside = point_in_polygon(point, self.polygon)
        if track.candidate != inside:
            track.candidate, track.candidate_since = inside, timestamp
        if timestamp - track.candidate_since < self.confirmation or track.stable == inside:
            return []
        previous, track.stable = track.stable, inside
        if inside:
            track.visit_id = str(uuid4())
            return [self.event(track_id, track, "entered" if previous is False else "observed_inside", timestamp)]
        if previous is True:
            result = self.event(track_id, track, "exited", timestamp)
            track.visit_id = None
            track.plates = PlateVotes(self.minimum_observations, self.minimum_confidence)
            return [result]
        return []

    def plate_capture_context(self, track_id):
        track = self.tracks.get(track_id)
        if not track or not track.visit_id:
            return None, False
        plate, _ = track.plates.best()
        return track.visit_id, plate is not None

    def add_plate_readings(self, track_id, visit_id, readings):
        track = self.tracks.get(track_id)
        if not track or track.visit_id != visit_id:
            return
        for text, confidence in readings:
            track.plates.add(text, confidence)

    def active_visit_ids(self):
        return {track.visit_id for track in self.tracks.values() if track.visit_id}

    def missing(self, seen_ids, timestamp):
        events = []
        for track_id, track in list(self.tracks.items()):
            if track_id in seen_ids:
                continue
            # A gap must not count towards consecutive zone confirmation.
            track.candidate = None
            if timestamp - track.last_seen >= self.lost_after:
                if track.visit_id:
                    events.append(self.event(track_id, track, "tracking_lost", timestamp))
                del self.tracks[track_id]
        return events

    def interrupt(self, timestamp):
        events = [self.event(tid, t, "tracking_lost", timestamp)
                  for tid, t in self.tracks.items() if t.visit_id]
        self.tracks.clear()
        return events

