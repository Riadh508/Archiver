"""End-to-end tests for web UI (handler mock, no real server)."""
import io
import json
import base64
import sys
import os
import tempfile
import shutil
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import arch.config as cfg
_TMP = Path(tempfile.mkdtemp(prefix="arch_web_"))
_saved = {k: getattr(cfg, k) for k in ("DB_PATH","LOG_PATH","DATA_DIR","ARCHIVES_DIR","KEY_PATH")}
cfg.DB_PATH = _TMP / "test.db"
cfg.LOG_PATH = _TMP / "test.log"
cfg.DATA_DIR = _TMP
cfg.ARCHIVES_DIR = _TMP / "archives"
cfg.KEY_PATH = _TMP / ".arch_key"

from arch.web import ArchHandler
from arch import core, trial_guard

# Purge trial markers so a fresh trial is always created
try:
    mp = trial_guard._get_marker_path()
    if mp.exists():
        mp.unlink()
except Exception:
    pass
try:
    import winreg
    sk, vn = trial_guard._get_registry_key()
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sk, 0, winreg.KEY_SET_VALUE)
    winreg.DeleteValue(k, vn)
    winreg.CloseKey(k)
except Exception:
    pass

core.init_db()
core.add_user('admin', 'admin123', 'admin', 'Admin')


class Headers:
    def __init__(self, auth=None, content_type="application/json"):
        self._auth = auth
        self._ct = content_type
    def get(self, k, d=""):
        if self._auth and k == "Authorization":
            return "Basic " + base64.b64encode(self._auth.encode()).decode()
        if k == "Content-Length":
            return str(len(self._body)) if hasattr(self, '_body') else "0"
        if k == "Content-Type":
            return self._ct
        if k == "Cookie":
            return ""
        return d


class MockHandler(ArchHandler):
    """Handler that skips automatic request handling in __init__."""

    def __init__(self, method, path, body, auth=None, content_type="application/json"):
        self.command = method
        self.path = path
        self.request_version = "HTTP/1.0"
        self.headers = Headers(auth, content_type)
        self.headers._body = body
        self.close_connection = True
        self.wfile = io.BytesIO()
        self.rfile = io.BytesIO(body)
        self.raw_requestline = b""
        self.requestline = f"{method} {path} HTTP/1.0"
        # skip BaseHTTPRequestHandler.__init__ which calls handle_one_request

    def version_string(self):
        return "ArchHTTP"


def test(method, path, body=b"", auth=None):
    h = MockHandler(method, path, body, auth)
    getattr(h, "do_" + method)()
    resp = h.wfile.getvalue()
    status_code = int(resp.split(b"\r\n")[0].split(b" ")[1])
    parts = resp.split(b"\r\n\r\n", 1)
    return status_code, (parts[1] if len(parts) > 1 else b"")


def _make_multipart(fields: dict, boundary=b"----TestBoundary") -> tuple[bytes, str]:
    """Build multipart/form-data body. fields: name -> (filename, data_or_None)."""
    body = b""
    for name, (fname, data) in fields.items():
        body += b"--" + boundary + b"\r\n"
        disp = f'Content-Disposition: form-data; name="{name}"'
        if fname:
            disp += f'; filename="{fname}"'
        body += disp.encode() + b"\r\n\r\n"
        if data is not None:
            body += data if isinstance(data, bytes) else data.encode()
        body += b"\r\n"
    body += b"--" + boundary + b"--\r\n"
    ct = f"multipart/form-data; boundary={boundary.decode()}"
    return body, ct


passed = 0
failed = 0

def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")

# 1. Unauthenticated -> login page
s, b = test("GET", "/")
check("GET / (no auth) returns 200", s == 200, str(s))
login_markers = [b"\xd8\xaa\xd8\xb3\xd8\xac\xd9\x8a\xd9\x84", b"login"]
check("GET / shows login page", any(m in b.lower() for m in login_markers))

# 2. POST /api/auth with wrong password
s, b = test("POST", "/api/auth", json.dumps({}).encode(), auth="admin:wrong")
check("POST /api/auth bad pw -> 401", s == 401, str(s))

# 3. POST /api/auth with correct password
s, b = test("POST", "/api/auth", json.dumps({}).encode(), auth="admin:admin123")
ok = s == 200 and json.loads(b).get("ok") is True
check("POST /api/auth good pw -> 200 ok", ok, f"{s} {b[:60]}")

# 4. GET /api/archives
s, b = test("GET", "/api/archives", auth="admin:admin123")
check("GET /api/archives", s == 200 and isinstance(json.loads(b), list), str(s))

# 5. GET /api/license/status
s, _ = test("GET", "/api/license/status", auth="admin:admin123")
check("GET /api/license/status", s == 200, str(s))

# 6. POST /api/license/activate
s, b = test("POST", "/api/license/activate",
            json.dumps({"code": "TEST_MONTHLY_AAAA_BBBB_CCCC"}).encode(),
            auth="admin:admin123")
check("POST /api/license/activate", s == 200, f"{s} {b[:60]}")

# 7. POST /api/users/add
s, b = test("POST", "/api/users/add",
            json.dumps({"username": "u2", "password": "p2", "role": "user"}).encode(),
            auth="admin:admin123")
check("POST /api/users/add", s == 200, f"{s} {b[:60]}")

# 8. POST /api/backup/create
s, b = test("POST", "/api/backup/create", json.dumps({}).encode(), auth="admin:admin123")
check("POST /api/backup/create", s == 200, f"{s} {b[:60]}")

# 9. GET /api/users
s, b = test("GET", "/api/users", auth="admin:admin123")
users = json.loads(b) if s == 200 else []
check("GET /api/users returns list", isinstance(users, list) and len(users) >= 2, str(s))

# 10. GET /api/backups
s, b = test("GET", "/api/backups", auth="admin:admin123")
check("GET /api/backups returns list", s == 200 and isinstance(json.loads(b), list), str(s))

# 11. Verify HTML template rendering
from arch.web import _render, HTML

h = _render("hello", "/settings")
check("_render contains nav links", "/settings" in h and "الإعدادات" in h)
check("HTML template has NAV/MAIN placeholders", "{NAV}" in HTML and "{MAIN}" in HTML)

# 12. Upload archive — missing file
body, ct = _make_multipart({"name": ("", b"test")})
h = MockHandler("POST", "/api/archives/upload", body, content_type=ct)
h.do_POST()
resp = h.wfile.getvalue()
status_code = int(resp.split(b"\r\n")[0].split(b" ")[1])
check("POST /api/archives/upload no file -> 400", status_code == 400)

# 13. Upload archive — bad zip file (now accepted as non-zip file)
import zipfile
bad_data = b"not a zip file"
body, ct = _make_multipart({"file": ("bad.zip", bad_data)})
h = MockHandler("POST", "/api/archives/upload", body, content_type=ct)
h.do_POST()
resp = h.wfile.getvalue()
status_code = int(resp.split(b"\r\n")[0].split(b" ")[1])
check("POST /api/archives/upload non-zip -> 200 (accepted)", status_code == 200, str(status_code))

# 14. Upload valid zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("hello.txt", "Hello World")
    zf.writestr("sub/file.bin", b"\x00\x01\x02")
zip_data = buf.getvalue()
body, ct = _make_multipart({"file": ("test.zip", zip_data)})
h = MockHandler("POST", "/api/archives/upload", body, content_type=ct)
h.do_POST()
resp = h.wfile.getvalue()
status_code = int(resp.split(b"\r\n")[0].split(b" ")[1])
data = json.loads(resp.split(b"\r\n\r\n", 1)[1])
check("POST /api/archives/upload valid zip -> 200", status_code == 200 and data.get("ok"))
check("Upload returns archive id", isinstance(data.get("id"), int) and data["id"] > 0)
upload_aid = data["id"]

# 15. Verify uploaded archive appears in list
s, b = test("GET", "/api/archives", auth="admin:admin123")
archives = json.loads(b) if s == 200 else []
found = any(a["id"] == upload_aid for a in archives)
check("Uploaded archive appears in list", found)
if found:
    a = next(a for a in archives if a["id"] == upload_aid)
    check("Uploaded archive name matches", a["name"] == "test")
    check("Uploaded archive has correct format", a["format"] == "zip")
    check("Uploaded archive has files count", a["files"] == 2)

# 16. Upload with custom name
buf2 = io.BytesIO()
with zipfile.ZipFile(buf2, "w") as zf:
    zf.writestr("a.txt", b"data")
zip_data2 = buf2.getvalue()
body, ct = _make_multipart({"file": ("myname.zip", zip_data2), "name": ("", b"custom_name")})
h = MockHandler("POST", "/api/archives/upload", body, content_type=ct)
h.do_POST()
resp = h.wfile.getvalue()
status_code = int(resp.split(b"\r\n")[0].split(b" ")[1])
data = json.loads(resp.split(b"\r\n\r\n", 1)[1])
check("POST upload with custom name -> 200", status_code == 200 and data.get("ok"))

# 17. Detail page routing — archived archive from test 14
s, b = test("GET", f"/archives/{upload_aid}", auth="admin:admin123")
check(f"GET /archives/{upload_aid} detail page -> 200", s == 200)
check("Detail page contains hello.txt", b"hello.txt" in b)
check("Detail page contains sub/file.bin", b"sub/file.bin" in b)
check("Detail page shows archive name", b"test" in b)

# 18. Delete via GET endpoint (returns JSON)
s, b = test("GET", f"/api/archives/{upload_aid}/delete", auth="admin:admin123")
check(f"DELETE /api/archives/{upload_aid} -> 200 ok", s == 200 and json.loads(b).get("ok") is True)

# 19. Verify deleted archive no longer in list
s, b = test("GET", "/api/archives", auth="admin:admin123")
archives = json.loads(b) if s == 200 else []
check("Deleted archive removed from list", all(a["id"] != upload_aid for a in archives))

# 20. Settings page renders
s, b = test("GET", "/settings", auth="admin:admin123")
check("GET /settings -> 200", s == 200)
page_text = b.decode("utf-8")
check("Settings page has license section", "الترخيص" in page_text)
check("Settings page has users section", "المستخدمون" in page_text)
check("Settings page has backup section", "نسخ" in page_text)
check("Settings page has general section", "الإعدادات العامة" in page_text)

# 21. Settings API — save and get
s, b = test("POST", "/api/settings/save", auth="admin:admin123", body=json.dumps({"hotel_name": "My Arch", "currency": "USD"}).encode())
check("POST /api/settings/save -> 200 ok", s == 200 and json.loads(b).get("ok") is True)
s, b = test("GET", "/api/settings", auth="admin:admin123")
settings = json.loads(b) if s == 200 else {}
check("GET /api/settings has hotel_name", settings.get("hotel_name") == "My Arch")

# 22. License status check
s, b = test("GET", "/api/license/status", auth="admin:admin123")
status = json.loads(b) if s == 200 else {}
check("License status shows valid", status.get("valid") is True)
check("License status shows type", status.get("info", {}).get("type") is not None)

# 23. Upload with category
_cat_buf = io.BytesIO()
with zipfile.ZipFile(_cat_buf, "w") as _zf:
    _zf.writestr("a.txt", "aaa")
_cat_zip = _cat_buf.getvalue()
body, ct = _make_multipart({"file": ("cat_test.zip", _cat_zip), "category": ("", b"TestFolder")})
h = MockHandler("POST", "/api/archives/upload", body, content_type=ct)
h.do_POST()
resp = h.wfile.getvalue()
status_code = int(resp.split(b"\r\n")[0].split(b" ")[1])
data = json.loads(resp.split(b"\r\n\r\n", 1)[1])
cat_aid = data.get("id")
check("Upload with category -> 200", status_code == 200 and data.get("ok"))
check("Upload with category returns id", cat_aid is not None)

# 25. GET /api/archives with sort
s, b = test("GET", "/api/archives?sort=name&order=ASC", auth="admin:admin123")
archives = json.loads(b) if s == 200 else []
check("GET /api/archives with sort -> 200", s == 200)
check("Archives list has category field", any("category" in a for a in archives))

# 26. GET /api/archives/categories
s, b = test("GET", "/api/archives/categories", auth="admin:admin123")
cats = json.loads(b) if s == 200 else []
check("GET /api/archives/categories -> 200", s == 200)
check("Categories includes TestFolder", "TestFolder" in cats)

# 27. GET /api/archives/search
s, b = test("GET", "/api/archives/search?q=aaa", auth="admin:admin123")
results = json.loads(b) if s == 200 else []
check("GET /api/archives/search -> 200", s == 200)

# 28. Archives page has search box
s, b = test("GET", "/archives", auth="admin:admin123")
page_text = b.decode("utf-8")
check("Archives page has search box", "بحث" in page_text)
check("Archives page has category column", "المجلد" in page_text)
check("Archives page has sort control", "ترتيب" in page_text or "تنازلي" in page_text)

# 29. Archives page with search query
s, b = test("GET", "/archives?q=test&sort=name&order=ASC", auth="admin:admin123")
check("GET /archives?q=... -> 200", s == 200)
page_text = b.decode("utf-8")
check("Search results show count", "نتيجة" in page_text)

# 30. Detail page shows category
from arch.core import add_archive as _add_archive
_cat_aid = _add_archive("cat_detail_test", "/tmp/c.zip", "zip", 0, 0, category="MyFolder")
s, b = test("GET", f"/archives/{_cat_aid}", auth="admin:admin123")
_detail_text = b.decode("utf-8")
check("Detail page shows category", s == 200 and "المجلد" in _detail_text)

print()
print(f"Results: {passed} passed, {failed} failed")
shutil.rmtree(_TMP, ignore_errors=True)
for k, v in _saved.items():
    setattr(cfg, k, v)
sys.exit(1 if failed else 0)
