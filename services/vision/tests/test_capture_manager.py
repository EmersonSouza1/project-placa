import unittest
from dock_vision.capture_manager import CaptureManager, capture_manager_config

class CaptureManagerTests(unittest.TestCase):
    def test_configuration(self):
        self.assertEqual(capture_manager_config("5","150"),(5,0.15))
        for values in (("0","1"),("21","1"),("x","1"),("1","-1")):
            with self.assertRaises(ValueError): capture_manager_config(*values)
    def test_limit_interval_and_identity(self):
        manager=CaptureManager(2,0.15)
        self.assertTrue(manager.add("visit",7,1.0,"a"))
        self.assertFalse(manager.add("visit",7,1.1,"b"))
        self.assertTrue(manager.add("visit",7,1.2,"b"))
        self.assertFalse(manager.add("visit",7,2.0,"c"))
        with self.assertRaises(ValueError): manager.add("visit",8,3.0,"x")
        self.assertEqual(manager.pop("visit"),["a","b"])
    def test_release_removes_finished_visit_memory(self):
        manager=CaptureManager(2,0)
        manager.add("finished",1,0,object())
        manager.add("active",2,0,object())
        manager.release_inactive({"active"})
        self.assertEqual(set(manager.batches),{"active"})
if __name__=="__main__": unittest.main()
