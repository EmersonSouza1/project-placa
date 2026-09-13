"""Persistent HTTP delivery. A failed request never discards an event."""
import json
from contextlib import contextmanager
import logging
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


class Outbox:
    def __init__(self, path, url):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path, self.url = str(path), url
        self.stop = threading.Event()
        self.thread = None
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS outbox (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0, last_error TEXT)""")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def enqueue(self, event):
        with self.connect() as db:
            db.execute("INSERT INTO outbox(event_id,payload) VALUES (?,?)",
                       (event["event_id"], json.dumps(event)))
        log.info("event queued: %s visit=%s", event["event_type"], event["visit_id"])

    def deliver_once(self):
        with self.connect() as db:
            row = db.execute("SELECT sequence,payload,attempts,next_attempt FROM outbox WHERE state='pending' ORDER BY sequence LIMIT 1").fetchone()
        if not row or row[3] > time.time():
            return False
        sequence, payload, attempts, _ = row
        state, error = "pending", None
        try:
            request = urllib.request.Request(self.url, data=payload.encode(),
                                             headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                if not 200 <= response.status < 300:
                    raise OSError(f"HTTP {response.status}")
            state = "delivered"
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}"
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                state = "rejected"
        except (OSError, TimeoutError) as exc:
            # Do not log URLs, which may include credentials.
            error = type(exc).__name__
        with self.connect() as db:
            if state == "delivered":
                db.execute("DELETE FROM outbox WHERE sequence=?", (sequence,))
            else:
                db.execute("UPDATE outbox SET state=?,attempts=?,next_attempt=?,last_error=? WHERE sequence=?",
                           (state, attempts + 1, time.time() + min(60, 2 ** min(attempts, 6)), error, sequence))
                log.warning("event delivery %s: %s (attempt %s)", state, error, attempts + 1)
        return True

    def start(self):
        def run():
            while not self.stop.is_set():
                try:
                    if not self.deliver_once():
                        self.stop.wait(0.5)
                except sqlite3.Error:
                    log.exception("outbox database failure")
                    self.stop.wait(2)
        self.thread = threading.Thread(target=run, name="event-delivery", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=7)
