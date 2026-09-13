import json
import logging
import os
from pathlib import Path
import signal
import threading

from .domain import ZoneProcessor
from .outbox import Outbox
from .simulation import run_simulation


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    mode = os.environ.get("SOURCE_MODE", "simulation")
    if mode == "ocr_test":
        from .ocr_test import run_ocr_test
        run_ocr_test(stop)
        return
    config_path = Path(os.environ.get("ZONE_PATH", "../../config/zone.json"))
    processor = ZoneProcessor(os.environ.get("CAMERA_ID", "camera-01"),
                              os.environ.get("DOCK_ID", "dock-01"), **json.loads(config_path.read_text()))
    outbox = Outbox(os.environ.get("OUTBOX_PATH", "../../data/outbox.sqlite3"),
                    os.environ.get("EVENTS_URL", "http://localhost:5080/dock-events"))
    outbox.start()
    try:
        if mode == "simulation":
            run_simulation(processor, outbox.enqueue, stop)
            logging.info("Simulation finished: expected 4 events / 2 stays with default zone. Delivery remains active.")
        elif mode == "video":
            from .pipeline import run_video
            run_video(processor, outbox.enqueue, stop)
            logging.info("Video finished; delivery remains active.")
        else:
            raise ValueError("SOURCE_MODE must be simulation, video or ocr_test")
        # Remain alive to deliver retries and permit inspection; never replay automatically.
        while not stop.wait(1):
            pass
    finally:
        outbox.close()


if __name__ == "__main__":
    main()
