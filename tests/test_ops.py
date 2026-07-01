"""Unit tests for ops.py — using unittest (stdlib)"""

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import arch.config as cfg

from arch import core, ops

_TMP = Path(tempfile.mkdtemp(prefix="arch_ops_"))


class TestOps(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._saved = {k: getattr(cfg, k) for k in ("DB_PATH","LOG_PATH","DATA_DIR","ARCHIVES_DIR","KEY_PATH")}
        cfg.DB_PATH = _TMP / "test.db"
        cfg.LOG_PATH = _TMP / "test.log"
        cfg.DATA_DIR = _TMP
        cfg.ARCHIVES_DIR = _TMP / "archives"
        cfg.KEY_PATH = _TMP / ".arch_key"
        core.init_db()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)
        for k, v in cls._saved.items():
            setattr(cfg, k, v)

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

    def test_cmd_add_file(self):
        src = _TMP / "src_single"
        src.mkdir()
        self._make_files(src, {"hello.txt": "hello world"})
        ops.cmd_add([str(src)], "zip", None, "", None, None)
        arch = self._find_by_name("src_single")
        self.assertIsNotNone(arch)
        self.assertEqual(arch.format, "zip")
        self.assertEqual(arch.file_count, 1)

    def test_cmd_add_with_glob(self):
        src = _TMP / "src_glob"
        src.mkdir()
        self._make_files(src, {"a.txt": "aaa", "b.log": "bbb", "c.txt": "ccc"})
        ops.cmd_add([str(src)], "zip", "glob_test", "with glob", "*.txt", None)
        arch = self._find_by_name("glob_test")
        self.assertIsNotNone(arch)
        self.assertEqual(arch.file_count, 2)

    def test_cmd_add_with_format(self):
        src = _TMP / "src_tar"
        src.mkdir()
        self._make_files(src, {"data.txt": "data"})
        ops.cmd_add([str(src)], "gztar", "tar_test", "", None, None)
        arch = self._find_by_name("tar_test")
        self.assertIsNotNone(arch)
        self.assertEqual(arch.format, "tar.gz")

    def test_cmd_add_nonexistent_path(self):
        src = _TMP / "i_dont_exist"
        ops.cmd_add([str(src)], "zip", "fail", "", None, None)

    def test_cmd_list_all(self):
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_list(None)
        sys.stdout = sys.__stdout__
        self.assertIn("glob_test", captured.getvalue())

    def test_cmd_list_detail(self):
        arch = self._find_by_name("src_single")
        self.assertIsNotNone(arch)
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_list(arch.id)
        sys.stdout = sys.__stdout__
        self.assertIn("hello.txt", captured.getvalue())

    def test_cmd_list_json(self):
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_list(None, json=True)
        sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("glob_test", output)
        self.assertIn('"id"', output)
        self.assertIn('"name"', output)

    def test_cmd_search(self):
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_search("hello")
        sys.stdout = sys.__stdout__
        self.assertIn("hello.txt", captured.getvalue())

    def test_cmd_extract(self):
        arch = self._find_by_name("src_single")
        self.assertIsNotNone(arch)
        out = _TMP / "extract_out"
        ops.cmd_extract(arch.id, str(out))
        self.assertTrue((out / "src_single" / "hello.txt").exists())

    def test_cmd_verify(self):
        arch = self._find_by_name("src_single")
        self.assertIsNotNone(arch)
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_verify(arch.id)
        sys.stdout = sys.__stdout__
        self.assertIn("PASS", captured.getvalue())

    def test_cmd_remove_and_restore(self):
        aid = core.add_archive("ops_del", "/tmp/x.zip", "zip", 0, 0)
        ops.cmd_remove(aid)
        self.assertIsNone(core.get_archive(aid))
        ops.cmd_restore(aid)
        self.assertIsNotNone(core.get_archive(aid))

    def test_cmd_prune(self):
        aid = core.add_archive("ops_prune", "/tmp/p.zip", "zip", 0, 0)
        core.soft_delete_archive(aid)
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_prune()
        sys.stdout = sys.__stdout__
        self.assertIn("Pruned", captured.getvalue())

    def test_cmd_export(self):
        export_path = _TMP / "export_ops.db"
        captured = io.StringIO()
        sys.stdout = captured
        ops.cmd_export(str(export_path))
        sys.stdout = sys.__stdout__
        self.assertTrue(export_path.exists())

    def test_cmd_scan(self):
        scan_root = _TMP / "scan_root"
        scan_root.mkdir()
        (scan_root / "sub_a").mkdir()
        (scan_root / "sub_b").mkdir()
        (scan_root / "sub_a" / "f1.txt").write_text("a")
        (scan_root / "sub_b" / "f2.txt").write_text("b")
        ops.cmd_scan(str(scan_root), "zip", None, "batch scan")
        self.assertIsNotNone(self._find_by_name("sub_a"))
        self.assertIsNotNone(self._find_by_name("sub_b"))


if __name__ == "__main__":
    unittest.main()
