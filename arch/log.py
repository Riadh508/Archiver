"""Async non-blocking logging via queue.Queue — writes to both file and stderr"""

import atexit
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}


class Logger:
    def __init__(self, path: Path, level: str = "INFO"):
        self.level = LEVELS.get(level, 1)
        self._path = path
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        atexit.register(self.flush)

    def _worker(self):
        path = self._path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
        while not self._stop.is_set():
            try:
                msg = self._queue.get(timeout=0.5)
                self._write(msg, path)
            except queue.Empty:
                continue
        while not self._queue.empty():
            self._write(self._queue.get_nowait(), path)

    def _write(self, msg: str, path: Path | None):
        sys.stderr.write(msg + "\n")
        if path:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except OSError:
                pass

    def _enqueue(self, level: str, msg: str):
        if LEVELS.get(level, 0) < self.level:
            return
        ts = datetime.now().isoformat()
        self._queue.put(f"{ts} [{level}] {msg}")

    def debug(self, msg: str):   self._enqueue("DEBUG", msg)
    def info(self, msg: str):    self._enqueue("INFO", msg)
    def warn(self, msg: str):    self._enqueue("WARN", msg)
    def error(self, msg: str):   self._enqueue("ERROR", msg)

    def flush(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)


_logger: Logger | None = None


def get(path: Path = None, level: str = "INFO") -> Logger:
    global _logger
    if _logger is None:
        _logger = Logger(path, level)
    return _logger
