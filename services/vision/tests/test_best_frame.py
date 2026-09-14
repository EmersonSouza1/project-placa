import unittest
from types import SimpleNamespace
from dock_vision.best_frame import BestFrameSelector

class Variance:
    def __init__(self,value): self.value=value
    def var(self): return self.value
class Cv:
    COLOR_BGR2GRAY=1; CV_64F=2
    cvtColor=staticmethod(lambda image,_:image)
    Laplacian=staticmethod(lambda image,_:Variance(image))
def candidate(sharpness,confidence,area):
    return SimpleNamespace(image=sharpness,detector_confidence=confidence,relative_area=area)
class BestFrameTests(unittest.TestCase):
    def test_selects_highest_deterministic_score(self):
        selector=BestFrameSelector(Cv)
        weak=candidate(10,0.5,0.01); strong=candidate(300,0.9,0.04)
        self.assertIs(selector.select([weak,strong]),strong)
    def test_empty_and_stable_tie(self):
        selector=BestFrameSelector(Cv)
        first=candidate(100,0.8,0.03); second=candidate(100,0.8,0.03)
        self.assertIsNone(selector.select([]))
        self.assertIs(selector.select([first,second]),first)
    def test_weights_are_validated(self):
        with self.assertRaises(ValueError): BestFrameSelector(Cv,0.5,0.5,0.5)
if __name__=="__main__": unittest.main()
