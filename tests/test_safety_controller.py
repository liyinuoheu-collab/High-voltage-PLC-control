import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.fault_detection import FaultEvent, FaultLevel  # noqa: E402
from drive_board_monitor.safety_controller import SafetyController  # noqa: E402


def arc_event():
    return FaultEvent(
        FaultLevel.ARC_SUSPECT,
        "sudden_drop",
        "P2P_GAP_SUSPECT",
        "wall",
        100,
        6500,
        4500,
        1,
        0,
    )


class SafetyControllerTests(unittest.TestCase):
    def test_auto_stop_defaults_on_and_sends_once(self):
        controller = SafetyController()
        self.assertTrue(controller.suspect_auto_stop_enabled)
        self.assertTrue(controller.handle(arc_event()).send_fault_stop)
        self.assertFalse(controller.handle(arc_event()).send_fault_stop)

    def test_disabled_mode_alerts_and_logs_without_stopping(self):
        controller = SafetyController()
        controller.set_enabled(False, board_idle=True, confirmed=True)
        action = controller.handle(arc_event())
        self.assertTrue(action.log)
        self.assertTrue(action.alert)
        self.assertFalse(action.send_fault_stop)

    def test_disable_requires_idle_and_confirmation(self):
        controller = SafetyController()
        with self.assertRaises(PermissionError):
            controller.set_enabled(False, board_idle=False, confirmed=True)
        with self.assertRaises(PermissionError):
            controller.set_enabled(False, board_idle=True, confirmed=False)


if __name__ == "__main__":
    unittest.main()
