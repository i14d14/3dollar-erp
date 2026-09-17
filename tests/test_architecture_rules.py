import unittest
from tools.check_boundaries import run_checks

class TestArchitectureBoundaries(unittest.TestCase):
    def test_layer_boundaries(self):
        exit_code = run_checks()
        self.assertEqual(exit_code, 0, "Architecture boundary violations detected!")

    def test_default_event_bus_forbidden_check(self):
        from tools.check_boundaries import SRC_ROOT, check_file
        dummy_service_path = SRC_ROOT / "core" / "services" / "_dummy_test_check.py"
        try:
            with open(dummy_service_path, "w", encoding="utf-8") as f:
                f.write("from src.shared.event_bus import default_event_bus\n")
            violations = check_file(dummy_service_path, ["extended_core", "channel_ui", "ai_wrapper"])
            self.assertTrue(any("default_event_bus" in v for v in violations), "Should catch default_event_bus violation")
        finally:
            if dummy_service_path.exists():
                dummy_service_path.unlink()


if __name__ == "__main__":
    unittest.main()
