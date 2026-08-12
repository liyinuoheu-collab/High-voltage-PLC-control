import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from PySide6.QtWidgets import QApplication  # noqa: E402
from drive_board_monitor.commands import BoardCommand  # noqa: E402
from drive_board_monitor.main_window import MainWindow  # noqa: E402
from drive_board_monitor.models import ReceivedSerialLine  # noqa: E402


def frame(seq, tick, *, state=0, locked=0, real=0, command=0, left=0, right=0):
    route = 0 if not (left or right) else (1 if left == right else 2)
    raw = (
        f"D,v=6,seq={seq},t_ms={tick},run=1,wave=1,mode=2,state={state},"
        f"route={route},left={left},right={right},v_set=6500,v_cmd={command},"
        f"v_real={real},adc_mv={real // 5},period_ms=2500,duty=50,"
        "phase_deg=180,duration_ms=20000,clear=1,cycle=1,fault=0,"
        f"locked={locked},stable=1,hard_protect=1\r\n"
    ).encode()
    return ReceivedSerialLine(raw, f"2026-07-29T14:05:{tick // 1000:02d}+08:00", tick * 1_000_000)


class FakeWorker:
    def __init__(self):
        self.commands = []

    def write_command(self, command):
        self.commands.append(command.wire)


class V6ControlFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_board_state_controls_start_lock_and_unlock_without_restart(self):
        window = MainWindow(auto_refresh_ports=False)
        worker = FakeWorker()
        window._serial_worker = worker
        window._connected = True
        window.handle_received_line(frame(1, 20))
        self.assertTrue(window.start_button.isEnabled())
        window._send_command(BoardCommand.set_voltage(6500))
        self.assertEqual(worker.commands[-1], b"SET,V=6500\r\n")
        window._send_command(BoardCommand.start())
        self.assertEqual(worker.commands[-1], b"START\r\n")

        window.handle_received_line(frame(2, 40, state=8, locked=1))
        self.assertFalse(window.start_button.isEnabled())
        self.assertTrue(window.unlock_button.isEnabled())
        window._unlock_confirmed()
        self.assertEqual(worker.commands[-1], b"UNLOCK\r\n")
        self.assertNotEqual(worker.commands[-1], b"START\r\n")
        window.close()

    def test_suspected_arc_sends_fault_stop_only_once_when_enabled(self):
        window = MainWindow(auto_refresh_ports=False)
        worker = FakeWorker()
        window._serial_worker = worker
        window._connected = True
        window.handle_received_line(
            frame(1, 20, state=2, real=6400, command=6500, left=1, right=0)
        )
        window.handle_received_line(
            frame(2, 40, state=2, real=4500, command=6500, left=1, right=0)
        )
        window.handle_received_line(
            frame(3, 60, state=2, real=3000, command=6500, left=1, right=0)
        )
        self.assertEqual(worker.commands.count(b"FAULT,PC_ARC\r\n"), 1)
        window.close()


if __name__ == "__main__":
    unittest.main()
