"""Deterministic synthetic trajectories, explicitly not a camera/OCR test."""
import time


def run_simulation(processor, emit, stop):
    # The default polygon contains (0.5,0.6), not (0.1,0.1).
    origin = time.time()
    tracks = [
        # Track 1: outside -> inside -> outside; one visit lasting 6 seconds.
        (0, 1, (0.1, 0.1)), (1.2, 1, (0.1, 0.1)),
        (2, 1, (0.5, 0.6)), (3.2, 1, (0.5, 0.6)),
        (6, 1, (0.5, 0.6)), (8, 1, (0.1, 0.1)), (9.2, 1, (0.1, 0.1)),
        # Track 2 starts inside, then disappears: unknown arrival and interrupted stay.
        (10, 2, (0.5, 0.6)), (11.2, 2, (0.5, 0.6)),
    ]
    for offset, track_id, point in tracks:
        if stop.is_set():
            return
        timestamp = origin + offset
        # Synthetic OCR observations validate aggregation, not OCR accuracy.
        readings = [("ABC1D23", 0.92)] if track_id == 1 else []
        for event in processor.missing({track_id}, timestamp):
            emit(event)
        for event in processor.update(track_id, point, timestamp, readings):
            emit(event)
    for event in processor.missing(set(), origin + 17):
        emit(event)

