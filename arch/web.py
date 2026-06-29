"""Built-in web UI — stdlib http.server, no external deps"""
import base64
import hashlib
import http.server
import io
import json
import mimetypes
import os
import sys
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path

from . import core
from . import ops
from .config import ARCHIVES_DIR, LOG_PATH, DATA_DIR
from .log import get as get_logger

log = get_logger(LOG_PATH, "INFO")

HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>arch — نظام الأرشفة</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.header{background:#1e293b;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155}
.header h1{font-size:1.3rem;color:#38bdf8}
.header h1 span{color:#64748b;font-size:.8rem}
.nav{display:flex;gap:.5rem}
.nav a{padding:.4rem .8rem;border-radius:6px;text-decoration:none;color:#94a3b8;font-size:.85rem}
.nav a:hover,.nav a.active{background:#334155;color:#e2e8f0}
.main{padding:2rem;max-width:1200px;margin:0 auto}
.card{background:#1e293b;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;border:1px solid #334155}
.card h2{font-size:1.1rem;margin-bottom:1rem;color:#38bdf8}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{padding:.6rem .8rem;text-align:right;border-bottom:1px solid #334155}
th{color:#64748b;font-weight:500}
tr:hover{background:#1a2332}
.btn{display:inline-block;padding:.4rem 1rem;border-radius:6px;text-decoration:none;font-size:.85rem;border:none;cursor:pointer}
.btn-primary{background:#2563eb;color:#fff}
.btn-danger{background:#dc2626;color:#fff}
.btn-success{background:#16a34a;color:#fff}
.btn-sm{padding:.25rem .6rem;font-size:.8rem}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.75rem}
.badge-ok{background:#166534;color:#4ade80}
.badge-no{background:#7c2d12;color:#fb923c}
.badge-expired{background:#7f1d1d;color:#fca5a5}
.form-group{margin-bottom:1rem}
.form-group label{display:block;margin-bottom:.3rem;color:#94a3b8;font-size:.85rem}
.form-group input,.form-group select{width:100%;padding:.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;font-size:.9rem}
.form-group input:focus{border-color:#2563eb;outline:none}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.stat{display:flex;flex-direction:column;align-items:center;padding:1rem;background:#0f172a;border-radius:8px}
.stat-value{font-size:2rem;font-weight:700;color:#38bdf8}
.stat-label{font-size:.8rem;color:#64748b;margin-top:.3rem}
.toast{position:fixed;top:1rem;left:50%;transform:translateX(-50%);padding:.8rem 1.5rem;border-radius:8px;z-index:999;display:none;font-size:.9rem}
.toast-success{background:#166534;color:#4ade80;display:block}
.toast-error{background:#7f1d1d;color:#fca5a5;display:block}
.empty{color:#64748b;text-align:center;padding:2rem}
.login-wrap{max-width:400px;margin:4rem auto}
.login-wrap .card{padding:2.5rem}
.login-wrap h2{text-align:center;margin-bottom:1.5rem;color:#38bdf8}
@media(max-width:768px){.nav{gap:.25rem}.nav a{font-size:.75rem;padding:.3rem .5rem}.main{padding:1rem}.grid-2{grid-template-columns:1fr}}
</style></head><body>
<div class="header"><h1>arch <span>v0.2</span></h1><div class="nav">{NAV}</div></div>
<div class="main">{MAIN}</div>
<script>
async function api(m,p){try{const r=await fetch(m,{method:p||'GET'});return await r.json()}catch(e){return{error:e.message}}}
async function apiPost(m,b){try{const r=await fetch(m,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});return await r.json()}catch(e){return{error:e.message}}}
function $(s){return document.querySelector(s)}
function toast(msg,type){const t=document.createElement('div');t.className='toast toast-'+type;t.textContent=msg;document.body.prepend(t);setTimeout(()=>t.remove(),3000)}
</script></body></html>"""


def _render(body: str, nav: str = "") -> str:
    nav_items = [
        ("/", "الرئيسية"),
        ("/archives", "الأرشيفات"),
        ("/settings", "الإعدادات"),
        ("/logout", "خروج"),
    ]
    nav_html = " ".join(f'<a href="{u}"{" class=active" if nav and u==nav else ""}>{n}</a>' for u, n in nav_items)
    return HTML.replace("{NAV}", nav_html).replace("{MAIN}", body)


def _json_resp(data: dict, status: int = 200) -> tuple[str, int, dict]:
    return (json.dumps(data, ensure_ascii=False, default=str), status, {"Content-Type": "application/json; charset=utf-8"})


def _html_resp(body: str, nav: str = "") -> tuple[str, int, dict]:
    return (_render(body, nav), 200, {"Content-Type": "text/html; charset=utf-8"})


class ArchHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _send(self, data: bytes, status: int = 200, ctype: str = "text/html"):
        try:
            self.send_response(status)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-XSS-Protection", "1; mode=block")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
            self.send_header("Referrer-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(data)
        except ConnectionError:
            pass

    def _serve_static(self, path: str):
        try:
            p = Path(__file__).parent / "static" / path
            if not p.exists() or ".." in path:
                self._send(b"Not Found", 404)
                return
            data = p.read_bytes()
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            self._send(data, 200, ctype)
        except Exception:
            self._send(b"Not Found", 404)

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            username, password = decoded.split(":", 1)
            return core.authenticate_user(username, password) is not None
        except Exception:
            return False

    def _parse_multipart(self) -> dict:
        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            return {}
        boundary = ctype.split("boundary=")[1].split(";")[0].strip().strip('"')
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        parts = body.split(("--" + boundary).encode())
        result = {}
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            headers_raw = part[:header_end].decode("utf-8", errors="replace")
            data = part[header_end + 4:]
            if data.endswith(b"\r\n"):
                data = data[:-2]
            name = filename = None
            for line in headers_raw.split("\r\n"):
                if line.startswith("Content-Disposition"):
                    for seg in line.split(";"):
                        seg = seg.strip()
                        if seg.startswith("name="):
                            name = seg[5:].strip('"')
                        elif seg.startswith("filename="):
                            filename = seg[9:].strip('"')
            if name:
                result[name] = (filename, data)
        return result

    def _get_param(self, name: str, default: str = "") -> str:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        vals = qs.get(name, [])
        return vals[0] if vals else default

    def _login_page(self):
        body = """
<div class="login-wrap">
<div class="card">
<h2>تسجيل الدخول</h2>
<form id=loginForm>
<div class=form-group><label>اسم المستخدم</label><input id=user autofocus></div>
<div class=form-group><label>كلمة المرور</label><input id=pass type=password></div>
<button class="btn btn-primary" style="width:100%" onclick="event.preventDefault();login()">دخول</button>
</form></div></div>
<script>
function login(){const u=$('#user').value,p=$('#pass').value
if(!u||!p)return toast('املأ الحقول','error')
const h='Basic '+btoa(u+':'+p)
fetch('/api/auth',{method:'POST',headers:{'Authorization':h}}).then(r=>r.json()).then(d=>{
if(d.ok){document.cookie='auth='+encodeURIComponent(h)+';path=/;SameSite=Lax';window.location='/'}
else toast('بيانات غير صحيحة','error')})}
</script>"""
        return _html_resp(body)

    def _dashboard(self):
        core.init_db()
        archives = core.list_archives()
        total = len(archives)
        total_size = sum(a.size_bytes for a in archives)
        lic_valid, lic_msg, lic_info = core.check_license_status()
        users = core.list_users()
        backups = core.list_backups()
        cats = core.list_categories()
        body = f"""
<div class="grid-2">
<div class=card><div class=stat><div class=stat-value>{total}</div><div class=stat-label>إجمالي الأرشيفات</div></div></div>
<div class=card><div class=stat><div class=stat-value>{ops._size_fmt(total_size)}</div><div class=stat-label>الحجم الإجمالي</div></div></div>
<div class=card><div class=stat><div class=stat-value>{len(cats)}</div><div class=stat-label>المجلدات</div></div></div>
<div class=card><div class=stat><div class=stat-value>{len(backups)}</div><div class=stat-label>النسخ الاحتياطية</div></div></div>
</div>
<div class=card><h2>الترخيص</h2>
<p style="color:{'#4ade80' if lic_valid else '#fca5a5'}">{'✅ الترخيص ساري' if lic_valid else '❌ ' + lic_msg}</p>
{('<p style=color:#94a3b8>النوع: '+lic_info['type']+' | متبقي: '+str(lic_info['remaining_days'])+' يوم</p>') if lic_info else ''}
</div>
<div class=card><h2>آخر الأرشيفات</h2>
<table><tr><th>#</th><th>الاسم</th><th>الحجم</th><th>الملفات</th><th>التوقيع</th><th></th></tr>
{''.join(f'<tr><td>{a.id}</td><td>{a.name}</td><td>{ops._size_fmt(a.size_bytes)}</td><td>{a.file_count}</td><td><span class="badge badge-{"ok" if core.verify_signature(a.id) else "no"}">{"OK" if core.verify_signature(a.id) else "NO"}</span></td><td><a href=/archives/{a.id} class="btn btn-primary btn-sm">عرض</a></td></tr>' for a in archives[:10])}
</table></div>"""
        return _html_resp(body, "/")

    def _archives_list(self):
        core.init_db()
        q = self._get_param("q", "")
        sort = self._get_param("sort", "created_at")
        order = self._get_param("order", "DESC")
        if q:
            archives = core.search_archives(q, sort, order)
        else:
            archives = core.list_archives(sort_by=sort, sort_order=order)
        categories = core.list_categories()
        rows = ""
        for a in archives:
            sig_ok = core.verify_signature(a.id) and a.signature
            badge = "ok" if sig_ok else "no"
            label = "OK" if sig_ok else "—"
            cat = f'<span style="color:#94a3b8;font-size:.8rem">{a.category}</span>' if a.category else "—"
            rows += f'<tr><td>{a.id}</td><td>{a.name}</td><td>{a.format}</td><td>{cat}</td><td>{ops._size_fmt(a.size_bytes)}</td><td>{a.file_count}</td><td><span class="badge badge-{badge}">{label}</span></td><td>{a.created_at[:10]}</td><td><a href=/archives/{a.id} class="btn btn-primary btn-sm">عرض</a> <a href=/api/archives/{a.id}/download class="btn btn-sm" style="background:#334155;color:#e2e8f0">تحميل</a> <a href=# class="btn btn-danger btn-sm" onclick="event.preventDefault();del({a.id})">حذف</a></td></tr>'
        cat_options = "".join(f'<option value="{c}">{c}</option>' for c in categories)
        order_opt = f"""
<select id=sortSelect onchange="doSort()" style="background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:.3rem;font-size:.8rem">
<option value="created_at" {"selected" if sort=="created_at" else ""}>التاريخ</option>
<option value="name" {"selected" if sort=="name" else ""}>الاسم</option>
<option value="size_bytes" {"selected" if sort=="size_bytes" else ""}>الحجم</option>
<option value="file_count" {"selected" if sort=="file_count" else ""}>الملفات</option>
<option value="category" {"selected" if sort=="category" else ""}>المجلد</option>
</select>
<select id=orderSelect onchange="doSort()" style="background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:.3rem;font-size:.8rem">
<option value="DESC" {"selected" if order=="DESC" else ""}>↓ تنازلي</option>
<option value="ASC" {"selected" if order=="ASC" else ""}>↑ تصاعدي</option>
</select>"""
        qs = f"?q={q}&sort={sort}&order={order}" if q else f"?sort={sort}&order={order}"
        upload_form = f"""
<div class=card><h2>رفع أرشيف جديد</h2>
<form id=uploadForm enctype=multipart/form-data>
<div class=form-group><label>الملف</label><input id=fileInput type=file></div>
<div class=form-group><label>اسم الأرشيف (اختياري)</label><input id=nameInput placeholder="اتركه فارغاً لاستخدام اسم الملف"></div>
<div class=form-group><label>المجلد (اختياري)</label>
<select id=catInput style="background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:.5rem;width:100%">
<option value="">— بدون مجلد —</option>{cat_options}
<option value="__new__">+ إنشاء مجلد جديد</option>
</select>
<input id=newCatInput style="display:none;margin-top:.5rem" placeholder="اسم المجلد الجديد">
</div>
<div class=form-group><label>ملاحظات (اختياري)</label><input id=notesInput></div>
<button class="btn btn-primary" type=button id=uploadBtn onclick="uploadArchive()">رفع وإنشاء أرشيف</button>
</form>
<div id=uploadResult style="margin-top:1rem"></div></div>
<script>
document.getElementById('catInput')?.addEventListener('change',function(){{const v=document.getElementById('newCatInput');v.style.display=this.value=='__new__'?'block':'none'}})
async function uploadArchive(){{const btn=$('#uploadBtn');btn.disabled=true;btn.textContent='جارٍ الرفع...'
const f=$('#fileInput').files[0];if(!f){{btn.disabled=false;btn.textContent='رفع وإنشاء أرشيف';return toast('اختر ملفاً','error')}}
const fd=new FormData();fd.append('file',f);fd.append('name',$('#nameInput').value);fd.append('notes',$('#notesInput').value)
const sel=$('#catInput');let cat=sel.value;if(cat=='__new__')cat=$('#newCatInput').value;fd.append('category',cat)
try{{const r=await fetch('/api/archives/upload',{{method:'POST',body:fd}})
const d=await r.json()
if(d.ok){{toast('تم رفع الأرشيف بنجاح','success');setTimeout(()=>location.reload(),1000)}}
else toast(d.msg||'فشل الرفع','error')}}catch(e){{toast('خطأ في الاتصال بالخادم','error')}}
finally{{btn.disabled=false;btn.textContent='رفع وإنشاء أرشيف'}}}}
async function del(id){{if(!confirm('حذف؟'))return;const r=await api('/api/archives/'+id+'/delete');if(r.ok)location.reload()}}
function doSort(){{const s=$('#sortSelect').value,o=$('#orderSelect').value;window.location='?sort='+s+'&order='+o}}
</script>"""
        search_box = f"""
<div class=card><h2>بحث في الأرشيفات</h2>
<form onsubmit="event.preventDefault();doSearch()" style="display:flex;gap:.5rem;align-items:center">
<input id=searchInput value="{q}" placeholder="اسم أرشيف، ملف، أو ملاحظة..." style="flex:1;padding:.5rem;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0">
<button class="btn btn-primary">بحث</button>
<a href="/archives" class="btn" style="background:#334155;color:#e2e8f0;text-decoration:none">إعادة تعيين</a>
</form>
<div id=searchResultCount style="margin-top:.5rem;color:#94a3b8;font-size:.85rem">{len(archives)} نتيجة</div></div>
<script>
function doSearch(){{const q=encodeURIComponent($('#searchInput').value);window.location='?q='+q+'&sort={sort}&order={order}'}}
</script>"""
        body = f"""
{upload_form}
{search_box}
<div class=card><h2>جميع الأرشيفات <span style="font-size:.8rem;color:#64748b">{order_opt}</span></h2>
<table><tr><th>#</th><th>الاسم</th><th>النوع</th><th>المجلد</th><th>الحجم</th><th>الملفات</th><th>التوقيع</th><th>التاريخ</th><th></th></tr>{rows if rows else '<tr><td colspan=9 class=empty>لا توجد أرشيفات</td></tr>'}</table></div>"""
        return _html_resp(body, "/archives")

    def _archive_detail(self, aid: int):
        core.init_db()
        arch = core.get_archive(aid)
        if not arch:
            return self._send(b"Not Found", 404)
        files = core.list_files(aid)
        sig_ok = core.verify_signature(aid) and arch.signature
        files_table = "".join(f"<tr><td>{f.path}</td><td>{ops._size_fmt(f.size_bytes)}</td><td>{f.checksum[:16] if f.checksum else '—'}</td></tr>" for f in files)
        body = f"""
<div class=card><h2>#{arch.id} {arch.name}</h2>
<p style=color:#94a3b8>النوع: {arch.format} | الحجم: {ops._size_fmt(arch.size_bytes)} | الملفات: {arch.file_count}{f" | المجلد: {arch.category}" if arch.category else ""}</p>
<p>المسار: <code style="color:#94a3b8;font-size:.85rem">{arch.path}</code></p>
<p>التوقيع: <span class="badge badge-{"ok" if sig_ok else "no"}">{"HMAC OK" if sig_ok else ("" if arch.signature else "—" )}</span></p>
<p>الإنشاء: {arch.created_at[:19]}</p>
</div>"""
        body += """
<div class=card><h2>الملفات</h2>
<table><tr><th>المسار</th><th>الحجم</th><th>checksum</th></tr>__FILES__</table></div>
<a href=/api/archives/__AID__/download class="btn btn-primary">تحميل</a> <a href=# class="btn btn-success" onclick="event.preventDefault();verifyArc(__AID__)">تحقق</a> <a href=# class="btn btn-danger" onclick="event.preventDefault();del(__AID__)">حذف</a> <a href=/archives class="btn" style="background:#334155;color:#e2e8f0">رجوع</a>
<script>
async function verifyArc(id){const r=await api('/api/archives/'+id+'/verify');toast(r.valid?'التوقيع صحيح':'التوقيع غير صالح',r.valid?'success':'error')}
async function del(id){if(!confirm('حذف؟'))return;const r=await api('/api/archives/'+id+'/delete');if(r.ok)location.reload()}
</script>"""
        body = body.replace("__FILES__", files_table).replace("__AID__", str(aid))
        return _html_resp(body, "/archives")

    def _license_page(self):
        core.init_db()
        valid, msg, info = core.check_license_status()
        status_html = f"""
<div class=card><h2>حالة الترخيص</h2>
<p style="color:{'#4ade80' if valid else '#fca5a5'};font-size:1.1rem">{'✅ الترخيص ساري' if valid else '❌ ' + msg}</p>
{('<p>النوع: '+info['type']+'</p><p>ينتهي: '+info['expires_at'][:19]+'</p><p>متبقي: '+str(info['remaining_days'])+' يوم</p>') if info else ''}
</div>"""
        form_html = """
<div class=card><h2>تفعيل ترخيص</h2>
<form onsubmit="event.preventDefault();activate()">
<div class=form-group><label>رمز الترخيص</label><input id=licCode style="direction:ltr;text-align:left;font-family:monospace"></div>
<button class="btn btn-success">تفعيل</button>
</form>
<div id=licResult style="margin-top:1rem"></div></div>
<script>
async function activate(){const c=$('#licCode').value;if(!c)return
const r=await apiPost('/api/license/activate',{code:c})
$('#licResult').innerHTML='<p style=color:'+(r.ok?'#4ade80':'#fca5a5')+'>'+r.msg+'</p>'}
</script>"""
        vfy_html = """
<div class=card><h2>التحقق من رمز</h2>
<form onsubmit="event.preventDefault();verify()">
<div class=form-group><label>رمز الترخيص</label><input id=vfyCode style="direction:ltr;text-align:left;font-family:monospace"></div>
<button class="btn btn-primary">تحقق</button>
</form>
<div id=vfyResult style="margin-top:1rem"></div></div>
<script>
async function verify(){const c=$('#vfyCode').value;if(!c)return
const r=await apiPost('/api/license/verify',{code:c})
$('#vfyResult').innerHTML='<p style=color:'+(r.valid?'#4ade80':'#fca5a5')+'>'+r.msg+'</p>'}
</script>"""
        return _html_resp(status_html + form_html + vfy_html, "/license")

    def _users_page(self):
        core.init_db()
        users = core.list_users()
        def _user_row(u):
            phone = u.get("phone", "") or "—"
            email = u.get("email", "") or "—"
            if u["role"] == "admin":
                return '<tr><td>{}<td>{}</td><td><span class="badge badge-ok">{}</span></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>—</td></tr>'.format(u["id"], u["username"], u["role"], u.get("full_name",""), phone, email, u["created_at"][:10])
            return '<tr><td>{}</td><td>{}</td><td><span class="badge badge-no">{}</span></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><a href="/api/users/{}/delete" class="btn btn-danger btn-sm" onclick="return confirm(\'حذف؟\')">حذف</a></td></tr>'.format(u["id"], u["username"], u["role"], u.get("full_name",""), phone, email, u["created_at"][:10], u["id"])
        rows = "".join(_user_row(u) for u in users)
        body = """
<div class=card><h2>إضافة مستخدم</h2>
<form onsubmit="event.preventDefault();addUser()">
<div class=grid-2>
<div class=form-group><label>اسم المستخدم</label><input id=newUser></div>
<div class=form-group><label>كلمة المرور</label><input id=newPass type=password></div>
</div>
<div class=grid-2>
<div class=form-group><label>الدور</label><select id=newRole><option value=user>مستخدم</option><option value=admin>مدير</option></select></div>
<div class=form-group><label>الاسم الكامل</label><input id=newName></div>
</div>
<div class=grid-2>
<div class=form-group><label>الهاتف</label><input id=newPhone></div>
<div class=form-group><label>البريد</label><input id=newEmail></div>
</div>
<button class="btn btn-success">إضافة</button>
</form>
<div id=userResult style="margin-top:1rem"></div></div>
<div class=card><h2>المستخدمون</h2>
<table><tr><th>#</th><th>اسم المستخدم</th><th>الدور</th><th>الاسم</th><th>الهاتف</th><th>البريد</th><th>التاريخ</th><th></th></tr>__ROWS__</table></div>
<script>
async function addUser(){const u=$('#newUser').value,p=$('#newPass').value,r=$('#newRole').value,n=$('#newName').value,ph=$('#newPhone').value,e=$('#newEmail').value
if(!u||!p)return toast('املأ الحقول','error')
const resp=await apiPost('/api/users/add',{username:u,password:p,role:r,full_name:n,phone:ph,email:e})
$('#userResult').innerHTML='<p style=color:'+(resp.ok?'#4ade80':'#fca5a5')+'>'+resp.msg+'</p>'
if(resp.ok)setTimeout(()=>location.reload(),1000)}
</script>""".replace("__ROWS__", rows)
        return _html_resp(body, "/users")

    def _backup_page(self):
        core.init_db()
        backups = core.list_backups()
        def _bak_row(b):
            return "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><a href=/api/backup/{}/restore class='btn btn-sm' style='background:#334155;color:#e2e8f0' onclick=\"return confirm('استعادة؟')\">استعادة</a></td></tr>".format(b["id"], b["filename"], ops._size_fmt(b["size_bytes"]), b["created_at"][:19], b["id"])
        rows = "".join(_bak_row(b) for b in backups)
        body = """
<div class=card><h2>إنشاء نسخة احتياطية</h2>
<button class="btn btn-primary" onclick="backup()">إنشاء نسخة الآن</button>
<div id=bakResult style="margin-top:1rem"></div></div>
<div class=card><h2>النسخ الاحتياطية</h2>
<table><tr><th>#</th><th>اسم الملف</th><th>الحجم</th><th>التاريخ</th><th></th></tr>__ROWS__</table></div>
<script>
async function backup(){const r=await apiPost('/api/backup/create')
$('#bakResult').innerHTML='<p style=color:'+(r.ok?'#4ade80':'#fca5a5')+'>'+r.msg+'</p>'
if(r.ok)setTimeout(()=>location.reload(),1000)}
</script>""".replace("__ROWS__", rows if rows else '<tr><td colspan=5 class=empty>لا توجد نسخ احتياطية</td></tr>')
        return _html_resp(body, "/backup")

    def _settings_page(self):
        core.init_db()
        lic_valid, lic_msg, lic_info = core.check_license_status()
        users = core.list_users()
        backups = core.list_backups()
        settings_dict = core.get_all_settings()
        hw_id = core.get_hardware_id()

        lic_card = f"""
<div class=card><h2>حالة الترخيص</h2>
<p style="color:{'#4ade80' if lic_valid else '#fca5a5'};font-size:1.1rem">{'✅ الترخيص ساري' if lic_valid else '❌ ' + lic_msg}</p>
{('<p>النوع: <strong>'+lic_info.get('type','')+'</strong></p><p>ينتهي: '+str(lic_info.get('expires_at',''))[:19]+'</p><p>متبقي: <strong>'+str(lic_info.get('remaining_days',0))+'</strong> يوم</p>') if lic_info else ''}
<hr>
<h3 style="font-size:.95rem;margin-bottom:.8rem">تفعيل ترخيص</h3>
<form onsubmit="event.preventDefault();activate()">
<div class=form-group><label>رمز الترخيص</label><input id=licCode style="direction:ltr;text-align:left;font-family:monospace"></div>
<button class="btn btn-success">تفعيل</button>
</form>
<div id=licResult style="margin-top:.8rem"></div>
<hr>
<h3 style="font-size:.95rem;margin-bottom:.8rem">التحقق من رمز</h3>
<form onsubmit="event.preventDefault();verify()">
<div class=form-group><label>رمز الترخيص</label><input id=vfyCode style="direction:ltr;text-align:left;font-family:monospace"></div>
<button class="btn btn-primary">تحقق</button>
</form>
<div id=vfyResult style="margin-top:.8rem"></div></div>"""

        user_card = f"""
<div class=card><h2>المستخدمون</h2>
<h3 style="font-size:.9rem;margin-bottom:.8rem;color:#94a3b8">إضافة مستخدم</h3>
<form onsubmit="event.preventDefault();addUser()">
<div class=grid-2>
<div class=form-group><label>اسم المستخدم</label><input id=newUser></div>
<div class=form-group><label>كلمة المرور</label><input id=newPass type=password></div>
</div>
<div class=grid-2>
<div class=form-group><label>الدور</label><select id=newRole><option value=user>مستخدم</option><option value=admin>مدير</option></select></div>
<div class=form-group><label>الاسم الكامل</label><input id=newName></div>
</div>
<button class="btn btn-success">إضافة</button>
</form>
<div id=userResult style="margin-top:.8rem"></div>
<table style="margin-top:1rem"><tr><th>#</th><th>المستخدم</th><th>الدور</th><th>الاسم</th><th>التاريخ</th><th></th></tr>
{''.join(f'<tr><td>{u["id"]}</td><td>{u["username"]}</td><td><span class="badge badge-{"ok" if u["role"]=="admin" else "no"}">{u["role"]}</span></td><td>{u.get("full_name","")}</td><td>{u["created_at"][:10]}</td><td><a href=# class="btn btn-danger btn-sm" onclick="event.preventDefault();delUser({u['id']})">حذف</a></td></tr>' for u in users)}
</table></div>"""

        bak_rows = "".join(f'<tr><td>{b["id"]}</td><td>{b["filename"]}</td><td>{ops._size_fmt(b["size_bytes"])}</td><td>{b["created_at"][:19]}</td><td><a href=/api/backup/{b["id"]}/restore class="btn btn-sm" style="background:#334155;color:#e2e8f0" onclick="return confirm(\'استعادة؟\')">استعادة</a></td></tr>' for b in backups)
        backup_card = f"""
<div class=card><h2>النسخ الاحتياطي</h2>
<button class="btn btn-primary" onclick="doBackup()">إنشاء نسخة الآن</button>
<div id=bakResult style="margin-top:.8rem"></div>
<table style="margin-top:1rem"><tr><th>#</th><th>الملف</th><th>الحجم</th><th>التاريخ</th><th></th></tr>
{bak_rows if bak_rows else '<tr><td colspan=5 class=empty>لا توجد نسخ</td></tr>'}</table></div>"""

        hotel_name = settings_dict.get("hotel_name", "")
        gen_card = f"""
<div class=card><h2>الإعدادات العامة</h2>
<form onsubmit="event.preventDefault();saveSettings()">
<div class=form-group><label>اسم النظام</label><input id=setHotelName value="{hotel_name}"></div>
<button class="btn btn-primary">حفظ</button>
</form>
<div id=setResult style="margin-top:.8rem"></div></div>"""

        archives_count = len(core.list_archives(deleted=True))
        adv_card = f"""
<div class=card><h2>أدوات متقدمة</h2>
<div style="display:flex;gap:.5rem;flex-wrap:wrap">
<a href=/api/db/export class="btn btn-primary">تصدير قاعدة البيانات</a>
<a href=# class="btn btn-danger" onclick="event.preventDefault();pruneArchives()">حذف نهائي ({archives_count} محذوف)</a>
</div>
<div id=advResult style="margin-top:.8rem"></div></div>"""

        body = f"""
{lic_card}
<div class=grid-2>
{user_card}
{backup_card}
</div>
<div class=grid-2>
{gen_card}
{adv_card}
</div>
<script>
async function activate(){{const c=$('#licCode').value
if(!c)return;const r=await apiPost('/api/license/activate',{{code:c}})
$('#licResult').innerHTML='<p style=color:'+(r.ok?'#4ade80':'#fca5a5')+'>'+r.msg+'</p>'}}
async function verify(){{const c=$('#vfyCode').value;if(!c)return
const r=await apiPost('/api/license/verify',{{code:c}})
$('#vfyResult').innerHTML='<p style=color:'+(r.valid?'#4ade80':'#fca5a5')+'>'+r.msg+'</p>'}}
async function addUser(){{const u=$('#newUser').value,p=$('#newPass').value,r=$('#newRole').value,n=$('#newName').value
if(!u||!p)return toast('املأ الحقول','error')
const resp=await apiPost('/api/users/add',{{username:u,password:p,role:r,full_name:n}})
$('#userResult').innerHTML='<p style=color:'+(resp.ok?'#4ade80':'#fca5a5')+'>'+resp.msg+'</p>'
if(resp.ok)setTimeout(()=>location.reload(),1000)}}
async function delUser(id){{if(!confirm('حذف المستخدم؟'))return
const r=await api('/api/users/'+id+'/delete');if(r.ok)location.reload()}}
async function doBackup(){{const r=await apiPost('/api/backup/create')
$('#bakResult').innerHTML='<p style=color:'+(r.ok?'#4ade80':'#fca5a5')+'>'+r.msg+'</p>'
if(r.ok)setTimeout(()=>location.reload(),1000)}}
async function saveSettings(){{const h=$('#setHotelName').value
const r=await apiPost('/api/settings/save',{{hotel_name:h}})
$('#setResult').innerHTML='<p style=color:'+(r.ok?'#4ade80':'#fca5a5')+'>تم الحفظ</p>'}}
async function pruneArchives(){{if(!confirm('حذف جميع الأرشيفات المحذوفة نهائياً؟'))return
const r=await api('/api/archives/prune')
$('#advResult').innerHTML='<p style=color:'+(r.ok?'#4ade80':'#fca5a5')+'>تم حذف '+r.count+' أرشيف</p>'}}
</script>"""
        return _html_resp(body, "/settings")

    def do_GET(self):
        core.init_db()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # API routes
        if path == "/api/auth":
            ok = self._check_auth()
            return self._send(json.dumps({"ok": ok}).encode(), 200 if ok else 401, "application/json")
        if path == "/api/archives":
            sort = self._get_param("sort", "created_at")
            order = self._get_param("order", "DESC")
            archives = [{"id": a.id, "name": a.name, "format": a.format, "size": a.size_bytes, "files": a.file_count, "checksum": a.checksum, "signature": a.signature, "category": a.category, "created": a.created_at} for a in core.list_archives(sort_by=sort, sort_order=order)]
            return self._send(json.dumps(archives, ensure_ascii=False, default=str).encode(), 200, "application/json")
        if path == "/api/archives/search":
            q = self._get_param("q", "")
            sort = self._get_param("sort", "created_at")
            order = self._get_param("order", "DESC")
            results = core.search_archives(q, sort, order)
            data = [{"id": a.id, "name": a.name, "format": a.format, "size": a.size_bytes, "files": a.file_count, "checksum": a.checksum, "signature": a.signature, "category": a.category, "created": a.created_at} for a in results]
            return self._send(json.dumps(data, ensure_ascii=False, default=str).encode(), 200, "application/json")
        if path == "/api/archives/categories":
            return self._send(json.dumps(core.list_categories(), ensure_ascii=False).encode(), 200, "application/json")
        if path.startswith("/api/archives/") and path.endswith("/download"):
            try:
                aid = int(path.split("/")[3])
            except (ValueError, IndexError):
                return self._send(json.dumps({"error": "invalid archive id"}).encode(), 400, "application/json")
            arch = core.get_archive(aid)
            if not arch or not Path(arch.path).exists():
                return self._send(json.dumps({"error": "not found"}).encode(), 404, "application/json")
            resolved = Path(arch.path).resolve()
            if not str(resolved).startswith(str(Path(ARCHIVES_DIR).resolve())):
                return self._send(json.dumps({"error": "access denied"}).encode(), 403, "application/json")
            data = Path(arch.path).read_bytes()
            nm = resolved.name or f"{arch.name}.{arch.format}"
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{nm}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except ConnectionError:
                pass
            return
        if path.startswith("/api/archives/") and path.endswith("/delete"):
            try:
                aid = int(path.split("/")[3])
            except (ValueError, IndexError):
                return self._send(json.dumps({"error": "invalid archive id"}).encode(), 400, "application/json")
            core.soft_delete_archive(aid)
            return self._send(json.dumps({"ok": True}).encode(), 200, "application/json")
        if path.startswith("/api/archives/") and path.endswith("/verify"):
            try:
                aid = int(path.split("/")[3])
            except (ValueError, IndexError):
                return self._send(json.dumps({"error": "invalid archive id"}).encode(), 400, "application/json")
            valid = core.verify_signature(aid)
            return self._send(json.dumps({"ok": valid, "valid": valid}).encode(), 200, "application/json")
        if path.startswith("/api/archives/") and path.endswith("/restore"):
            try:
                aid = int(path.split("/")[3])
            except (ValueError, IndexError):
                return self._send(json.dumps({"error": "invalid archive id"}).encode(), 400, "application/json")
            ok = core.restore_archive(aid)
            return self._send(json.dumps({"ok": ok}).encode(), 200, "application/json")
        if path == "/api/archives/prune":
            count = core.prune_archives()
            return self._send(json.dumps({"ok": True, "count": count}).encode(), 200, "application/json")
        if path == "/api/db/export":
            if not self._check_auth():
                return self._send(json.dumps({"error": "unauthorized"}).encode(), 401, "application/json")
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            core.export_db(tmp.name)
            data = Path(tmp.name).read_bytes()
            Path(tmp.name).unlink(missing_ok=True)
            nm = "arch_backup.db"
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{nm}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except ConnectionError:
                pass
            return
        if path == "/api/license/status":
            valid, msg, info = core.check_license_status()
            return self._send(json.dumps({"valid": valid, "msg": msg, "info": info}, ensure_ascii=False, default=str).encode(), 200, "application/json")
        if path == "/api/users":
            return self._send(json.dumps(core.list_users(), ensure_ascii=False, default=str).encode(), 200, "application/json")
        if path.startswith("/api/users/") and path.endswith("/delete"):
            try:
                uid = int(path.split("/")[3])
            except (ValueError, IndexError):
                return self._send(json.dumps({"error": "invalid user id"}).encode(), 400, "application/json")
            ok = core.delete_user(uid)
            return self._send(json.dumps({"ok": ok}).encode(), 200, "application/json")
        if path == "/api/backups":
            return self._send(json.dumps(core.list_backups(), ensure_ascii=False, default=str).encode(), 200, "application/json")
        if path.startswith("/api/backup/") and path.endswith("/restore"):
            try:
                bid = int(path.split("/")[3])
            except (ValueError, IndexError):
                return self._send(json.dumps({"error": "invalid backup id"}).encode(), 400, "application/json")
            p = core.restore_backup(bid)
            return self._send(json.dumps({"ok": p is not None, "path": p}).encode(), 200, "application/json")
        if path == "/api/settings":
            return self._send(json.dumps(core.get_all_settings(), ensure_ascii=False).encode(), 200, "application/json")

        # Check auth for HTML pages (except login)
        auth_cookie = self.headers.get("Cookie", "")
        authed = False
        if "auth=" in auth_cookie:
            try:
                for cookie_part in auth_cookie.split(";"):
                    cookie_part = cookie_part.strip()
                    if cookie_part.startswith("auth="):
                        token = urllib.parse.unquote(cookie_part[5:])
                        self.headers["Authorization"] = token
                        authed = self._check_auth()
                        break
            except Exception:
                authed = False
        if not authed:
            authed = self._check_auth()
        if not authed:
            if path == "/" or path.startswith("/archives") or path.startswith("/settings") or path.startswith("/license") or path.startswith("/users") or path.startswith("/backup"):
                resp = self._login_page()
                self._send(resp[0].encode(), resp[1], resp[2].get("Content-Type", "text/html"))
                return

        # HTML pages
        if path == "/":
            body = self._dashboard()
        elif path == "/archives":
            body = self._archives_list()
        elif path.startswith("/archives/") and path.endswith("/download"):
            return self._send(b"use /api" + path.encode() + b" endpoint", 301)
        elif path.startswith("/archives/") and len(path.split("/")) == 3:
            try:
                detail_id = int(path.split("/")[-1])
            except ValueError:
                body = _html_resp("<h1>400 Bad Request</h1>", "")
            else:
                body = self._archive_detail(detail_id)
        elif path == "/settings":
            body = self._settings_page()
        elif path == "/license":
            body = self._license_page()
        elif path == "/users":
            body = self._users_page()
        elif path == "/backup":
            body = self._backup_page()
        elif path == "/logout":
            self.send_response(302)
            self.send_header("Set-Cookie", "auth=;path=/;max-age=0")
            self.send_header("Location", "/")
            self.end_headers()
            return
        elif path.startswith("/static/"):
            self._serve_static(path[8:])
            return
        else:
            body = _html_resp("<h1>404</h1>", "")

        self._send(body[0].encode(), body[1], body[2].get("Content-Type", "text/html"))

    def do_POST(self):
        core.init_db()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # Multipart upload — body is not JSON, let the handler parse it
        if path == "/api/archives/upload":
            return self._handle_upload()

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

        if path == "/api/auth":
            ok = self._check_auth()
            if ok:
                return self._send(json.dumps({"ok": True}).encode(), 200, "application/json")
            return self._send(json.dumps({"ok": False, "msg": "بيانات غير صحيحة"}).encode(), 401, "application/json")

        if path == "/api/license/activate":
            code = data.get("code", "")
            valid, msg = core.activate_license(code)
            return self._send(json.dumps({"ok": valid, "msg": msg}, ensure_ascii=False).encode(), 200, "application/json")

        if path == "/api/license/verify":
            code = data.get("code", "")
            valid, msg = core.verify_license_code(code)
            return self._send(json.dumps({"valid": valid, "msg": msg}, ensure_ascii=False).encode(), 200, "application/json")

        if path == "/api/users/add":
            u, p = data.get("username", ""), data.get("password", "")
            r = "user"
            n = data.get("full_name", "")
            ph = data.get("phone", "")
            em = data.get("email", "")
            uid = core.add_user(u, p, r, n)
            if uid and (ph or em):
                core.update_user(uid, phone=ph or None, email=em or None)
            return self._send(json.dumps({"ok": uid is not None, "msg": "تم" if uid else "المستخدم موجود مسبقاً"}, ensure_ascii=False).encode(), 200, "application/json")

        if path == "/api/backup/create":
            bak = core.create_backup()
            return self._send(json.dumps({"ok": bak is not None, "msg": bak or "فشل الإنشاء"}, ensure_ascii=False).encode(), 200, "application/json")

        if path == "/api/settings/save":
            for k, v in data.items():
                core.set_setting(k, str(v))
            return self._send(json.dumps({"ok": True}).encode(), 200, "application/json")

        return self._send(json.dumps({"error": "unknown endpoint"}).encode(), 404, "application/json")

    def _handle_upload(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 100 * 1024 * 1024:
            return self._send(json.dumps({"ok": False, "msg": "الملف كبير جداً (الحد 100MB)"}).encode(), 400, "application/json")
        parts = self._parse_multipart()
        if "file" not in parts:
            return self._send(json.dumps({"ok": False, "msg": "الملف مطلوب"}).encode(), 400, "application/json")
        filename, data = parts["file"]
        if not filename:
            return self._send(json.dumps({"ok": False, "msg": "اسم الملف مطلوب"}).encode(), 400, "application/json")
        override_name = (parts.get("name") or (None, None))[1] or b""
        notes = (parts.get("notes") or (None, None))[1] or b""
        cat_raw = (parts.get("category") or (None, None))[1] or b""
        name = override_name.decode("utf-8", errors="replace").strip() or Path(filename).stem
        note_str = notes.decode("utf-8", errors="replace").strip()
        category_str = cat_raw.decode("utf-8", errors="replace").strip()
        ext = Path(filename).suffix.lower()
        safe_name = Path(filename).name
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
        safe_name = safe_name.strip()[:128]
        if not safe_name:
            safe_name = "upload"
        chk_hex = hashlib.sha256(data).hexdigest()
        files = []
        fmt = "zip"
        if ext == ".zip" and zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                for info in zf.infolist():
                    if not info.is_dir():
                        files.append((info.filename, info.filename, info.file_size, None))
        else:
            files.append((safe_name, safe_name, len(data), chk_hex))
            fmt = ext.lstrip(".") or "bin"
        ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
        dest = ARCHIVES_DIR / safe_name
        dest.write_bytes(data)
        core.init_db()
        aid = core.add_archive(
            name=name,
            path=str(dest),
            fmt=fmt,
            size=dest.stat().st_size,
            file_count=len(files),
            checksum=chk_hex,
            notes=note_str,
            category=category_str,
        )
        if files:
            core.add_files(aid, files)
        del data
        log.info(f"Web upload: archive id={aid} name={name} fmt={fmt} files={len(files)}")
        return self._send(json.dumps({"ok": True, "msg": "تمت الإضافة", "id": aid}, ensure_ascii=False).encode(), 200, "application/json")


def serve(host: str = "127.0.0.1", port: int = 8080):
    core.init_db()
    if core.authenticate_user("admin", "admin123") is None:
        core.add_user("admin", "admin123", "admin", "المدير")
    server = http.server.HTTPServer((host, port), ArchHandler)
    print(f"arch web UI at http://{host}:{port}")
    log.info(f"Web UI started on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()


if __name__ == "__main__":
    serve()
