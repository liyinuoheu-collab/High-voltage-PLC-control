"""Serial discovery and read-only line acquisition, independent of Qt."""

from __future__ import annotations

import time
import threading
from datetime import datetime
from typing import Callable, Iterable

from .models import ReceivedSerialLine
from .commands import BoardCommand


def _default_port_provider() -> Iterable:
    from serial.tools import list_ports

    return list_ports.comports()


def list_serial_ports(provider: Callable[[], Iterable] | None = None) -> list[tuple[str, str]]:
    provider = provider or _default_port_provider
    result = [(item.device, item.description or "") for item in provider()]
    return sorted(result, key=lambda item: item[0])


def _default_serial_factory(**kwargs):
    import serial

    return serial.Serial(**kwargs)


class SerialLineReader:
    def __init__(
        self,
        serial_factory: Callable | None = None,
        wall_clock: Callable[[], str] | None = None,
        monotonic_clock: Callable[[], int] | None = None,
    ) -> None:
        self._factory = serial_factory or _default_serial_factory
        self._wall_clock = wall_clock or (
            lambda: datetime.now().astimezone().isoformat(timespec="microseconds")
        )
        self._monotonic_clock = monotonic_clock or time.monotonic_ns
        self._port = None
        self._io_lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return self._port is not None

    def connect(self, port: str, baudrate: int = 115200) -> None:
        if self._port is not None:
            self.disconnect()
        self._port = self._factory(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.1,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def read_once(self) -> ReceivedSerialLine | None:
        if self._port is None:
            raise RuntimeError("serial port is not connected")
        with self._io_lock:
            raw = self._port.readline()
        if not raw:
            return None
        return ReceivedSerialLine(raw, self._wall_clock(), self._monotonic_clock())

    def write_command(self, command: BoardCommand) -> None:
        if self._port is None:
            raise ConnectionError("board is not connected")
        with self._io_lock:
            self._port.write(command.wire)
            self._port.flush()

    def disconnect(self) -> None:
        with self._io_lock:
            if self._port is not None:
                self._port.close()
                self._port = None


try:
    from PySide6.QtCore import QObject, Signal, Slot

    class QtSerialWorker(QObject):
        line_received = Signal(object)
        connected = Signal()
        disconnected = Signal(str)
        command_failed = Signal(str)
        finished = Signal()

        def __init__(self, port: str, baudrate: int = 115200) -> None:
            super().__init__()
            self._port_name = port
            self._baudrate = baudrate
            self._reader = SerialLineReader()
            self._stop_requested = False

        @Slot()
        def run(self) -> None:
            try:
                self._reader.connect(self._port_name, self._baudrate)
                self.connected.emit()
                while not self._stop_requested:
                    received = self._reader.read_once()
                    if received is not None:
                        self.line_received.emit(received)
            except Exception as exc:  # Serial exceptions vary by backend.
                if not self._stop_requested:
                    self.disconnected.emit(str(exc))
            finally:
                self._reader.disconnect()
                self.finished.emit()

        @Slot()
        def request_stop(self) -> None:
            self._stop_requested = True

        @Slot(object)
        def write_command(self, command: BoardCommand) -> None:
            try:
                self._reader.write_command(command)
            except Exception as exc:
                self.command_failed.emit(str(exc))

except ImportError:  # Core parser/recorder remain usable without the GUI extra.
    QtSerialWorker = None
