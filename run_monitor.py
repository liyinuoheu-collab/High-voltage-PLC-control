from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from drive_board_monitor.app import main


if __name__ == "__main__":
    raise SystemExit(main())
