import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.protocol import (  # noqa: E402
    SequenceTracker,
    parse_serial_line,
)


class ProtocolTests(unittest.TestCase):
    def test_parses_protocol_v6_board_snapshot(self):
        parsed = parse_serial_line(
            b"D,v=6,seq=12,t_ms=840,run=1,wave=1,mode=2,state=2,"
            b"route=1,left=1,right=0,v_set=6500,v_cmd=6500,v_real=6240,"
            b"adc_mv=1248,period_ms=2500,duty=50,phase_deg=180,"
            b"duration_ms=20000,clear=1,cycle=4,fault=0,locked=0,"
            b"stable=1,hard_protect=1\r\n",
            "2026-07-29T14:05:06.123000+08:00",
            987654321,
        )
        self.assertEqual(parsed.kind, "telemetry")
        item = parsed.telemetry
        self.assertEqual(item.protocol_version, 6)
        self.assertEqual(item.sequence, 12)
        self.assertEqual(item.vset_v, 6500)
        self.assertEqual(item.command_voltage_v, 6500)
        self.assertEqual(item.feedback_hv_magnitude_v, 6240)
        self.assertEqual(item.period_ms, 2500)
        self.assertEqual(item.duty_pct, 50)
        self.assertEqual(item.phase_deg, 180)
        self.assertEqual((item.left_state, item.right_state), (1, 0))
        self.assertTrue(item.hard_protection_enabled)
        self.assertFalse(item.locked)

    def test_parses_v6_command_ack_and_error(self):
        ack = parse_serial_line(
            b"EVENT,run=1,CMD,ACK,SET\r\n", "wall", 1
        )
        error = parse_serial_line(
            b"EVENT,run=1,CMD,ERR,NOT_IDLE\r\n", "wall", 2
        )
        self.assertEqual(ack.kind, "ack")
        self.assertTrue(ack.ack.ok)
        self.assertEqual(ack.ack.command, "SET")
        self.assertEqual(error.kind, "ack")
        self.assertFalse(error.ack.ok)
        self.assertEqual(error.ack.reason, "NOT_IDLE")

    def test_parses_complete_telemetry_with_negative_phase(self):
        parsed = parse_serial_line(
            b"D,v=3,s=1234,t=24680,r=3,m=2,st=0,p=-1,c=0,"
            b"cmd=0,adc=1383,hv=6916,clr=0\r\n",
            "2026-07-20T20:00:00.123+08:00",
            987654321,
        )

        self.assertEqual(parsed.kind, "telemetry")
        self.assertEqual(parsed.telemetry.sequence, 1234)
        self.assertEqual(parsed.telemetry.phase, -1)
        self.assertEqual(parsed.telemetry.mode_name, "0.4 Hz")
        self.assertEqual(parsed.telemetry.state_name, "待机")
        self.assertEqual(parsed.telemetry.period_ms, 2500)
        self.assertEqual(parsed.telemetry.output_kind, "OFF")
        self.assertEqual(parsed.telemetry.feedback_signed_v, 0)

    def test_accepts_field_order_changes(self):
        parsed = parse_serial_line(
            b"D,hv=7001,adc=1400,cmd=7000,c=2,p=3,st=2,m=4,r=1,t=80,s=4,v=3,clr=1\n",
            "wall",
            10,
        )
        self.assertEqual(parsed.kind, "telemetry")
        self.assertEqual(parsed.telemetry.output_kind, "DRIVE_SYNC")
        self.assertEqual(parsed.telemetry.feedback_signed_v, 7001)

    def test_cancel_feedback_sign_is_derived_not_measured(self):
        parsed = parse_serial_line(
            b"D,v=3,s=5,t=100,r=1,m=1,st=4,p=-1,c=0,cmd=3000,adc=600,hv=3001,clr=1\n",
            "wall",
            20,
        )
        self.assertEqual(parsed.telemetry.output_kind, "CANCEL_SYNC")
        self.assertEqual(parsed.telemetry.feedback_signed_v, -3001)
        self.assertFalse(parsed.telemetry.feedback_polarity_measured)

    def test_v4_duration_is_parsed(self):
        parsed = parse_serial_line(
            b"D,v=4,s=1,t=20,r=1,m=2,st=0,p=-1,c=0,"
            b"cmd=0,adc=12,hv=63,clr=0,dur=60000\r\n",
            "2026-07-21T10:58:27.715+08:00",
            1,
        )
        self.assertEqual(parsed.kind, "telemetry")
        self.assertEqual(parsed.telemetry.run_duration_ms, 60000)
        self.assertFalse(parsed.telemetry.run_duration_inferred)

    def test_v4_unlimited_duration_is_zero(self):
        parsed = parse_serial_line(
            b"D,v=4,s=1,t=20,r=1,m=2,st=0,p=-1,c=0,"
            b"cmd=0,adc=12,hv=63,clr=0,dur=0\r\n",
            "wall",
            1,
        )
        self.assertEqual(parsed.telemetry.run_duration_ms, 0)
        self.assertFalse(parsed.telemetry.run_duration_inferred)

    def test_v3_falls_back_to_twenty_seconds(self):
        parsed = parse_serial_line(
            b"D,v=3,s=1,t=20,r=1,m=2,st=0,p=-1,c=0,"
            b"cmd=0,adc=12,hv=63,clr=0\r\n",
            "wall",
            1,
        )
        self.assertEqual(parsed.telemetry.run_duration_ms, 20000)
        self.assertTrue(parsed.telemetry.run_duration_inferred)

    def test_v4_missing_duration_is_malformed(self):
        parsed = parse_serial_line(
            b"D,v=4,s=1,t=20,r=1,m=2,st=0,p=-1,c=0,"
            b"cmd=0,adc=12,hv=63,clr=0\r\n",
            "wall",
            1,
        )
        self.assertEqual(parsed.kind, "malformed")
        self.assertIn("dur", parsed.error)

    def test_classifies_board_events_and_unknown_lines(self):
        event = parse_serial_line(b"STATE,run=2,t=42,RECOVERY_15S\r\n", "wall", 1)
        unknown = parse_serial_line(b"legacy diagnostic\xff\r\n", "wall", 2)
        self.assertEqual(event.kind, "event")
        self.assertEqual(event.event_type, "STATE")
        self.assertEqual(unknown.kind, "unknown")
        self.assertIn("\ufffd", unknown.text)

    def test_missing_or_noninteger_fields_are_malformed_not_dropped(self):
        missing = parse_serial_line(b"D,v=3,s=1\n", "wall", 1)
        bad = parse_serial_line(
            b"D,v=3,s=x,t=1,r=1,m=1,st=1,p=-1,c=0,cmd=0,adc=0,hv=0,clr=0\n",
            "wall",
            2,
        )
        self.assertEqual(missing.kind, "malformed")
        self.assertIn("missing", missing.error)
        self.assertEqual(bad.kind, "malformed")
        self.assertIn("integer", bad.error)

    def test_sequence_tracker_detects_gap_wrap_and_board_restart(self):
        tracker = SequenceTracker()
        self.assertEqual(tracker.observe(10, 100), [])
        self.assertEqual(tracker.observe(12, 120)[0].lost_frames, 1)
        tracker = SequenceTracker()
        tracker.observe(0xFFFFFFFF, 100)
        self.assertEqual(tracker.observe(0, 120), [])
        restart = tracker.observe(0, 5)
        self.assertEqual(restart[0].event_type, "BOARD_RESTART")


if __name__ == "__main__":
    unittest.main()
