import sys, os, shutil, tempfile
sys.path.insert(0, 'E:/ho/arch')
from pathlib import Path

import arch.config as cfg

# Run all test suites sequentially, each with its own temp dir

results = {}

for suite_name, test_module in [
    ("test_core", "tests.test_core"),
    ("test_license", "tests.test_license"),
    ("test_ops", "tests.test_ops"),
    ("test_security", "tests.test_security"),
    ("test_web", "tests.test_web"),
]:
    # Reset config each time
    TMP = Path(tempfile.mkdtemp(prefix=f"arch_{suite_name}_"))
    cfg.DB_PATH = TMP / "test.db"
    cfg.LOG_PATH = TMP / "test.log"
    cfg.DATA_DIR = TMP
    cfg.ARCHIVES_DIR = TMP / "archives"
    cfg.KEY_PATH = TMP / ".arch_key"
    
    # Import and run
    from unittest import TextTestRunner, TestLoader
    loader = TestLoader()
    suite = loader.loadTestsFromName(test_module)
    runner = TextTestRunner(verbosity=2, stream=open(os.devnull, 'w'))
    result = runner.run(suite)
    results[suite_name] = result
    
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 60)
print("            FULL TEST RESULTS")
print("=" * 60)
total = 0
passed = 0
failed_total = 0
for name, r in results.items():
    t = r.testsRun
    f = len(r.failures) + len(r.errors)
    total += t
    passed += (t - f)
    failed_total += f
    status = "PASS" if f == 0 else f"FAIL ({f})"
    print(f"  {name:<20} {t:>3} tests  {status}")
print("-" * 60)
print(f"  TOTAL: {total} tests, {passed} passed, {failed_total} failed")
print("=" * 60)
if failed_total == 0:
    print("  ALL PASSED")
else:
    print("  SOME TESTS FAILED")
    sys.exit(1)
