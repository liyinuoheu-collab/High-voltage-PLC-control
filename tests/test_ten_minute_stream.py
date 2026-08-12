import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.models import ReceivedSerialLine  # noqa: E402
from drive_board_monitor.session import SessionController  # noqa: E402


class TenMinuteStreamTests(unittest.TestCase):
    def test_50_hz_ten_minute_equivalent_stream_stays_lossless_and_bounded(self):
        frame_count = 50 * 60 * 10
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = SessionController(window_seconds=30.0)
            controller.start_recording(Path(temp_dir), {"test": "ten-minute-equivalent"})
            for sequence in range(frame_count):
                tick = sequence * 20
                phase = (tick // 312) % 64
                raw = (
                    f"D,v=3,s={sequence},t={tick},r=1,m=4,st=2,p={phase},"
                    f"c={(phase // 2) + 1},cmd={7000 if phase % 2 else 0},"
                    "adc=1400,hv=7001,clr=1\r\n"
                ).encode()
                controller.process(
                    ReceivedSerialLine(raw, f"wall-{tick}", tick * 1_000_000)
                )
            controller.process(
                ReceivedSerialLine(b"damaged\xff\r\n", "wall-end", 600_000_000_000)
            )
            session_dir = controller.stop_recording("manual")

            metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["telemetry_rows"], frame_count)
            self.assertEqual(metadata["lost_frames"], 0)
            self.assertEqual(metadata["unknown_lines"], 1)
            self.assertLessEqual(len(controller.plot_buffer.snapshot().time_s), 1501)
            self.assertGreater((session_dir / "serial_raw.log").stat().st_size, 1_000_000)


if __name__ == "__main__":
    unittest.main()
