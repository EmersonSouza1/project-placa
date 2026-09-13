from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import tempfile
import threading
import unittest

from dock_vision.outbox import Outbox


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.requests = []
        self.status = 201
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                case.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(case.status)
                self.end_headers()

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.path = self.temp.name + "/outbox.sqlite3"
        self.url = f"http://127.0.0.1:{self.server.server_port}/dock-events"
        self.outbox = Outbox(self.path, self.url)
        self.event = dict(event_id="event-1", visit_id="visit-1", event_type="entered")

    def tearDown(self):
        self.outbox.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_durable_queue_and_success(self):
        self.outbox.enqueue(self.event)
        reloaded = Outbox(self.path, self.url)
        self.assertTrue(reloaded.deliver_once())
        self.assertEqual(self.requests, [self.event])
        self.assertFalse(reloaded.deliver_once())

    def test_retry_keeps_identical_event(self):
        self.status = 503
        self.outbox.enqueue(self.event)
        self.outbox.deliver_once()
        with self.outbox.connect() as db:
            self.assertEqual(db.execute("SELECT state,attempts FROM outbox").fetchone(), ("pending", 1))
            db.execute("UPDATE outbox SET next_attempt=0")
        self.status = 200
        self.outbox.deliver_once()
        self.assertEqual(self.requests, [self.event, self.event])

    def test_permanent_rejection_is_retained_and_next_event_can_pass(self):
        self.status = 409
        self.outbox.enqueue(self.event)
        self.outbox.deliver_once()
        with self.outbox.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM outbox").fetchone()[0], "rejected")
        self.status = 201
        self.outbox.enqueue(dict(self.event, event_id="event-2"))
        self.assertTrue(self.outbox.deliver_once())
        with self.outbox.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)

    def test_rate_limit_remains_retryable(self):
        self.status = 429
        self.outbox.enqueue(self.event)
        self.outbox.deliver_once()
        with self.outbox.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM outbox").fetchone()[0], "pending")


if __name__ == "__main__":
    unittest.main()

