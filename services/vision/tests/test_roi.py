import math
import unittest

from dock_vision.roi import ProcessingRoi


class SliceFrame:
    def __init__(self, shape=(100, 200, 3)):
        self.shape = shape
        self.size = shape[0] * shape[1] * shape[2]

    def __getitem__(self, selection):
        rows, columns = selection
        return SliceFrame((rows.stop - rows.start, columns.stop - columns.start, self.shape[2]))


class ProcessingRoiTests(unittest.TestCase):
    def test_empty_configuration_preserves_full_frame(self):
        image = SliceFrame()
        cropped, offset = ProcessingRoi.parse("").crop(image)
        self.assertIs(cropped, image)
        self.assertEqual(offset, (0, 0))

    def test_normalized_roi_crops_and_translates_detection(self):
        roi = ProcessingRoi.parse("0.25,0.20,0.75,0.80")
        cropped, offset = roi.crop(SliceFrame())
        self.assertEqual(cropped.shape, (60, 100, 3))
        self.assertEqual(offset, (50, 20))
        bounds = roi.to_frame_bounds([10, 5, 70, 50], offset)
        self.assertEqual(bounds, [60, 25, 120, 70])
        x1, _, x2, y2 = bounds
        self.assertEqual(((x1 + x2) / 400, y2 / 100), (0.45, 0.7))

    def test_fractional_edges_cover_configured_region(self):
        self.assertEqual(ProcessingRoi.parse("0.333,0.111,0.667,0.889").pixel_bounds(10, 10), (3, 1, 7, 9))

    def test_invalid_configuration_is_rejected(self):
        invalid = ("0,0,1", "a,0,1,1", "nan,0,1,1", "0,0,inf,1",
                   "-0.1,0,1,1", "0,0,1.1,1", "0.5,0,0.5,1", "0,0.8,1,0.2")
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ProcessingRoi.parse(value)

    def test_invalid_frame_dimensions_are_rejected(self):
        for width, height in ((0, 1), (1, 0), (-1, 1), (1.5, 1), (1, math.nan)):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                ProcessingRoi().pixel_bounds(width, height)


if __name__ == "__main__":
    unittest.main()
