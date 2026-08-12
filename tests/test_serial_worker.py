import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.serial_worker import (  # noqa: E402
    SerialLineReader,
    list_serial_ports,
)


class FakePort:
    def __init__(self, lines):
        self.lines = list(lines)
        self.closed = False
        self.written = []
        self.flushed = False

    def readline(self):
        if not self.lines:
            return b""
        item = self.lines.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True

    def write(self, data):
        self.written.append(data)
        return len(data)

    def flush(self):
        self.flushed = True


class SerialWorkerTests(unittest.TestCase):
    def test_lists_ports_without_opening_them(self):
        class Port:
            def __init__(self, device, description):
                self.device = device
                self.description = description

        ports = list_serial_ports(lambda: [Port("COM7", "USB Serial"), Port("COM3", "STLink")])
        self.assertEqual(ports, [("COM3", "STLink"), ("COM7", "USB Serial")])

    def test_reader_opens_read_only_and_timestamps_at_receipt(self):
        opened = {}
        fake = FakePort([b"STATE,run=1,t=20,PREPARE\r\n"])

        def factory(**kwargs):
            opened.update(kwargs)
            return fake

        reader = SerialLineReader(
            serial_factory=factory,
            wall_clock=lambda: "wall-now",
            monotonic_clock=lambda: 123,
        )
        reader.connect("COM7", 115200)
        received = reader.read_once()
        self.assertEqual(opened["port"], "COM7")
        self.assertEqual(opened["baudrate"], 115200)
        self.assertNotIn("write", opened)
        self.assertEqual(received.raw, b"STATE,run=1,t=20,PREPARE\r\n")
        self.assertEqual(received.pc_wall_time_iso, "wall-now")
        self.assertEqual(received.pc_monotonic_ns, 123)
        reader.disconnect()
        self.assertTrue(fake.closed)

    def test_empty_timeout_is_not_a_line_and_disconnect_error_propagates(self):
        fake = FakePort([b"", OSError("cable removed")])
        reader = SerialLineReader(serial_factory=lambda **_: fake)
        reader.connect("COM7", 115200)
        self.assertIsNone(reader.read_once())
        with self.assertRaisesRegex(OSError, "cable removed"):
            reader.read_once()

    def test_reader_can_write_v6_command_on_same_serial_port(self):
        from drive_board_monitor.commands import BoardCommand

        fake = FakePort([])
        reader = SerialLineReader(serial_factory=lambda **_: fake)
        reader.connect("COM7", 115200)
        reader.write_command(BoardCommand.set_phase(90))
        self.assertEqual(fake.written, [b"SET,PHASE=90\r\n"])
        self.assertTrue(fake.flushed)


if __name__ == "__main__":
    unittest.main()
