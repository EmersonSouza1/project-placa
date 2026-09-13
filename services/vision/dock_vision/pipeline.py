"""Optional real-video adapters. Imports stay lazy for the simulation image."""
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

log = logging.getLogger(__name__)


class PlateReader:
    def __init__(self, model_path, device):
        if not Path(model_path).is_file():
            raise ValueError("PLATE_MODEL must point to trained plate detection weights")
        from ultralytics import YOLO
        from paddleocr import TextRecognition
        self.detector = YOLO(model_path)
        self.reader = TextRecognition(model_name="en_PP-OCRv4_mobile_rec", device="cpu")
        self.device = device

    def read(self, frame, bounds):
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bounds
        crop = frame[max(0, int(y1)):min(height, int(y2)), max(0, int(x1)):min(width, int(x2))]
        if not crop.size:
            return []
        result = self.detector.predict(crop, conf=0.4, device=self.device, verbose=False)[0]
        candidates = []
        for box in result.boxes:
            px1, py1, px2, py2 = box.xyxy[0].tolist()
            plate = crop[max(0, int(py1)):min(crop.shape[0], int(py2)),
                         max(0, int(px1)):min(crop.shape[1], int(px2))]
            if not plate.size:
                continue
            for recognition in self.reader.predict(input=plate, batch_size=1):
                candidates.append((str(recognition["rec_text"]), float(recognition["rec_score"])))
        # Only one vote per vehicle per frame: overlapping boxes must not inflate consensus.
        return [max(candidates, key=lambda item: item[1])] if candidates else []


def validate_source(source):
    """Validate without inference imports or including secrets in errors."""
    if not source:
        raise ValueError("VIDEO_SOURCE is required in video mode")
    live = source.lower().startswith(("rtsp://", "rtsps://"))
    if live:
        try:
            parsed = urlsplit(source)
            valid = bool(parsed.hostname) and (parsed.port is None or parsed.port > 0)
            valid = valid and not any(c.isspace() or c == "\\" for c in source)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("VIDEO_SOURCE requires an RTSP host and a valid port") from None
    else:
        try:
            valid = Path(source).is_file()
        except (OSError, ValueError):
            valid = False
        if not valid:
            raise ValueError("VIDEO_SOURCE must be an RTSP URL or an existing video file") from None
    return live


def run_video(processor, emit, stop):
    source = os.environ.get("VIDEO_SOURCE", "")
    live = validate_source(source)

    import cv2
    from ultralytics import YOLO

    if stop.is_set():
        return
    device = os.environ.get("DEVICE", "cpu")
    vehicle_weights = os.environ.get("VEHICLE_MODEL", "yolo11n.pt")
    reader = PlateReader(os.environ.get("PLATE_MODEL", "/models/plate.pt"), device) if os.environ.get("OCR_ENABLED", "false").lower() == "true" else None
    model = YOLO(vehicle_weights)
    capture = None
    last_timestamp = time.time()
    try:
        while not stop.is_set():
            # Timeouts prevent an unreachable RTSP source from hanging forever.
            try:
                capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
                ])
                opened = capture.isOpened()
            except cv2.error:
                # Native error text may contain the authenticated source URL.
                opened = False
            if not opened:
                if capture is not None:
                    capture.release()
                    capture = None
                if not live:
                    raise RuntimeError("Unable to open video") from None
                log.warning("Camera unavailable camera_id=%s; retrying in 3 seconds", processor.camera_id)
                stop.wait(3)
                continue
            fps = capture.get(cv2.CAP_PROP_FPS)
            if not 0 < fps < 1000:
                fps = 25
            frame_number, started_at = 0, time.time()
            while not stop.is_set():
                try:
                    ok, frame = capture.read()
                except cv2.error:
                    ok, frame = False, None
                if stop.is_set():
                    break
                if not ok or frame is None or not frame.size:
                    break
                height, width = frame.shape[:2]
                if not height or not width:
                    break
                if frame_number == 0:
                    log.info("First frame received camera_id=%s width=%s height=%s",
                             processor.camera_id, width, height)
                # Files use media time, not CPU inference time, for deterministic dwell.
                last_timestamp = time.time() if live else started_at + frame_number / fps
                frame_number += 1
                result = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[2, 3, 5, 7],
                                     conf=0.25, device=device, verbose=False)[0]
                seen = set()
                if result.boxes.id is not None:
                    for box in result.boxes:
                        track_id = int(box.id.item())
                        seen.add(track_id)
                        bounds = box.xyxy[0].tolist()
                        x1, _, x2, y2 = bounds
                        # Bottom-center approximates vehicle ground contact.
                        point = ((x1 + x2) / (2 * width), y2 / height)
                        readings = []
                        if reader and frame_number % 5 == 0:
                            try:
                                readings = reader.read(frame, bounds)
                            except Exception:
                                log.exception("Plate OCR failed; zone tracking continues")
                        for event in processor.update(track_id, point, last_timestamp, readings):
                            emit(event)
                for event in processor.missing(seen, last_timestamp):
                    emit(event)
            capture.release()
            capture = None
            for event in processor.interrupt(last_timestamp if not live else time.time()):
                emit(event)
            if not live or stop.is_set():
                return
            log.warning("Camera disconnected camera_id=%s; tracking interrupted; retrying in 3 seconds",
                        processor.camera_id)
            if stop.wait(3):
                return
            # A new tracker cannot inherit IDs/state across camera reconnection.
            model = YOLO(vehicle_weights)
    finally:
        if capture is not None:
            capture.release()
        for event in processor.interrupt(last_timestamp if not live else time.time()):
            emit(event)
