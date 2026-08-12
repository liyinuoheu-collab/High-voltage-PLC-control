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


class V4EndToEndTests(unittest.TestCase):
    def test_mixed_v4_v3_stream_remains_complete_and_self_describing(self):
        frames = [
            b"D,v=4,s=1,t=20,r=0,m=2,st=0,p=-1,c=0,cmd=0,adc=0,hv=0,clr=0,dur=60000\r\n",
            b"D,v=4,s=2,t=40,r=1,m=2,st=2,p=1,c=1,cmd=7000,adc=1400,hv=7001,clr=0,dur=60000\r\n",
            b"D,v=4,s=3,t=60,r=1,m=2,st=6,p=-1,c=0,cmd=0,adc=100,hv=500,clr=0,dur=60000\r\n",
            b"D,v=3,s=4,t=80,r=1,m=2,st=0,p=-1,c=0,cmd=0,adc=20,hv=100,clr=0\r\n",
            b"D,v=4,s=5,t=100,r=1,m=2,st=0,p=-1,c=0,cmd=0,adc=0,hv=0,clr=0,dur=0\r\n",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            controller = SessionController()
            session_dir = controller.start_recording(
                Path(temp_dir), {"port": "SYNTHETIC", "baud": 115200}
            )
            for index, raw in enumerate(frames):
                controller.process(
                    ReceivedSerialLine(
                        raw,
                        f"2026-07-21T12:00:0{index}.123456+08:00",
                        1_000_000_000 + index * 20_000_000,
                    )
                )
            controller.stop_recording("synthetic_verification")

            self.assertEqual((session_dir / "serial_raw.log").read_bytes(), b"".join(frames))
            with (session_dir / "telemetry_raw.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                raw_rows = list(csv.DictReader(handle))
            with (session_dir / "simple_export.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                simple_reader = csv.DictReader(handle)
                self.assertEqual(
                    simple_reader.fieldnames,
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
                simple_rows = list(simple_reader)

            self.assertEqual(len(raw_rows), len(frames))
            self.assertEqual(len(simple_rows), len(frames))
            self.assertEqual(simple_rows[0]["电脑时间"], "12:00:00.123")
            self.assertEqual(raw_rows[3]["run_duration_ms"], "20000")
            self.assertEqual(raw_rows[3]["run_duration_inferred"], "1")

            metadata = json.loads(
                (session_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["selected_run_duration_ms"], 0)
            self.assertFalse(metadata["duration_inferred"])
            self.assertEqual(metadata["telemetry_rows"], len(frames))
            self.assertEqual(metadata["simple_export_status"], "ok")


if __name__ == "__main__":
    unittest.main()
