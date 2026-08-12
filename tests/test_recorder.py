import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from drive_board_monitor.protocol import parse_serial_line  # noqa: E402
from drive_board_monitor.recorder import SessionRecorder  # noqa: E402


class RecorderTests(unittest.TestCase):
    def test_session_writes_exact_raw_bytes_and_structured_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir), {"port": "COM7", "baud": 115200})
            raw = (
                b"D,v=3,s=1,t=20,r=1,m=2,st=2,p=1,c=1,"
                b"cmd=7000,adc=1400,hv=7001,clr=0\r\n"
            )
            parsed = parse_serial_line(raw, "2026-07-20T20:00:00+08:00", 100)
            recorder.record(raw, parsed)
            recorder.stop("manual")

            self.assertEqual((recorder.session_dir / "serial_raw.log").read_bytes(), raw)
            with (recorder.session_dir / "telemetry_raw.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["pc_wall_time_iso"], "2026-07-20T20:00:00+08:00")
            self.assertEqual(rows[0]["pc_monotonic_ns"], "100")
            self.assertEqual(rows[0]["feedback_hv_magnitude_v"], "7001")
            self.assertEqual(rows[0]["feedback_polarity_measured"], "0")
            metadata = json.loads(
                (recorder.session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["end_reason"], "manual")
            self.assertEqual(metadata["telemetry_rows"], 1)
            self.assertEqual(metadata["baud"], 115200)

    def test_bad_and_event_lines_are_preserved_in_event_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir), {"port": "COM8", "baud": 115200})
            lines = [
                b"STATE,run=1,t=40,COMPLETE\r\n",
                b"D,v=3,s=not-an-int\r\n",
                b"other\xff\r\n",
            ]
            for index, raw in enumerate(lines):
                recorder.record(raw, parse_serial_line(raw, f"wall-{index}", index))
            recorder.add_system_event("SERIAL_DISCONNECTED", "cable removed", "wall-3", 3)
            recorder.stop("serial_disconnected")

            with (recorder.session_dir / "events.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                [row["event_type"] for row in rows],
                ["STATE", "MALFORMED", "UNKNOWN", "SERIAL_DISCONNECTED"],
            )
            metadata = json.loads(
                (recorder.session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["parse_errors"], 1)
            self.assertEqual(metadata["unknown_lines"], 1)
            self.assertEqual(metadata["end_reason"], "serial_disconnected")

    def test_session_directories_are_unique_and_flush_is_public(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = SessionRecorder(Path(temp_dir), {})
            second = SessionRecorder(Path(temp_dir), {})
            self.assertNotEqual(first.session_dir, second.session_dir)
            first.flush()
            first.stop("manual")
            second.stop("manual")

    def test_v4_writes_duration_raw_metadata_and_simple_voltage_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir), {"port": "COM8", "baud": 115200})
            raw = (
                b"D,v=4,s=1,t=20,r=1,m=2,st=2,p=1,c=1,"
                b"cmd=7000,adc=1400,hv=7001,clr=0,dur=60000\r\n"
            )
            parsed = parse_serial_line(
                raw, "2026-07-21T10:58:27.715236+08:00", 100
            )
            recorder.record(raw, parsed)
            recorder.stop("manual")

            with (recorder.session_dir / "telemetry_raw.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                raw_rows = list(csv.DictReader(handle))
            self.assertEqual(raw_rows[0]["run_duration_ms"], "60000")
            self.assertEqual(raw_rows[0]["run_duration_inferred"], "0")

            with (recorder.session_dir / "simple_export.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                simple = csv.DictReader(handle)
                simple_rows = list(simple)
                self.assertEqual(
                    simple.fieldnames,
                    [
                        "电脑时间",
                        "实验阶段",
                        "设定电压_V",
                        "实际电压_V",
                        "相位_deg",
                        "左输出",
                        "右输出",
                        "故障码",
                    ],
                )
            self.assertEqual(len(simple_rows), 1)
            self.assertEqual(simple_rows[0]["电脑时间"], "10:58:27.715")
            self.assertEqual(simple_rows[0]["实验阶段"], "周期驱动")
            self.assertEqual(simple_rows[0]["设定电压_V"], "7000")
            self.assertEqual(simple_rows[0]["实际电压_V"], "7001")

            metadata = json.loads(
                (recorder.session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["selected_run_duration_ms"], 60000)
            self.assertFalse(metadata["duration_inferred"])
            self.assertEqual(metadata["gui_version"], "3.0.0")
            self.assertEqual(metadata["simple_export_status"], "ok")

    def test_simple_export_failure_does_not_break_raw_recording(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir), {"port": "COM8", "baud": 115200})

            def fail_simple_write(_item):
                raise OSError("simulated simple export failure")

            recorder._write_simple_row = fail_simple_write
            raw = (
                b"D,v=4,s=1,t=20,r=1,m=2,st=2,p=1,c=1,"
                b"cmd=7000,adc=1400,hv=7001,clr=0,dur=20000\r\n"
            )
            parsed = parse_serial_line(
                raw, "2026-07-21T10:58:27.715236+08:00", 100
            )
            recorder.record(raw, parsed)
            recorder.stop("manual")

            self.assertEqual((recorder.session_dir / "serial_raw.log").read_bytes(), raw)
            with (recorder.session_dir / "telemetry_raw.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)
            metadata = json.loads(
                (recorder.session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["telemetry_rows"], 1)
            self.assertEqual(metadata["simple_export_status"], "error")
            self.assertIn("simulated simple export failure", metadata["simple_export_error"])

    def test_v6_records_complete_snapshot_and_exactly_five_session_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(
                Path(temp_dir),
                {"port": "COM7", "baud": 115200, "suspect_auto_stop": True},
            )
            raw = (
                b"D,v=6,seq=12,t_ms=840,run=1,wave=1,mode=2,state=2,"
                b"route=2,left=1,right=0,v_set=6500,v_cmd=6500,v_real=6240,"
                b"adc_mv=1248,period_ms=2500,duty=50,phase_deg=180,"
                b"duration_ms=20000,clear=1,cycle=4,fault=0,locked=0,"
                b"stable=1,hard_protect=1\r\n"
            )
            recorder.record(
                raw,
                parse_serial_line(
                    raw, "2026-07-29T14:05:06.123456+08:00", 123456789
                ),
            )
            recorder.stop("manual")
            self.assertEqual(
                {path.name for path in recorder.session_dir.iterdir()},
                {
                    "serial_raw.log",
                    "telemetry_raw.csv",
                    "events.csv",
                    "simple_export.csv",
                    "metadata.json",
                },
            )
            with (recorder.session_dir / "telemetry_raw.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["pc_time_hms"], "14:05:06.123")
            self.assertEqual(row["vset_v"], "6500")
            self.assertEqual(row["phase_deg"], "180")
            self.assertEqual((row["left_state"], row["right_state"]), ("1", "0"))


if __name__ == "__main__":
    unittest.main()
