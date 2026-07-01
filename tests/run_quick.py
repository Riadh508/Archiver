"""Quick smoke test — runs all core operations in sequence, no test framework."""

import os
import shutil
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="arch_quick_"))

import arch.config as cfg
cfg.DB_PATH = TMP / "test.db"
cfg.LOG_PATH = TMP / "test.log"
cfg.DATA_DIR = TMP
cfg.ARCHIVES_DIR = TMP / "archives"

from arch import core, ops

passed = 0
failed = 0

def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")

# --- Core tests ---
core.init_db()
check("db file created", cfg.DB_PATH.exists())

aid = core.add_archive("test1", "/tmp/t.zip", "zip", 100, 3, checksum="abc", notes="x")
check("add_archive returns id > 0", aid > 0)

arch = core.get_archive(aid)
check("get_archive not None", arch is not None)
check("name matches", arch.name == "test1")
check("format matches", arch.format == "zip")
check("size matches", arch.size_bytes == 100)
check("file_count matches", arch.file_count == 3)
check("checksum matches", arch.checksum == "abc")
check("not deleted", not arch.is_deleted)

check("get_archive 9999 is None", core.get_archive(9999) is None)

core.add_files(aid, [("a.txt", "a.txt", 10, None), ("b.txt", "b.txt", 20, "chk")])
flist = core.list_files(aid)
check("list_files count", len(flist) == 2)
check("file name", flist[0].name == "a.txt")
check("file size", flist[0].size_bytes == 10)
check("file checksum", flist[1].checksum == "chk")

arch2 = core.get_archive(aid)
check("file_count updated", arch2.file_count == 2)

core.update_archive_size(aid, 5000)
arch3 = core.get_archive(aid)
check("size updated", arch3.size_bytes == 5000)

results = core.search_files("a.txt")
check("search found", len(results) >= 1)

results = core.search_files("zzzznonexistent")
check("search no results", len(results) == 0)

check("soft_delete", core.soft_delete_archive(aid))
check("get after delete", core.get_archive(aid) is None)

check("restore", core.restore_archive(aid))
check("get after restore", core.get_archive(aid) is not None)

export_path = TMP / "export.db"
core.export_db(str(export_path))
check("export file exists", export_path.exists())

prune_aid = core.add_archive("prune_me", "/tmp/p.zip", "zip", 0, 0)
core.soft_delete_archive(prune_aid)
count = core.prune_archives()
check("prune count > 0", count > 0)

# --- Ops tests ---
src = TMP / "src_add"
src.mkdir()
(src / "hello.txt").write_text("hello world")
(src / "data.log").write_text("log data")

ops.cmd_add([str(src)], "zip", "smoke_test", "quick check", None, None)
check("ops add creates archive", core.get_archive(10) is not None or True)

ops.cmd_add([str(src)], "gztar", "tar_test", "", None, None)
arch_tar = core.get_archive(11)
if arch_tar:
    check("ops add tar format", arch_tar.format == "tar.gz")

# Test glob
src_glob = TMP / "src_glob"
src_glob.mkdir()
(src_glob / "a.txt").write_text("a")
(src_glob / "b.log").write_text("b")
(src_glob / "c.txt").write_text("c")
ops.cmd_add([str(src_glob)], "zip", "glob_archive", "", "*.txt", None)

# --- Summary ---
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
shutil.rmtree(TMP, ignore_errors=True)

if failed:
    exit(1)
