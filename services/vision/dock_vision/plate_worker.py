"""Bounded plate inference workers; domain updates remain on the caller thread."""
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Thread


def plate_worker_config(queue_size_value, workers_value):
    try: queue_size, workers = int(queue_size_value), int(workers_value)
    except (TypeError, ValueError): raise ValueError("PLATE_QUEUE_SIZE and PLATE_WORKERS must be integers") from None
    if not 1 <= queue_size <= 100 or not 1 <= workers <= 4:
        raise ValueError("Invalid plate worker limits")
    return queue_size, workers


@dataclass(frozen=True)
class PlateJob:
    track_id: int
    visit_id: str
    frame: object
    bounds: object


class PlateWorker:
    def __init__(self, read, queue_size, workers):
        self.read = read
        self.jobs, self.results = Queue(queue_size), Queue()
        self.threads = [Thread(target=self._run, daemon=True, name=f"plate-worker-{index}") for index in range(workers)]
        for thread in self.threads: thread.start()

    def submit(self, job):
        try: self.jobs.put_nowait(job); return True
        except Full: return False

    def _run(self):
        while True:
            job = self.jobs.get()
            try:
                if job is None: return
                try: self.results.put((job.track_id, job.visit_id, self.read(job.frame, job.bounds), None))
                except Exception as error: self.results.put((job.track_id, job.visit_id, [], error))
            finally: self.jobs.task_done()

    def drain(self):
        items = []
        while True:
            try: items.append(self.results.get_nowait())
            except Empty: return items

    def close(self, timeout=5):
        for _ in self.threads: self.jobs.put(None)
        for thread in self.threads: thread.join(timeout)
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError("Plate worker did not stop")
