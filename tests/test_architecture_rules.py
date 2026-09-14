import unittest
from tools.check_boundaries import run_checks

class TestArchitectureBoundaries(unittest.TestCase):
    def test_layer_boundaries(self):
        exit_code = run_checks()
        self.assertEqual(exit_code, 0, "Architecture boundary violations detected!")

if __name__ == "__main__":
    unittest.main()
