import sys, os, json, zipfile, io, hashlib, base64
sys.path.insert(0, 'E:/ho/arch')
from arch.web import ArchHandler
from arch import core

core.init_db()
core.add_user('admin', 'admin123', 'admin', 'Admin')

class Headers:
    def __init__(self, auth=None, ct='application/json'):
        self._auth = auth
        self._ct = ct
    def get(self, k, d=''):
        if self._auth and k == 'Authorization':
            return 'Basic ' + base64.b64encode(self._auth.encode()).decode()
        if k == 'Content-Length':
            return str(len(self._body)) if hasattr(self, '_body') else '0'
        if k == 'Content-Type':
            return self._ct
        if k == 'Cookie':
            return ''
        return d

class MockHandler(ArchHandler):
    def __init__(self, method, path, body, auth=None, ct='application/json'):
        self.command = method
        self.path = path
        self.request_version = 'HTTP/1.0'
        self.headers = Headers(auth, ct)
        self.headers._body = body
        self.close_connection = True
        self.wfile = io.BytesIO()
        self.rfile = io.BytesIO(body)
        self.raw_requestline = b''
        self.requestline = method + ' ' + path + ' HTTP/1.0'
    def version_string(self):
        return 'ArchHTTP'

def test(m, p, b=b'', auth=None):
    h = MockHandler(m, p, b, auth)
    getattr(h, 'do_' + m)()
    resp = h.wfile.getvalue()
    sc = int(resp.split(b'\r\n')[0].split(b' ')[1])
    parts = resp.split(b'\r\n\r\n', 1)
    return sc, (parts[1] if len(parts) > 1 else b'')

def make_multipart(fields, boundary=b'----TestBoundary'):
    body = b''
    for name, (fname, data) in fields.items():
        body += b'--' + boundary + b'\r\n'
        disp = 'Content-Disposition: form-data; name="' + name + '"'
        if fname:
            disp += '; filename="' + fname + '"'
        body += disp.encode() + b'\r\n\r\n'
        if data is not None:
            body += data if isinstance(data, bytes) else data.encode()
        body += b'\r\n'
    body += b'--' + boundary + b'--\r\n'
    return body, 'multipart/form-data; boundary=' + boundary.decode()

# Upload a zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as zf:
    zf.writestr('hello.txt', 'Hello World')
    zf.writestr('sub/file.bin', b'\x00\x01\x02')
zip_data = buf.getvalue()

body, ct = make_multipart({'file': ('test.zip', zip_data)})
h = MockHandler('POST', '/api/archives/upload', body, ct=ct)
h.do_POST()
resp = h.wfile.getvalue()
data = json.loads(resp.split(b'\r\n\r\n', 1)[1])
aid = data['id']
print('aid=' + str(aid))

# Test detail page
s, b = test('GET', '/archives/' + str(aid), auth='admin:admin123')
print('status=' + str(s))
print('len=' + str(len(b)))
n1 = b'hello.txt' in b
n2 = b'sub/file.bin' in b
n3 = b'test' in b
print('hello.txt=' + str(n1) + ' sub/file.bin=' + str(n2) + ' test=' + str(n3))
if not n1:
    print('Body preview: ' + b[600:1000].decode('utf-8', errors='replace'))
# Search for any content after CSS
idx = b.find(b'<div class=main>')
if idx >= 0:
    print('Main content: ' + b[idx:idx+500].decode('utf-8', errors='replace'))
else:
    print('No main div found')
    # Find where the style ends and body content starts
    idx2 = b.find(b'</style>')
    if idx2 >= 0:
        print('After style: ' + b[idx2:idx2+500].decode('utf-8', errors='replace'))

