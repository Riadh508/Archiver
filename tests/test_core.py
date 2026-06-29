"""Unit tests for core.py — using unittest (stdlib)"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import arch.config as cfg

from arch import core


class TestCore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="arch_core_"))
        cls._saved = {k: getattr(cfg, k) for k in ("DB_PATH","LOG_PATH","DATA_DIR","ARCHIVES_DIR","KEY_PATH")}
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

    def setUp(self):
        conn = core._get_conn()
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM archives")
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM settings")
        conn.execute("DELETE FROM licenses")
        conn.execute("DELETE FROM license_activations")
        conn.execute("DELETE FROM backups")
        conn.commit()

    def test_add_archive(self):
        aid = core.add_archive("test1", "/tmp/test.zip", "zip", 100, 3,
                               checksum="abc", notes="testing")
        self.assertGreater(aid, 0)
        arch = core.get_archive(aid)
        self.assertIsNotNone(arch)
        self.assertEqual(arch.name, "test1")
        self.assertEqual(arch.format, "zip")
        self.assertEqual(arch.size_bytes, 100)
        self.assertEqual(arch.file_count, 3)
        self.assertEqual(arch.checksum, "abc")
        self.assertEqual(arch.notes, "testing")
        self.assertFalse(arch.is_deleted)

    def test_add_and_list_files(self):
        aid = core.add_archive("file_test", "/tmp/f.zip", "zip", 0, 0)
        files = [
            ("a.txt", "dir/a.txt", 10, None),
            ("b.txt", "b.txt", 20, "chk_b"),
        ]
        core.add_files(aid, files)
        flist = core.list_files(aid)
        self.assertEqual(len(flist), 2)
        self.assertEqual(flist[0].name, "a.txt")
        self.assertEqual(flist[0].size_bytes, 10)
        self.assertEqual(flist[1].checksum, "chk_b")

        arch = core.get_archive(aid)
        self.assertEqual(arch.file_count, 2)

    def test_get_archive_not_found(self):
        self.assertIsNone(core.get_archive(9999))

    def test_soft_delete_and_restore(self):
        aid = core.add_archive("del_test", "/tmp/d.zip", "zip", 0, 0)
        self.assertTrue(core.soft_delete_archive(aid))
        self.assertIsNone(core.get_archive(aid))
        self.assertTrue(core.restore_archive(aid))
        self.assertIsNotNone(core.get_archive(aid))

    def test_prune(self):
        aid = core.add_archive("prune_me", "/tmp/p.zip", "zip", 0, 0)
        core.soft_delete_archive(aid)
        count = core.prune_archives()
        self.assertGreaterEqual(count, 1)

    def test_search_files(self):
        aid = core.add_archive("search_test", "/tmp/s.zip", "zip", 0, 0)
        core.add_files(aid, [("secret.txt", "secret.txt", 5, None)])
        results = core.search_files("secret")
        self.assertEqual(len(results), 1)
        arch_rec, file_rec = results[0]
        self.assertEqual(arch_rec.name, "search_test")
        self.assertEqual(file_rec.name, "secret.txt")

    def test_search_no_results(self):
        results = core.search_files("zzzznothing")
        self.assertEqual(len(results), 0)

    def test_update_size(self):
        aid = core.add_archive("size_test", "/tmp/sz.zip", "zip", 0, 0)
        core.update_archive_size(aid, 5000)
        arch = core.get_archive(aid)
        self.assertEqual(arch.size_bytes, 5000)

    def test_export_import(self):
        export_path = self._tmp / "exported.db"
        core.export_db(str(export_path))
        self.assertTrue(export_path.exists())
        conn = sqlite3.connect(str(export_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        names = [r[0] for r in tables]
        self.assertIn("archives", names)
        self.assertIn("files", names)

    # ─── Settings ──────────────────────────────────────────────────────────

    def test_set_get_setting(self):
        core.set_setting("test_key", "test_value")
        self.assertEqual(core.get_setting("test_key"), "test_value")
        self.assertIsNone(core.get_setting("nonexistent"))
        self.assertEqual(core.get_setting("nonexistent", "def"), "def")

    def test_get_all_settings(self):
        core.set_setting("k1", "v1")
        core.set_setting("k2", "v2")
        s = core.get_all_settings()
        self.assertIn("k1", s)
        self.assertIn("k2", s)
        self.assertEqual(s["k1"], "v1")

    # ─── Users ─────────────────────────────────────────────────────────────

    def test_update_user(self):
        uid = core.add_user("update_test", "pass123", role="user")
        self.assertIsNotNone(uid)
        ok = core.update_user(uid, full_name="Updated Name")
        self.assertTrue(ok)
        users = core.list_users()
        u = next((x for x in users if x["id"] == uid), None)
        self.assertIsNotNone(u)
        self.assertEqual(u["full_name"], "Updated Name")

    def test_change_password(self):
        uid = core.add_user("pw_test", "oldpass")
        self.assertIsNotNone(uid)
        ok = core.change_user_password(uid, "newpass1234")
        self.assertTrue(ok)
        self.assertIsNotNone(core.authenticate_user("pw_test", "newpass1234"))
        self.assertIsNone(core.authenticate_user("pw_test", "oldpass"))

    def test_change_password_too_short(self):
        uid = core.add_user("pw_short", "validpass")
        self.assertIsNotNone(uid)
        ok = core.change_user_password(uid, "ab")
        self.assertFalse(ok)

if __name__ == "__main__":
    unittest.main()
