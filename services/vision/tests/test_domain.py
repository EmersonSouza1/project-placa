import unittest
from threading import Event

from dock_vision.domain import PlateVotes, ZoneProcessor, normalize_plate, point_in_polygon
from dock_vision.simulation import run_simulation

POLYGON = [[0.3, 0.3], [0.8, 0.3], [0.8, 0.9], [0.3, 0.9]]
IN, OUT = (0.5, 0.6), (0.1, 0.1)


class ZoneTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneProcessor("camera", "dock", POLYGON)

    def update(self, point, timestamp, track=1):
        return self.zone.update(track, point, timestamp)

    def enter(self):
        self.update(OUT, 0)
        self.update(OUT, 1)
        self.update(IN, 2)
        return self.update(IN, 3)[0]

    def test_entry_exit_and_reentry(self):
        entry = self.enter()
        self.assertEqual(entry["event_type"], "entered")
        self.assertEqual(self.update(IN, 4), [])
        self.update(OUT, 5)
        exit_event = self.update(OUT, 6)[0]
        self.assertEqual(exit_event["event_type"], "exited")
        self.assertEqual(entry["visit_id"], exit_event["visit_id"])
        self.assertNotEqual(entry["event_id"], exit_event["event_id"])
        self.update(IN, 7)
        self.assertNotEqual(self.update(IN, 8)[0]["visit_id"], entry["visit_id"])

    def test_border_jitter_does_not_emit(self):
        self.update(OUT, 0)
        self.update(OUT, 1)
        for index in range(20):
            self.assertEqual(self.update(IN if index % 2 else OUT, 2 + index * 0.1), [])

    def test_starts_inside_is_not_an_entry(self):
        self.update(IN, 0)
        self.assertEqual(self.update(IN, 1)[0]["event_type"], "observed_inside")

    def test_loss_is_not_exit_and_state_is_evicted(self):
        entry = self.enter()
        self.assertEqual(self.zone.missing(set(), 4), [])
        loss = self.zone.missing(set(), 8)[0]
        self.assertEqual(loss["event_type"], "tracking_lost")
        self.assertEqual(loss["visit_id"], entry["visit_id"])
        self.assertEqual(self.zone.tracks, {})
        self.assertEqual(self.zone.missing(set(), 9), [])

    def test_missing_frame_resets_transition_confirmation(self):
        self.update(OUT, 0)
        self.update(OUT, 1)
        self.update(IN, 2)
        self.zone.missing(set(), 2.5)
        self.assertEqual(self.update(IN, 3), [])
        self.assertEqual(self.update(IN, 4)[0]["event_type"], "entered")

    def test_occlusion_keeps_existing_visit(self):
        entry = self.enter()
        self.zone.missing(set(), 4)
        self.assertEqual(self.update(IN, 5), [])
        self.assertEqual(self.zone.tracks[1].visit_id, entry["visit_id"])

    def test_outside_track_loss_has_no_event(self):
        self.update(OUT, 0)
        self.update(OUT, 1)
        self.assertEqual(self.zone.missing(set(), 6), [])
        self.assertFalse(self.zone.tracks)

    def test_interrupt_emits_once(self):
        self.enter()
        self.assertEqual(self.zone.interrupt(4)[0]["event_type"], "tracking_lost")
        self.assertEqual(self.zone.interrupt(5), [])

    def test_tracks_and_worker_runs_have_separate_identity(self):
        first = self.enter()
        self.update(IN, 4, track=2)
        second = self.update(IN, 5, track=2)[0]
        self.assertNotEqual(first["visit_id"], second["visit_id"])
        other = ZoneProcessor("camera", "dock", POLYGON)
        self.assertNotEqual(other.stream_id, self.zone.stream_id)

    def test_polygon_and_validation(self):
        self.assertTrue(point_in_polygon(IN, POLYGON))
        self.assertTrue(point_in_polygon((0.3, 0.3), POLYGON))
        self.assertFalse(point_in_polygon(OUT, POLYGON))
        with self.assertRaises(ValueError):
            ZoneProcessor("c", "d", [[0, 0], [0, 0], [0, 0]])
        with self.assertRaises(ValueError):
            ZoneProcessor("c", "d", POLYGON, confirmation_seconds=6)

    def test_simulation_contract(self):
        events = []
        run_simulation(self.zone, events.append, Event())
        self.assertEqual([e["event_type"] for e in events],
                         ["entered", "exited", "observed_inside", "tracking_lost"])
        self.assertEqual(events[0]["visit_id"], events[1]["visit_id"])
        self.assertEqual(events[2]["visit_id"], events[3]["visit_id"])
        self.assertEqual(events[0]["plate"], "ABC1D23")
        self.assertIsNone(events[2]["plate"])


class PlateTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(normalize_plate("abc-1234"), "ABC1234")
        self.assertEqual(normalize_plate(" ABC 1D23 "), "ABC1D23")
        for text in ["BRASIL", "ABC123", "ABC12345", "ABCID23", "ABC@1234"]:
            self.assertIsNone(normalize_plate(text))

    def test_consensus_and_confidence(self):
        votes = PlateVotes()
        votes.add("ABC1D23", 0.9)
        self.assertEqual(votes.best(), (None, None))
        votes.add("ABC1D23", 0.8)
        votes.add("XYZ1234", 0.99)
        votes.add("ABC1D23", float("nan"))
        votes.add("ABC1D23", 0.2)
        self.assertEqual(votes.best(), ("ABC1D23", 0.85))

    def test_plate_can_arrive_after_entry_and_is_in_exit(self):
        zone = ZoneProcessor("c", "d", POLYGON)
        zone.update(1, OUT, 0)
        zone.update(1, OUT, 1)
        zone.update(1, IN, 2)
        self.assertIsNone(zone.update(1, IN, 3)[0]["plate"])
        zone.update(1, IN, 4, [("ABC1234", 0.95)])
        zone.update(1, OUT, 5, [("ABC1234", 0.91)])
        self.assertEqual(zone.update(1, OUT, 6)[0]["plate"], "ABC1234")


if __name__ == "__main__":
    unittest.main()

