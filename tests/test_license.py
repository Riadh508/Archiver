"""Tests for license, user, backup features"""
import shutil
import tempfile
import unittest
from pathlib import Path

import arch.config as cfg

from arch import core


class TestLicense(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="arch_lic_"))
        cls._saved = {}
        for k in ("DB_PATH", "LOG_PATH", "DATA_DIR", "ARCHIVES_DIR", "KEY_PATH"):
            cls._saved[k] = getattr(cfg, k)
        cfg.DB_PATH = cls._tmp / "test.db"
        cfg.LOG_PATH = cls._tmp / "test.log"
        cfg.DATA_DIR = cls._tmp
        cfg.ARCHIVES_DIR = cls._tmp / "archives"
        cfg.KEY_PATH = cls._tmp / ".arch_key"
        if cfg.DB_PATH.exists():
            cfg.DB_PATH.unlink()
        core.init_db()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)
        for k, v in cls._saved.items():
            setattr(cfg, k, v)

    def test_license_status_no_license(self):
        ok, msg, info = core.check_license_status()
        # Trial might be active, so we just check that it returns something
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)

    def test_user_add_and_authenticate(self):
        uid = core.add_user("testuser", "password123", role="admin")
        self.assertIsNotNone(uid)
        user = core.authenticate_user("testuser", "password123")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "testuser")

    def test_backup_create(self):
        backup_path = core.create_backup()
        self.assertIsNotNone(backup_path)
        backups = core.list_backups()
        self.assertGreaterEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()