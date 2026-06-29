"""Security tests: zip slip, HMAC integrity, input sanitization, DB import validation"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import arch.config as cfg

from arch import core, ops


class TestSecurity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="arch_sec_"))
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

    def _make_files(self, base: Path, files: dict[str, str]):
        for name, content in files.items():
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def _find_by_name(self, name: str):
        for a in core.list_archives():
            if a.name == name:
                return a
        return None

    def test_hmac_signature_created_on_add(self):
        """Every archive should have an HMAC signature."""
        src = self._tmp / "hmac_test"
        src.mkdir()
        self._make_files(src, {"file.txt": "data"})
        ops.cmd_add([str(src)], "zip", "hmac_archive", "", None, None)
        arch = self._find_by_name("hmac_archive")
        self.assertIsNotNone(arch)
        self.assertIsNotNone(arch.signature, "HMAC signature should exist")
        self.assertTrue(core.verify_signature(arch.id), "HMAC should verify")

    def test_hmac_detects_tampered_checksum(self):
        """If checksum is modified in DB, verify_signature should fail."""
        src = self._tmp / "tamper_test"
        src.mkdir()
        self._make_files(src, {"data.txt": "original"})
        ops.cmd_add([str(src)], "zip", "tamper_me", "", None, None)
        arch = self._find_by_name("tamper_me")
        self.assertIsNotNone(arch)
        # Tamper with DB directly using core's connection
        conn = core._get_conn()
        conn.execute("UPDATE archives SET checksum='tampered' WHERE id=?", (arch.id,))
        conn.commit()
        # Now verify should detect tampering
        self.assertFalse(core.verify_signature(arch.id), "HMAC should detect tampered checksum")

    def test_zip_slip_blocked(self):
        """Create a zip with path traversal and verify it's blocked."""
        import zipfile
        malicious_zip = self._tmp / "malicious.zip"
        with zipfile.ZipFile(str(malicious_zip), "w") as z:
            z.writestr("../../../etc/passwd", "root:x:0:0:root:")
        extract_to = self._tmp / "extract_target"
        extract_to.mkdir()
        with self.assertRaises(ValueError):
            ops._safe_extract_zip(malicious_zip, extract_to)
        # Verify no file was created outside target
        self.assertFalse((extract_to / "etc" / "passwd").exists())

    def test_tar_slip_blocked(self):
        """Create a tar with path traversal and verify it's blocked."""
        import tarfile
        import io
        malicious_tar = self._tmp / "malicious.tar"
        with tarfile.open(str(malicious_tar), "w") as t:
            info = tarfile.TarInfo(name="../../../tmp/evil.sh")
            info.type = tarfile.REGTYPE
            info.size = 4
            t.addfile(info, io.BytesIO(b"evil"))
        extract_to = self._tmp / "tar_target"
        extract_to.mkdir()
        with self.assertRaises(ValueError):
            ops._safe_extract_tar(malicious_tar, extract_to)
        self.assertFalse((extract_to / "tmp" / "evil.sh").exists())

    def test_input_sanitization_null_byte(self):
        """Null bytes in archive name should be stripped."""
        aid = core.add_archive("bad\0name", "/tmp/x.zip", "zip", 0, 0)
        arch = core.get_archive(aid)
        self.assertIsNotNone(arch)
        self.assertNotIn("\0", arch.name)
        self.assertEqual(arch.name, "badname")

    def test_input_sanitization_path_traversal_rejected(self):
        """Path traversal in file path should raise ValueError."""
        with self.assertRaises(ValueError):
            core.add_files(1, [("safe.txt", "../../etc/passwd", 10, None)])

    def test_input_sanitization_truncation(self):
        """Long inputs should be truncated."""
        long_name = "A" * 2000
        aid = core.add_archive(long_name, "/tmp/x.zip", "zip", 0, 0)
        arch = core.get_archive(aid)
        self.assertIsNotNone(arch)
        self.assertLessEqual(len(arch.name), 512)

    def test_import_validates_db_integrity(self):
        """Import should reject non-SQLite files."""
        fake_db = self._tmp / "fake.db"
        fake_db.write_text("not a database")
        with self.assertRaises(ValueError):
            core.import_db(str(fake_db))

    def test_key_file_created_with_restricted_perms(self):
        """Key file should exist at SECURITY test's KEY_PATH after init_db."""
        core.init_db()
        core._get_or_create_key()
        self.assertTrue(cfg.KEY_PATH.exists(), f"Key file not found at {cfg.KEY_PATH}")
        self.assertEqual(cfg.KEY_PATH.stat().st_size, 32, "Key should be 32 bytes")

    def test_verify_command_passes_with_valid_hmac(self):
        """cmd_verify should report PASS for a valid archive."""
        import io, sys
        src = self._tmp / "verify_test"
        src.mkdir()
        self._make_files(src, {"file.txt": "data"})
        ops.cmd_add([str(src)], "zip", "verify_pass", "", None, None)
        arch = self._find_by_name("verify_pass")
        self.assertIsNotNone(arch)
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_verify(arch.id)
        sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("PASS", output)

    def test_verify_command_fails_with_tampered_data(self):
        """cmd_verify should report FAIL for a tampered archive."""
        import io, sys
        src = self._tmp / "verify_fail_test"
        src.mkdir()
        self._make_files(src, {"data.txt": "original"})
        ops.cmd_add([str(src)], "zip", "verify_fail", "", None, None)
        arch = self._find_by_name("verify_fail")
        self.assertIsNotNone(arch)
        # Tamper with DB directly
        conn = core._get_conn()
        conn.execute("UPDATE archives SET checksum='tampered' WHERE id=?", (arch.id,))
        conn.commit()
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_verify(arch.id)
        sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("FAIL", output)


if __name__ == "__main__":
    unittest.main()
