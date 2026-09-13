"""Full-frame OCR diagnostic for a plate displayed on a phone; no dock events."""
from datetime import datetime, timezone
import json
import logging
import math
import os
from queue import Empty, Full, Queue
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from .domain import normalize_plate
from .pipeline import validate_source

log = logging.getLogger(__name__)


def best_plate(results):
    candidates = []
    for result in results:
        for text, score in zip(result.get("rec_texts", []), result.get("rec_scores", [])):
            plate = normalize_plate(str(text))
            confidence = float(score)
            if plate and math.isfinite(confidence) and 0.7 <= confidence <= 1:
                candidates.append((plate, confidence))
    return max(candidates, key=lambda candidate: candidate[1], default=None)


class Confirmation:
    """Require the same plate on two distinct recent frames of one connection."""
    def __init__(self):
        self.previous = None

    def update(self, candidate, timestamp, session):
        previous, self.previous = self.previous, (candidate, timestamp, session)
        if candidate and previous and previous[0] and candidate[0] == previous[0][0] and \
                session == previous[2] and 0 < timestamp - previous[1] <= 15:
            return candidate
        return None


def capture_latest(source, camera_id, frames, stop):
    import cv2
    session = 0
    while not stop.is_set():
        capture = None
        try:
            capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
            ])
            session += 1
            first = True
            while capture.isOpened() and not stop.is_set():
                ok, frame = capture.read()
                if not ok or frame is None or not frame.size:
                    break
                timestamp = time.time()
                if first:
                    log.info("OCR test receiving frames camera_id=%s width=%s height=%s",
                             camera_id, frame.shape[1], frame.shape[0])
                    first = False
                try:
                    frames.get_nowait()
                except Empty:
                    pass
                try:
                    frames.put_nowait((frame, timestamp, session))
                except Full:
                    pass
        except cv2.error:
            # Do not expose native errors containing the authenticated source.
            pass
        finally:
            if capture is not None:
                capture.release()
            try:
                frames.get_nowait()
            except Empty:
                pass
        if not stop.is_set():
            log.warning("OCR test camera unavailable camera_id=%s; retrying in 3 seconds", camera_id)
            stop.wait(3)


def publish_observation(url, camera_id, candidate, timestamp):
    plate, confidence = candidate
    body = json.dumps(dict(camera_id=camera_id, plate=plate, confidence=confidence,
                           detected_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat())).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        response.read()


def run_ocr_test(stop):
    source = os.environ.get("VIDEO_SOURCE", "")
    if not validate_source(source):
        raise ValueError("ocr_test requires an RTSP camera source")
    from paddleocr import PaddleOCR

    camera_id = os.environ.get("CAMERA_ID", "camera-01")
    url = os.environ.get("OCR_OBSERVATIONS_URL", "http://localhost:5080/ocr-observations")
    reader = PaddleOCR(text_detection_model_name="PP-OCRv5_mobile_det",
                       text_recognition_model_name="en_PP-OCRv4_mobile_rec",
                       use_doc_orientation_classify=False, use_doc_unwarping=False,
                       use_textline_orientation=False, device="cpu", enable_mkldnn=False)
    frames = Queue(maxsize=1)
    capture = threading.Thread(target=capture_latest, args=(source, camera_id, frames, stop), daemon=True)
    confirmation = Confirmation()
    capture.start()
    log.info("OCR test ready camera_id=%s; show a plate to the camera", camera_id)
    try:
        while not stop.is_set():
            try:
                frame, timestamp, session = frames.get(timeout=1)
            except Empty:
                continue
            try:
                candidate = best_plate(reader.predict(frame))
            except Exception:
                log.exception("OCR test inference failed")
                confirmation = Confirmation()
                stop.wait(1)
                continue
            confirmed = confirmation.update(candidate, timestamp, session)
            if confirmed and not stop.is_set():
                try:
                    publish_observation(url, camera_id, confirmed, timestamp)
                    log.info("OCR plate detected camera_id=%s plate=%s detected_at=%s",
                             camera_id, confirmed[0], datetime.fromtimestamp(timestamp, timezone.utc).isoformat())
                except (URLError, TimeoutError, OSError):
                    log.warning("OCR observation delivery failed; next confirmed frame will retry")
            stop.wait(0.5)
    finally:
        stop.set()
        capture.join(timeout=6)
