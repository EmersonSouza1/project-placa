"""Normalized processing region-of-interest helpers."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ProcessingRoi:
    left: float = 0.0
    top: float = 0.0
    right: float = 1.0
    bottom: float = 1.0

    @classmethod
    def parse(cls, value):
        """Parse left,top,right,bottom normalized coordinates."""
        if value is None or not str(value).strip():
            return cls()
        parts = [part.strip() for part in str(value).split(",")]
        if len(parts) != 4:
            raise ValueError("PROCESSING_ROI must contain left,top,right,bottom normalized coordinates")
        try:
            coordinates = tuple(float(part) for part in parts)
        except ValueError:
            raise ValueError("PROCESSING_ROI coordinates must be numbers") from None
        if not all(math.isfinite(coordinate) for coordinate in coordinates):
            raise ValueError("PROCESSING_ROI coordinates must be finite")
        left, top, right, bottom = coordinates
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("PROCESSING_ROI must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1")
        return cls(left, top, right, bottom)

    @property
    def is_full_frame(self):
        return self == ProcessingRoi()

    def pixel_bounds(self, width, height):
        if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
            raise ValueError("Frame width must be a positive integer")
        if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
            raise ValueError("Frame height must be a positive integer")
        left = min(width - 1, int(self.left * width))
        top = min(height - 1, int(self.top * height))
        right = min(width, max(left + 1, math.ceil(self.right * width)))
        bottom = min(height, max(top + 1, math.ceil(self.bottom * height)))
        return left, top, right, bottom

    def crop(self, frame):
        height, width = frame.shape[:2]
        if self.is_full_frame:
            return frame, (0, 0)
        left, top, right, bottom = self.pixel_bounds(width, height)
        crop = frame[top:bottom, left:right]
        if not getattr(crop, "size", 0):
            raise ValueError("PROCESSING_ROI produced an empty frame")
        return crop, (left, top)

    @staticmethod
    def to_frame_bounds(bounds, offset):
        left, top = offset
        x1, y1, x2, y2 = bounds
        return [x1 + left, y1 + top, x2 + left, y2 + top]
