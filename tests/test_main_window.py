import os
import json
import sys
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from PySide6.QtWidgets import QApplication  # noqa: E402

from drive_board_monitor.main_window import MainWindow, format_run_duration  # noqa: E402
from drive_board_monitor.models import ReceivedSerialLine  # noqa: E402


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_has_collapsed_v6_controls_and_defaults_to_30_second_view(self):
        window = MainWindow(auto_refresh_ports=False)
        self.assertIn("Donut-HASEL", window.windowTitle())
        self.assertIn("Microsoft YaHei", window.font().family())
        self.assertIn("双向", window.link_mode_label.text())
        self.assertFalse(window.control_panel.expanded)
        self.assertFalse(window.diagnostic_panel.expanded)
        self.assertEqual(window.window_seconds_box.currentText(), "30 s")
        self.assertFalse(window.stop_record_button.isEnabled())
        window.close()

    def test_telemetry_updates_cards_without_boot_event(self):
        window = MainWindow(auto_refresh_ports=False)
        raw = (
            b"D,v=3,s=5,t=100,r=2,m=4,st=6,p=-1,c=0,"
            b"cmd=0,adc=200,hv=1000,clr=1\r\n"
        )
        window.handle_received_line(ReceivedSerialLine(raw, "wall", 1_000_000_000))
        self.assertEqual(window.mode_value.text(), "1.6 Hz")
        self.assertEqual(window.state_value.text(), "15 s 恢复")
        self.assertEqual(window.run_value.text(), "2")
        self.assertEqual(window.clear_value.text(), "开启")
        self.assertEqual(window.duration_value.text(), "20 s（V3 默认）")
        self.assertIn("1.000 kV", window.feedback_value.text())
        window.close()

    def test_v4_telemetry_updates_finite_duration_card(self):
        window = MainWindow(auto_refresh_ports=False)
        raw = (
            b"D,v=4,s=5,t=100,r=2,m=4,st=2,p=1,c=0,"
            b"cmd=7000,adc=200,hv=6500,clr=1,dur=60000\r\n"
        )
        window.handle_received_line(ReceivedSerialLine(raw, "wall", 1_000_000_000))
        self.assertEqual(window.duration_value.text(), "60 s")
        window.close()

    def test_v4_telemetry_updates_unlimited_duration_card(self):
        window = MainWindow(auto_refresh_ports=False)
        raw = (
            b"D,v=4,s=5,t=100,r=2,m=4,st=2,p=1,c=0,"
            b"cmd=7000,adc=200,hv=6500,clr=1,dur=0\r\n"
        )
        window.handle_received_line(ReceivedSerialLine(raw, "wall", 1_000_000_000))
        self.assertEqual(window.duration_value.text(), "持续运行 · 按 CH 结束")
        window.close()

    def test_duration_formatter(self):
        self.assertEqual(format_run_duration(10000), "10 s")
        self.assertEqual(format_run_duration(0), "持续运行 · 按 CH 结束")

    def test_recording_metadata_uses_latest_v4_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            window = MainWindow(auto_refresh_ports=False)
            window._connected = True
            window.port_box.addItem("COM7", "COM7")
            window.output_dir_edit.setText(temp_dir)
            raw = (
                b"D,v=4,s=5,t=100,r=2,m=4,st=0,p=-1,c=0,"
                b"cmd=0,adc=0,hv=0,clr=1,dur=60000\r\n"
            )
            window.handle_received_line(
                ReceivedSerialLine(raw, "2026-07-21T12:00:00+08:00", 1)
            )
            window.start_recording()
            session_dir = window.controller.session_dir
            window.stop_recording()
            metadata = json.loads(
                (session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["protocol_version"], 4)
            self.assertEqual(metadata["selected_run_duration_ms"], 60000)
            self.assertFalse(metadata["duration_inferred"])
            window.close()

    def test_recording_metadata_before_first_frame_falls_back_to_v3(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            window = MainWindow(auto_refresh_ports=False)
            window._connected = True
            window.port_box.addItem("COM7", "COM7")
            window.output_dir_edit.setText(temp_dir)
            window.start_recording()
            session_dir = window.controller.session_dir
            window.stop_recording()
            metadata = json.loads(
                (session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["protocol_version"], 3)
            self.assertEqual(metadata["selected_run_duration_ms"], 20000)
            self.assertTrue(metadata["duration_inferred"])
            window.close()

    def test_disconnect_event_gets_real_monotonic_timestamp(self):
        window = MainWindow(auto_refresh_ports=False)

        class Controller:
            def __init__(self):
                self.received = None
                self.is_recording = False

            def connection_lost(self, detail, wall, monotonic_ns):
                self.received = (detail, wall, monotonic_ns)
                return None

        controller = Controller()
        window.controller = controller
        window._on_disconnected("cable removed")
        self.assertEqual(controller.received[0], "cable removed")
        self.assertGreater(controller.received[2], 0)
        window.close()


if __name__ == "__main__":
    unittest.main()
