"""Deterministic sampling tests; no OpenCV, models or camera."""
import unittest

from dock_vision.sampling import FileTimeline, FrameSampler


class SamplingTests(unittest.TestCase):
    def test_native_rates_select_three_slots_per_second(self):
        for native_fps in (25, 30, 60):
            sampler = FrameSampler(3)
            selected = [i for i in range(native_fps * 10) if sampler.accept(i / native_fps)]
            self.assertEqual(len(selected), 30)
            self.assertEqual(selected[0], 0)

    def test_slow_source_and_stall_do_not_replay_slots(self):
        sampler = FrameSampler(3)
        self.assertTrue(sampler.accept(100))
        self.assertFalse(sampler.accept(100))
        self.assertTrue(sampler.accept(101))
        self.assertTrue(sampler.accept(200))
        self.assertFalse(sampler.accept(200.01))

    def test_custom_rate_and_invalid_configuration(self):
        sampler = FrameSampler("2")
        self.assertEqual([sampler.accept(t) for t in (0, 0.1, 0.5, 0.9, 1)],
                         [True, False, True, False, True])
        for value in ("", "bad", "nan", "inf", "0", "-1", "1001"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "PROCESS_FPS"):
                FrameSampler(value)

    def test_file_uses_media_positions_despite_incorrect_fps(self):
        timeline = FileTimeline(1)
        values = [timeline.advance(t) for t in (100, 140, 180, 220)]
        for actual, expected in zip(values, (0, 0.04, 0.08, 0.12)):
            self.assertAlmostEqual(actual, expected)

    def test_invalid_file_fps_and_positions_fall_back(self):
        for fps in (0, -1, float("nan"), float("inf"), 1000):
            timeline = FileTimeline(fps)
            values = [timeline.advance(t) for t in (0, 0, float("nan"), -1)]
            for actual, expected in zip(values, (0, 0.04, 0.08, 0.12)):
                self.assertAlmostEqual(actual, expected)

    def test_file_positions_never_rewind_and_can_recover(self):
        timeline = FileTimeline(25)
        values = [timeline.advance(t) for t in (0, 40, 10, 0, 200)]
        for actual, expected in zip(values, (0, 0.04, 0.08, 0.12, 0.2)):
            self.assertAlmostEqual(actual, expected)

    def test_file_can_start_without_media_positions(self):
        timeline = FileTimeline(25)
        values = [timeline.advance(t) for t in (float("nan"), float("nan"), 80, 120)]
        for actual, expected in zip(values, (0, 0.04, 0.08, 0.12)):
            self.assertAlmostEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
