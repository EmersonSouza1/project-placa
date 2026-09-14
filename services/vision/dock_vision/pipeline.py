"""Optional real-video adapters. Imports stay lazy for the simulation image."""
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from time import monotonic

from .metrics import PipelineMetrics
from .motion import MotionDetector, motion_config
from .plate_capture import PlateCapturePolicy, plate_capture_config
from .plate_worker import PlateJob, PlateWorker, plate_worker_config
from .sampling import FrameSampler
from .roi import ProcessingRoi
from .stream_reader import StreamReader, queue_capacity

log = logging.getLogger(__name__)


class PlateReader:
    def __init__(self, model_path, device, metrics):
        if not Path(model_path).is_file():
            raise ValueError("PLATE_MODEL must point to trained plate detection weights")
        from ultralytics import YOLO
        from paddleocr import TextRecognition
        self.detector = YOLO(model_path)
        self.reader = TextRecognition(model_name="en_PP-OCRv4_mobile_rec", device="cpu")
        self.device = device
        self.metrics = metrics

    def read(self, frame, bounds):
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bounds
        crop = frame[max(0, int(y1)):min(height, int(y2)), max(0, int(x1)):min(width, int(x2))]
        if not crop.size:
            return []
        with self.metrics.measure("plate_detection"):
            result = self.detector.predict(crop, conf=0.4, device=self.device, verbose=False)[0]
        candidates = []
        for box in result.boxes:
            px1, py1, px2, py2 = box.xyxy[0].tolist()
            plate = crop[max(0, int(py1)):min(crop.shape[0], int(py2)),
                         max(0, int(px1)):min(crop.shape[1], int(px2))]
            if not plate.size:
                continue
            with self.metrics.measure("ocr"):
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
    process_fps = os.environ.get("PROCESS_FPS", "3")
    FrameSampler(process_fps)  # Validate configuration before loading models.
    processing_roi = ProcessingRoi.parse(os.environ.get("PROCESSING_ROI", ""))
    motion_enabled, motion_ratio = motion_config(os.environ.get("MOTION_ENABLED", "false"), os.environ.get("MOTION_MINIMUM_CHANGED_RATIO", "0.02"))
    capture_attempts, capture_window = plate_capture_config(
        os.environ.get("PLATE_CAPTURE_MAX_ATTEMPTS", "5"),
        os.environ.get("PLATE_CAPTURE_WINDOW_SECONDS", "10"))
    plate_queue_size, plate_workers = plate_worker_config(
        os.environ.get("PLATE_QUEUE_SIZE", "5"), os.environ.get("PLATE_WORKERS", "1"))
    capacity = queue_capacity(os.environ.get("FRAME_QUEUE_SIZE", "5"))

    import cv2
    from ultralytics import YOLO

    if stop.is_set():
        return
    device = os.environ.get("DEVICE", "cpu")
    vehicle_weights = os.environ.get("VEHICLE_MODEL", "yolo11n.pt")
    metrics = PipelineMetrics(log, processor.camera_id, processor.stream_id)
    reader = PlateReader(os.environ.get("PLATE_MODEL", "/models/plate.pt"), device, metrics) if os.environ.get("OCR_ENABLED", "false").lower() == "true" else None
    model = YOLO(vehicle_weights)
    plate_worker = PlateWorker(reader.read, plate_queue_size, plate_workers) if reader else None
    capture = None
    session = 0
    last_timestamp = time.time()
    try:
        while not stop.is_set():
            metrics.report()
            try:
                capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
                ])
                opened = capture.isOpened()
            except cv2.error:
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
            session += 1
            stream = StreamReader(capture, cv2, live, stop, capacity, process_fps,
                                  session, log, processor.camera_id,
                                  wall_clock=time.time, sample_clock=monotonic)
            stream.start()
            motion = MotionDetector(cv2, motion_ratio) if motion_enabled else None
            plate_capture = PlateCapturePolicy(capture_attempts, capture_window)
            capture = None  # The capture thread now owns read/release.
            processed_number = 0
            try:
                while not stop.is_set():
                    packet = stream.get()
                    metrics.capture_snapshot(stream.snapshot())
                    metrics.report()
                    if packet is None:
                        if stream.finished:
                            break
                        continue
                    if packet.session != session:
                        raise RuntimeError("Capture session mismatch")
                    if plate_worker:
                        for track_id, visit_id, readings, error in plate_worker.drain():
                            if error:
                                log.error("Plate OCR failed; zone tracking continues", exc_info=error)
                            else:
                                processor.add_plate_readings(track_id, visit_id, readings)
                    frame, last_timestamp = packet.image, packet.timestamp
                    height, width = frame.shape[:2]
                    inference_frame, roi_offset = processing_roi.crop(frame)
                    if motion and not motion.has_motion(inference_frame):
                        metrics.frames_discarded += 1
                        continue
                    processed_number += 1
                    metrics.frames_processed += 1
                    with metrics.measure("vehicle_tracking"):
                        result = model.track(inference_frame, persist=True, tracker="bytetrack.yaml",
                                             classes=[2, 3, 5, 7], conf=0.25,
                                             device=device, verbose=False)[0]
                    seen = set()
                    if result.boxes.id is not None:
                        for box in result.boxes:
                            track_id = int(box.id.item())
                            seen.add(track_id)
                            bounds = processing_roi.to_frame_bounds(
                                box.xyxy[0].tolist(), roi_offset)
                            x1, _, x2, y2 = bounds
                            point = ((x1 + x2) / (2 * width), y2 / height)
                            for event in processor.update(track_id, point, last_timestamp):
                                emit(event)
                            visit_id, has_consensus = processor.plate_capture_context(track_id)
                            if plate_worker and plate_capture.should_capture(
                                    visit_id, last_timestamp, has_consensus):
                                if not plate_worker.submit(PlateJob(
                                        track_id, visit_id, frame, bounds)):
                                    log.warning("Plate queue full; capture discarded track_id=%s", track_id)
                    for event in processor.missing(seen, last_timestamp):
                        emit(event)
                    plate_capture.retain(processor.active_visit_ids())
                if stream.failed:
                    raise RuntimeError("Capture worker failed") from None
            finally:
                try:
                    stream.close()
                finally:
                    metrics.capture_snapshot(stream.snapshot())
                    last_timestamp = stream.last_timestamp
            for event in processor.interrupt(last_timestamp if not live else time.time()):
                emit(event)
            if not live or stop.is_set():
                return
            log.warning("Camera disconnected camera_id=%s; tracking interrupted; retrying in 3 seconds",
                        processor.camera_id)
            if stop.wait(3):
                return
            model = YOLO(vehicle_weights)
    finally:
        try:
            if capture is not None:
                capture.release()
            for event in processor.interrupt(last_timestamp if not live else time.time()):
                emit(event)
        finally:
            if plate_worker:
                plate_worker.close()
            metrics.report(final=True)
