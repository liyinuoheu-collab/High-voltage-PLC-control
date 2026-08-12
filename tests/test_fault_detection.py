import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.fault_detection import FaultDetector, FaultLevel  # noqa: E402
from drive_board_monitor.protocol import parse_serial_line  # noqa: E402


def sample(
    tick,
    real,
    *,
    command=6500,
    left=1,
    right=1,
    stable=1,
    waveform=1,
    run=1,
):
    raw = (
        f"D,v=6,seq={tick // 20},t_ms={tick},run={run},wave={waveform},"
        f"mode=2,state=2,route=1,left={left},right={right},v_set=6500,"
        f"v_cmd={command},v_real={real},adc_mv={real // 5},period_ms=2500,"
        "duty=50,phase_deg=180,duration_ms=20000,clear=1,cycle=4,"
        f"fault=0,locked=0,stable={stable},hard_protect=1\r\n"
    ).encode()
    return parse_serial_line(raw, f"wall-{tick}", tick * 1_000_000).telemetry


class FaultDetectorTests(unittest.TestCase):
    def test_normal_tracking_and_switching_edges_are_not_arc_suspects(self):
        detector = FaultDetector()
        events = []
        for item in (
            sample(0, 6300),
            sample(20, 6250),
            sample(40, 0, command=0, left=0, right=0, stable=0),
            sample(60, 0, command=0, left=0, right=0, stable=1),
        ):
            event = detector.observe(item)
            if event:
                events.append(event)
        self.assertFalse([e for e in events if e.level is FaultLevel.ARC_SUSPECT])

    def test_sudden_drop_is_suspected_and_route_classifies_location(self):
        detector = FaultDetector()
        detector.observe(sample(0, 6400, left=1, right=0))
        detector.observe(sample(20, 6350, left=1, right=0))
        event = detector.observe(sample(40, 4700, left=1, right=0))
        self.assertIsNotNone(event)
        self.assertIs(event.level, FaultLevel.ARC_SUSPECT)
        self.assertEqual(event.reason, "sudden_drop")
        self.assertEqual(event.classification, "P2P_GAP_SUSPECT")

    def test_long_low_tracking_is_warning_not_arc(self):
        detector = FaultDetector()
        events = []
        for tick in range(0, 260, 20):
            event = detector.observe(sample(tick, 4000))
            if event is not None:
                events.append(event)
        event = events[-1]
        self.assertIsNotNone(event)
        self.assertIs(event.level, FaultLevel.TRACKING_WARN)
        self.assertEqual(event.classification, "HV_PATH_SUSPECT")

    def test_detector_resets_on_run_change(self):
        detector = FaultDetector()
        detector.observe(sample(0, 6400, run=1))
        self.assertIsNone(detector.observe(sample(20, 3000, run=2)))


if __name__ == "__main__":
    unittest.main()
