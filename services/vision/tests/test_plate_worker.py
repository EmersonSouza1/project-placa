import unittest
from threading import Event
from dock_vision.plate_worker import PlateJob, PlateWorker, plate_worker_config

class PlateWorkerTests(unittest.TestCase):
    def test_configuration(self):
        self.assertEqual(plate_worker_config("5","1"),(5,1))
        for values in (("0","1"),("101","1"),("1","0"),("1","5"),("x","1")):
            with self.assertRaises(ValueError): plate_worker_config(*values)
    def test_result_preserves_identity_and_models_are_reused(self):
        called=[]
        worker=PlateWorker(lambda frame,bounds: called.append((frame,bounds)) or [("ABC1234",.9)],2,1)
        worker.submit(PlateJob(7,"visit","frame","bounds"))
        worker.jobs.join()
        result=worker.drain()[0]
        worker.close()
        self.assertEqual(result[:3],(7,"visit",[("ABC1234",.9)]))
        self.assertEqual(called,[("frame","bounds")])
    def test_queue_is_bounded(self):
        blocked=Event(); release=Event()
        def read(*_): blocked.set(); release.wait(2); return []
        worker=PlateWorker(read,1,1)
        worker.submit(PlateJob(1,"a",None,None)); blocked.wait(1)
        self.assertTrue(worker.submit(PlateJob(2,"b",None,None)))
        self.assertFalse(worker.submit(PlateJob(3,"c",None,None)))
        release.set(); worker.jobs.join(); worker.close()
if __name__=="__main__": unittest.main()
