import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.commands import BoardCommand  # noqa: E402


class BoardCommandTests(unittest.TestCase):
    def test_encodes_actual_firmware_v6_commands(self):
        self.assertEqual(BoardCommand.set_voltage(6500).wire, b"SET,V=6500\r\n")
        self.assertEqual(
            BoardCommand.set_period_ms(2500).wire, b"SET,PERIOD_MS=2500\r\n"
        )
        self.assertEqual(BoardCommand.set_duty(50).wire, b"SET,DUTY=50\r\n")
        self.assertEqual(BoardCommand.set_phase(180).wire, b"SET,PHASE=180\r\n")
        self.assertEqual(
            BoardCommand.set_duration(0).wire, b"SET,DURATION_MS=0\r\n"
        )
        self.assertEqual(BoardCommand.set_waveform("HOLD").wire, b"SET,WAVE=HOLD\r\n")
        self.assertEqual(BoardCommand.fault_stop().wire, b"FAULT,PC_ARC\r\n")
        self.assertEqual(BoardCommand.unlock().wire, b"UNLOCK\r\n")

    def test_rejects_values_not_supported_by_board(self):
        for factory, value in (
            (BoardCommand.set_voltage, 4250),
            (BoardCommand.set_period_ms, 1000),
            (BoardCommand.set_duty, 60),
            (BoardCommand.set_phase, 45),
            (BoardCommand.set_duration, -1),
        ):
            with self.subTest(factory=factory.__name__, value=value):
                with self.assertRaises(ValueError):
                    factory(value)


if __name__ == "__main__":
    unittest.main()
