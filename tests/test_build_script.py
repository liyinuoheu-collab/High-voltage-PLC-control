import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildScriptTests(unittest.TestCase):
    def test_windows_build_uses_short_external_work_and_dist_paths(self):
        script = (ROOT / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("DonutHASELMonitorBuild", script)
        self.assertIn('$distDir = Join-Path $OutputRoot "dist"', script)
        self.assertIn('$workDir = Join-Path $OutputRoot "work"', script)
        self.assertIn('--specpath $specDir', script)
        self.assertIn('--distpath $distDir', script)
        self.assertIn('--workpath $workDir', script)

    def test_v3_version_build_name_and_operator_guide(self):
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        script = (ROOT / "build_exe.ps1").read_text(encoding="utf-8")
        guide = ROOT / "docs" / "UPPER_COMPUTER_V3_GUIDE.md"
        self.assertIn('version = "3.0.0"', project)
        self.assertIn("Donut-HASEL-Drive-Monitor-V3", script)
        self.assertIn("--onefile", script)
        self.assertTrue(guide.exists())
        text = guide.read_text(encoding="utf-8")
        for required in (
            "PB6",
            "PB7",
            "不要连接 USB-TTL 的 VCC",
            "Vcmd",
            "Vreal",
            "LEFT",
            "RIGHT",
            "simple_export.csv",
            "板端硬保护",
            "疑似击穿自动停机",
            "解锁不会自动启动",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
