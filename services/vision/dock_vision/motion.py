"""Lightweight frame-difference gate for vehicle inference."""

def motion_config(enabled_value, ratio_value):
    enabled = str(enabled_value).strip().lower()
    if enabled not in ("true", "false"): raise ValueError("MOTION_ENABLED must be true or false")
    try: ratio = float(ratio_value)
    except (TypeError, ValueError): raise ValueError("MOTION_MINIMUM_CHANGED_RATIO must be a number") from None
    if not 0 < ratio <= 1: raise ValueError("MOTION_MINIMUM_CHANGED_RATIO must be greater than 0 and at most 1")
    return enabled == "true", ratio

class MotionDetector:
    def __init__(self, cv2, ratio): self.cv2, self.ratio, self.previous = cv2, ratio, None
    def has_motion(self, frame):
        gray = self.cv2.GaussianBlur(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY), (5, 5), 0)
        if self.previous is None:
            self.previous = gray
            return True
        difference = self.cv2.absdiff(self.previous, gray)
        self.previous = gray
        _, changed = self.cv2.threshold(difference, 25, 255, self.cv2.THRESH_BINARY)
        return self.cv2.countNonZero(changed) / changed.size >= self.ratio
