"""Deterministic best-frame selection without OCR dependencies."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class FrameScore:
    total: float
    sharpness: float
    detector_confidence: float
    relative_area: float


class BestFrameSelector:
    def __init__(self, cv2, sharpness_weight=0.5, confidence_weight=0.3, area_weight=0.2):
        weights = (sharpness_weight, confidence_weight, area_weight)
        if any(not math.isfinite(value) or value < 0 for value in weights) or abs(sum(weights) - 1) > 1e-9:
            raise ValueError("Best-frame weights must be non-negative and sum to 1")
        self.cv2 = cv2
        self.weights = weights

    def score(self, candidate):
        gray = self.cv2.cvtColor(candidate.image, self.cv2.COLOR_BGR2GRAY)
        variance = max(0.0, float(self.cv2.Laplacian(gray, self.cv2.CV_64F).var()))
        sharpness = variance / (variance + 100)
        confidence = min(1.0, max(0.0, float(candidate.detector_confidence)))
        area = min(1.0, max(0.0, float(candidate.relative_area)) / 0.05)
        total = sum(value * weight for value, weight in zip((sharpness, confidence, area), self.weights))
        return FrameScore(total, sharpness, confidence, area)

    def select(self, candidates):
        ranked = [(self.score(candidate), index, candidate) for index, candidate in enumerate(candidates)]
        return max(ranked, key=lambda item: (item[0].total, -item[1]))[2] if ranked else None
