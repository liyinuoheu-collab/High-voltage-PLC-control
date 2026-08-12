import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.buffer import RollingPlotBuffer  # noqa: E402


class BufferTests(unittest.TestCase):
    def test_window_and_max_points_are_bounded(self):
        buffer = RollingPlotBuffer(window_seconds=30.0, max_points=100)
        for index in range(200):
            buffer.append(index * 1_000_000_000, index, index * 2, -index)

        snapshot = buffer.snapshot()
        self.assertLessEqual(len(snapshot.time_s), 31)
        self.assertEqual(snapshot.command_v[-1], 199)

    def test_display_smoothing_does_not_change_stored_raw_values(self):
        buffer = RollingPlotBuffer(window_seconds=30.0, max_points=100)
        for index, value in enumerate((0, 9, 0)):
            buffer.append(index * 1_000_000_000, value, value, value)

        raw = buffer.snapshot(smoothing_points=1)
        smooth = buffer.snapshot(smoothing_points=3)
        self.assertEqual(raw.command_v, (0, 9, 0))
        self.assertEqual(smooth.command_v, (0.0, 3.0, 3.0))
        self.assertEqual(buffer.snapshot(smoothing_points=1).command_v, (0, 9, 0))

    def test_v6_snapshot_keeps_voltage_and_route_bands_separate(self):
        buffer = RollingPlotBuffer(window_seconds=30.0)
        buffer.append(1_000_000_000, 6500, 6200, 6200, 1, 0)
        snapshot = buffer.snapshot()
        self.assertEqual(snapshot.vcmd_v, (6500,))
        self.assertEqual(snapshot.vreal_v, (6200,))
        self.assertEqual(snapshot.left_state, (1,))
        self.assertEqual(snapshot.right_state, (0,))


if __name__ == "__main__":
    unittest.main()
