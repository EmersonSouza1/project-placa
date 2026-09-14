import unittest
from dock_vision.motion import MotionDetector, motion_config
class Image:
    def __init__(self, value, size=100): self.value, self.size = value, size
class Cv:
    COLOR_BGR2GRAY=1; THRESH_BINARY=2
    cvtColor=staticmethod(lambda frame,_: frame)
    GaussianBlur=staticmethod(lambda frame,*_: frame)
    absdiff=staticmethod(lambda old,new: Image(abs(new.value-old.value),new.size))
    threshold=staticmethod(lambda diff,threshold,*_: (threshold,Image(diff.size if diff.value>threshold else 0,diff.size)))
    countNonZero=staticmethod(lambda image:image.value)
class Tests(unittest.TestCase):
    def test_config(self):
        self.assertEqual(motion_config("true","0.02"),(True,0.02))
        for values in (("yes","0.02"),("true","0"),("true","1.1"),("true","x")):
            with self.assertRaises(ValueError): motion_config(*values)
    def test_static_and_changed_roi(self):
        detector=MotionDetector(Cv,0.02)
        self.assertTrue(detector.has_motion(Image(10)))
        self.assertFalse(detector.has_motion(Image(10)))
        self.assertTrue(detector.has_motion(Image(50)))
if __name__=="__main__": unittest.main()
