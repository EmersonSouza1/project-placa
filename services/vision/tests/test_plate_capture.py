import unittest
from dock_vision.plate_capture import PlateCapturePolicy, plate_capture_config

class PlateCapturePolicyTests(unittest.TestCase):
    def test_configuration(self):
        self.assertEqual(plate_capture_config("3", "10"), (3, 10.0))
        for values in (("0","10"),("101","10"),("x","10"),("3","0"),("3","nan"),("3","301")):
            with self.assertRaises(ValueError): plate_capture_config(*values)
    def test_capture_requires_visit_and_stops_on_consensus(self):
        policy=PlateCapturePolicy(3,10)
        self.assertFalse(policy.should_capture(None,0,False))
        self.assertTrue(policy.should_capture("visit",0,False))
        self.assertFalse(policy.should_capture("visit",1,True))
    def test_attempt_and_time_limits(self):
        policy=PlateCapturePolicy(2,5)
        self.assertTrue(policy.should_capture("visit",0,False))
        self.assertTrue(policy.should_capture("visit",1,False))
        self.assertFalse(policy.should_capture("visit",2,False))
        self.assertTrue(policy.should_capture("other",10,False))
        self.assertFalse(policy.should_capture("other",16,False))
    def test_inactive_visit_state_is_released(self):
        policy=PlateCapturePolicy(2,5)
        policy.should_capture("visit",0,False)
        policy.retain(set())
        self.assertEqual(policy.states,{})
if __name__=="__main__": unittest.main()
