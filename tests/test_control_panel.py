import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from PySide6.QtWidgets import QApplication  # noqa: E402
from drive_board_monitor.control_panel import ExperimentControlPanel  # noqa: E402


class ControlPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_control_panel_uses_firmware_supported_values(self):
        panel = ExperimentControlPanel()
        self.assertEqual(panel.voltage_values, [4000, 4500, 5000, 5500, 6000, 6500, 7000])
        self.assertEqual(panel.period_values, [5000, 2500, 1250, 625])
        self.assertEqual(panel.duty_values, [25, 50, 75])
        self.assertEqual(panel.phase_values, [0, 90, 180])
        self.assertEqual(panel.duration_values, [10000, 20000, 30000, 60000, 0])
        self.assertFalse(panel.expanded)
        panel.close()


if __name__ == "__main__":
    unittest.main()
