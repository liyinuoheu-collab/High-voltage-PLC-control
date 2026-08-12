import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.models import ReceivedSerialLine  # noqa: E402
from drive_board_monitor.session import SessionController  # noqa: E402


def line(sequence, tick, mode=2, state=2, phase=1):
    raw = (
        f"D,v=3,s={sequence},t={tick},r=1,m={mode},st={state},p={phase},c=1,"
        "cmd=7000,adc=1400,hv=7001,clr=0\r\n"
    ).encode()
    return ReceivedSerialLine(raw, f"wall-{tick}", tick * 1_000_000)


class SessionControllerTests(unittest.TestCase):
    def test_first_frame_recovers_mode_and_state_without_boot_line(self):
        controller = SessionController()
        result = controller.process(line(5, 100, mode=4, state=6, phase=-1))
        self.assertEqual(result.kind, "telemetry")
        self.assertEqual(controller.latest.mode_name, "1.6 Hz")
        self.assertEqual(controller.latest.state_name, "15 s 恢复")

    def test_complete_state_does_not_stop_manual_recording(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = SessionController()
            controller.start_recording(Path(temp_dir), {"port": "COM7", "baud": 115200})
            controller.process(line(1, 20, state=7, phase=-1))
            self.assertTrue(controller.is_recording)
            controller.process(line(2, 40, state=0, phase=-1))
            session_dir = controller.stop_recording("manual")
            metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["telemetry_rows"], 2)
            self.assertEqual(metadata["end_reason"], "manual")

    def test_gaps_and_restarts_become_events_and_gap_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = SessionController()
            controller.start_recording(Path(temp_dir), {})
            controller.process(line(10, 100))
            controller.process(line(13, 120))
            controller.process(line(0, 5))
            session_dir = controller.stop_recording("manual")
            with (session_dir / "events.csv").open(encoding="utf-8", newline="") as handle:
                event_types = [row["event_type"] for row in csv.DictReader(handle)]
            self.assertIn("FRAME_GAP", event_types)
            self.assertIn("BOARD_RESTART", event_types)
            metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["lost_frames"], 2)

    def test_connection_loss_closes_active_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = SessionController()
            controller.start_recording(Path(temp_dir), {})
            session_dir = controller.connection_lost("cable removed", "wall", 1)
            self.assertFalse(controller.is_recording)
            metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["end_reason"], "serial_disconnected")


if __name__ == "__main__":
    unittest.main()
