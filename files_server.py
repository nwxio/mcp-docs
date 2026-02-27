#!/usr/bin/env python3
"""Unified files server: upload + download on single port"""

import http.server
import socketserver
import os
import sys
import json
import uuid
import shutil
import time
import base64
from datetime import datetime, timedelta
from urllib.parse import unquote, quote, urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
HOST = "172.24.1.204"
DOMAIN = "https://files.netwize.work"

BASE_DIR = "/files"
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SHARED_DIR = os.path.join(BASE_DIR, "shared")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
SESSIONS_FILE = os.path.join(BASE_DIR, "sessions.json")
TOKENS_FILE = os.path.join(BASE_DIR, "tokens.json")

SESSION_TTL_HOURS = 24
TOKEN_TTL_MINUTES = 30
MAX_FILE_SIZE = 50 * 1024 * 1024

os.makedirs(SHARED_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_link(url, text="Источник"):
    return f"[{text}]({url})"


def encode_download_key(session_id, filename):
    raw = f"{session_id}/{filename}".encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def decode_download_key(key):
    try:
        padded = key + '=' * (-len(key) % 4)
        raw = base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8')
        sid, filename = raw.split('/', 1)
        sid = os.path.basename(sid)
        filename = os.path.basename(filename)
        if not sid or not filename:
            return None, None
        return sid, filename
    except Exception:
        return None, None


def cleanup_sessions():
    sessions = load_json(SESSIONS_FILE)
    now = datetime.now()
    for sid in list(sessions.keys()):
        try:
            if now > datetime.fromisoformat(sessions[sid]['expires']):
                path = os.path.join(SHARED_DIR, sid)
                if os.path.exists(path):
                    shutil.rmtree(path)
                del sessions[sid]
        except:
            pass
    save_json(SESSIONS_FILE, sessions)


def cleanup_tokens():
    tokens = load_json(TOKENS_FILE)
    now = datetime.now()
    for token in list(tokens.keys()):
        try:
            if now > datetime.fromisoformat(tokens[token]['expires']):
                del tokens[token]
        except:
            pass
    save_json(TOKENS_FILE, tokens)


class FileHandler(http.server.BaseHTTPRequestHandler):
    server_version = 'FileServer/1.0'
    
    def log_message(self, format, *args):
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {args[0]}")

    def send_text(self, text, code=200, content_type='text/plain'):
        data = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj, code=200):
        self.send_text(json.dumps(obj, ensure_ascii=False), code, 'application/json')

    def send_error_page(self, code, message):
        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error {code}</title>
<style>body{{font-family:Arial;text-align:center;padding:50px;background:#1a1a2e;color:#fff}}
.error{{background:#fff;color:#333;padding:40px;border-radius:10px;max-width:400px;margin:0 auto}}
h1{{color:#c62828}}</style></head>
<body><div class="error"><h1>Error {code}</h1><p>{message}</p></div></body></html>'''
        self.send_text(html, code, 'text/html')

    def show_download_bridge(self, key):
        sid, filename = decode_download_key(key)
        if not sid or not filename:
            self.send_error_page(400, 'Invalid download link')
            return

        safe_sid = quote(sid, safe='')
        safe_name = quote(filename, safe='')
        direct_url = f"/{safe_sid}/{safe_name}"

        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Download</title>
<style>
body{{font-family:Arial,sans-serif;background:#f5f7fa;margin:0;padding:24px;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.box{{max-width:460px;width:100%;background:#fff;border-radius:12px;padding:24px;box-shadow:0 8px 30px rgba(0,0,0,.1);text-align:center}}
.btn{{display:inline-block;background:#2e7d32;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700;margin-top:12px}}
.hint{{color:#666;font-size:13px;margin-top:10px}}
</style></head>
<body><div class="box">
<h2 style="margin:0 0 8px">Preparing download</h2>
<p style="margin:0;color:#666">If your browser blocks auto-redirect, tap button:</p>
<a class="btn" href="{direct_url}" target="_blank" rel="noopener noreferrer">Скачать</a>
<div class="hint">File: {filename}</div>
</div>
<script>
setTimeout(function(){{window.location.href='{direct_url}';}},120);
</script>
</body></html>'''
        self.send_text(html, 200, 'text/html')

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)

            if path.startswith('/d/'):
                key = path[3:].split('/', 1)[0].strip()
                if not key:
                    self.send_error_page(400, 'Invalid download link')
                    return
                self.show_download_bridge(key)
                return

            short_upload = query.get('u', [None])[0]
            if short_upload:
                self.show_upload_page(short_upload)
                return

            short_download = query.get('d', [None])[0]
            if short_download:
                self.show_download_bridge(short_download)
                return

            short_session = query.get('s', [None])[0]
            short_file = query.get('f', [None])[0]
            if short_session and short_file:
                self.download_file(short_session, short_file)
                return
            
            if path == '/health':
                self.send_json({'status': 'ok', 'time': datetime.now().isoformat()})
                return
            
            if path == '/' or path == '/files':
                self.show_files()
                return
            
            if path == '/Загрузи':
                self.create_upload_link_and_redirect()
                return
            
            if path.startswith('/upload/'):
                self.show_upload_page(path[8:].split('?')[0].rstrip('/'))
                return
            
            if path.startswith('/api/check/'):
                self.check_token(path[11:])
                return
            
            # Session-based: /<session_id>/<filename>
            parts = path.strip('/').split('/', 1)
            if len(parts) >= 1 and parts[0]:
                sid = parts[0]
                session_path = os.path.join(SESSIONS_DIR, sid)
                
                if not os.path.exists(session_path):
                    self.send_error_page(404, 'Session not found')
                    return
                
                if len(parts) == 1:
                    self.show_session(sid)
                    return
                
                filename = parts[1]
                self.download_file(sid, filename)
                return
            
            self.send_error_page(404, 'Not found')
            
        except Exception as e:
            print(f"GET error: {e}")
            self.send_error_page(500, str(e))

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)

            short_upload = query.get('u', [None])[0]
            if short_upload:
                self.handle_upload(short_upload)
                return
            
            if path.startswith('/upload/'):
                self.handle_upload(path[8:].rstrip('/'))
                return
            
            if path == '/api/token' or path == '/api/create_token':
                self.create_token()
                return
            
            if path.startswith('/api/check/'):
                self.check_token(path[11:])
                return
            
            if path == '/api/share':
                self.create_share_link()
                return
            
            self.send_error_page(404, 'Not found')
            
        except Exception as e:
            print(f"POST error: {e}")
            self.send_json({'error': str(e)}, 500)

    def show_files(self):
        files = []
        for f in os.listdir(SHARED_DIR):
            fp = os.path.join(SHARED_DIR, f)
            if os.path.isfile(fp):
                size = os.path.getsize(fp)
                files.append({'name': f, 'size': size})
        
        html = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Files</title>
<style>body{font-family:Arial,sans-serif;margin:40px;background:#f5f5f5}
.container{max-width:800px;margin:0 auto;background:#fff;padding:20px;border-radius:8px}
h1{color:#333}
.file{padding:10px;border-bottom:1px solid #eee}
.file a{color:#1976d2;text-decoration:none;font-size:16px}
.file .size{color:#888;font-size:12px}
.upload{background:#4CAF50;color:#fff;padding:10px 20px;text-decoration:none;border-radius:5px}
</style></head>
<body><div class="container"><h1>📁 Files</h1>
<a href="/Загрузи" class="upload">➕ Загрузить файл</a><br><br>'''
        
        for f in files:
            size_str = f"{f['size']/1024:.1f} KB" if f['size'] < 1048576 else f"{f['size']/1048576:.1f} MB"
            html += f'<div class="file"><a href="/{quote(f["name"])}">{f["name"]}</a> <span class="size">({size_str})</span></div>'
        
        if not files:
            html += '<p>No files yet</p>'
        
        html += '</div></body></html>'
        self.send_text(html, 200, 'text/html')

    def create_upload_link_and_redirect(self):
        import uuid
        token = str(uuid.uuid4())
        now = datetime.now()
        expires = now + timedelta(minutes=30)
        
        tokens = load_json(TOKENS_FILE)
        tokens[token] = {
            'created': now.isoformat(),
            'expires': expires.isoformat(),
            'used': False
        }
        save_json(TOKENS_FILE, tokens)
        
        self.send_response(302)
        self.send_header('Location', f'/upload/{token}')
        self.end_headers()

    def download_file(self, sid, filename):
        filepath = os.path.join(SESSIONS_DIR, sid, filename)
        if not os.path.exists(filepath):
            self.send_error_page(404, 'File not found')
            return
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(filename, safe='')}")
        self.send_header('Content-Length', str(size))
        self.end_headers()
        with open(filepath, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)
    
    def download_file_direct(self, filepath, filename):
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(filename, safe='')}")
        self.send_header('Content-Length', str(size))
        self.end_headers()
        with open(filepath, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)
    
    def show_session(self, sid):
        sessions = load_json(SESSIONS_FILE)
        if sid not in sessions:
            self.send_error_page(404, 'Session not found')
            return
        data = sessions[sid]
        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Session</title>
<style>body{{font-family:Arial;margin:40px}}ul{{list-style:none;padding:0}}li{{margin:10px 0}}a{{color:#1976d2;font-size:16px}}</style></head>
<body><h1>Files</h1><p style="color:#666">Expires: {data.get('expires','')[:19]}</p><ul>'''
        for fname in data.get('files', []):
            url = f"{DOMAIN}/{sid}/{quote(fname, safe='')}"
            html += f'<li><a href="{url}">{fname}</a></li>'
        html += '</ul></body></html>'
        self.send_text(html, 200, 'text/html')

    def show_upload_page(self, token):
        tokens = load_json(TOKENS_FILE)
        
        if token not in tokens:
            self.send_error_page(400, 'Invalid or expired link')
            return
        
        data = tokens[token]
        now = datetime.now()
        
        if now > datetime.fromisoformat(data['expires']):
            self.send_error_page(400, 'Link expired')
            return
        
        if data.get('used'):
            self.send_error_page(400, 'Link already used')
            return
        
        expires_ts = int(datetime.fromisoformat(data['expires']).timestamp())
        
        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Upload File</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
.container{{background:#fff;border-radius:16px;padding:40px;max-width:500px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.3)}}
h1{{color:#1a1a2e;margin-bottom:10px}}
.subtitle{{color:#666;margin-bottom:30px;font-size:14px}}
.dropzone{{border:3px dashed #ccc;border-radius:12px;padding:60px 20px;text-align:center;cursor:pointer;transition:all .3s;background:#fafafa}}
.dropzone:hover{{border-color:#4CAF50;background:#f0fff0}}
.dropzone-icon{{font-size:48px;margin-bottom:10px}}
.dropzone-text{{color:#666;font-size:16px}}
.dropzone-hint{{color:#999;font-size:12px;margin-top:10px}}
input[type=file]{{display:none}}
.file-info{{background:#e3f2fd;border-radius:8px;padding:15px;margin:20px 0;display:none}}
.file-info.show{{display:block}}
.file-name{{font-weight:700;color:#1976d2}}
.file-size{{color:#666;font-size:12px}}
.btn{{width:100%;padding:15px;border:none;border-radius:8px;font-size:16px;font-weight:700;cursor:pointer;transition:all .3s;margin-top:20px}}
.btn-upload{{background:linear-gradient(135deg,#4CAF50,#45a049);color:#fff}}
.btn-upload:hover{{transform:translateY(-2px);box-shadow:0 4px 12px rgba(76,175,80,.4)}}
.btn-upload:disabled{{background:#ccc;cursor:not-allowed;transform:none}}
.progress{{width:100%;height:6px;background:#e0e0e0;border-radius:3px;margin-top:20px;display:none}}
.progress-bar{{height:100%;background:linear-gradient(90deg,#4CAF50,#8BC34A);width:0;transition:width .3s}}
.success{{text-align:center;padding:40px;display:none}}
.success.show{{display:block}}
.success-icon{{font-size:64px;margin-bottom:20px}}
.success-text{{color:#4CAF50;font-size:24px;font-weight:700;margin-bottom:10px}}
.error-box{{background:#ffebee;border-radius:8px;padding:20px;color:#c62828;text-align:center;display:none}}
.error-box.show{{display:block}}
.timer{{text-align:center;margin-top:20px;color:#999;font-size:12px}}
</style></head>
<body>
<div class="container">
<div id="uploadForm">
<h1>Upload File</h1>
<p class="subtitle">One-time secure file upload</p>
<div class="dropzone" id="dropzone">
<div class="dropzone-icon">📁</div>
<div class="dropzone-text">Drag & drop file here</div>
<div class="dropzone-hint">or click to browse - max 50 MB</div>
<input type="file" id="fileInput">
</div>
<div class="file-info" id="fileInfo">
<div class="file-name" id="fileName"></div>
<div class="file-size" id="fileSize"></div>
</div>
<div class="progress" id="progress"><div class="progress-bar" id="progressBar"></div></div>
<button class="btn btn-upload" id="uploadBtn" disabled>Upload File</button>
<div class="timer" id="timer"></div>
</div>
<div class="success" id="success">
<div class="success-icon">✅</div>
<div class="success-text">Upload Complete!</div>
<p>File has been received. This link is now invalid.</p>
</div>
<div class="error-box" id="error"><div id="errorText"></div></div>
</div>
<script>
const expiresTs={expires_ts};
let selectedFile=null;
const timer=document.getElementById('timer');
function updateTimer(){{
const d=expiresTs-Math.floor(Date.now()/1000);
if(d<=0){{timer.textContent='⚠️ Link expired';document.getElementById('uploadBtn').disabled=true;return;}}
timer.textContent=`⏱️ Link expires in ${{Math.floor(d/60)}}m ${{d%60}}s`;
}}
updateTimer();setInterval(updateTimer,1000);
const dropzone=document.getElementById('dropzone');
const fileInput=document.getElementById('fileInput');
dropzone.onclick=()=>fileInput.click();
dropzone.ondragover=e=>{{e.preventDefault();dropzone.style.borderColor='#4CAF50';}};
dropzone.ondragleave=()=>dropzone.style.borderColor='#ccc';
dropzone.ondrop=e=>{{e.preventDefault();dropzone.style.borderColor='#ccc';if(e.dataTransfer.files.length)handleFile(e.dataTransfer.files[0]);}};
fileInput.onchange=e=>{{if(e.target.files.length)handleFile(e.target.files[0]);}};
function handleFile(f){{
selectedFile=f;
document.getElementById('fileName').textContent=f.name;
document.getElementById('fileSize').textContent=(f.size<1024?f.size+' B':f.size<1048576?(f.size/1024).toFixed(1)+' KB':(f.size/1048576).toFixed(1)+' MB');
document.getElementById('fileInfo').classList.add('show');
document.getElementById('uploadBtn').disabled=false;
}}
document.getElementById('uploadBtn').onclick=async()=>{{
if(!selectedFile)return;
const btn=document.getElementById('uploadBtn');
btn.disabled=true;btn.textContent='Uploading...';
document.getElementById('progress').style.display='block';
const fd=new FormData();
fd.append('file',selectedFile);
const xhr=new XMLHttpRequest();
xhr.upload.onprogress=e=>{{if(e.lengthComputable)document.getElementById('progressBar').style.width=(e.loaded/e.total*100)+'%';}};
xhr.onload=()=>{{
if(xhr.status===200){{
document.getElementById('uploadForm').style.display='none';
document.getElementById('success').classList.add('show');
}}else{{
let err='Upload failed';
try{{
const parsed=JSON.parse(xhr.responseText);
if(parsed&&parsed.error)err=parsed.error;
}}catch(e){{
if(xhr.responseText)err=xhr.responseText;
}}
document.getElementById('uploadForm').style.display='none';
document.getElementById('error').classList.add('show');
document.getElementById('errorText').textContent=err;
}}
}};
xhr.onerror=()=>{{document.getElementById('uploadForm').style.display='none';document.getElementById('error').classList.add('show');document.getElementById('errorText').textContent='Network error';}};
            xhr.open('POST','/upload/{token}');
            xhr.send(fd);
        }};
</script>
</body></html>'''
        self.send_text(html, 200, 'text/html')

    def handle_upload(self, token):
        tokens = load_json(TOKENS_FILE)
        
        if token not in tokens:
            self.send_json({'error': 'Invalid token'}, 400)
            return
        
        data = tokens[token]
        now = datetime.now()
        
        if now > datetime.fromisoformat(data['expires']) or data.get('used'):
            self.send_json({'error': 'Token expired or used'}, 400)
            return
        
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > MAX_FILE_SIZE:
            self.send_json({'error': 'File too large (max 50MB)'}, 400)
            return
        
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            self.send_json({'error': 'Expected multipart/form-data'}, 400)
            return
        
        try:
            boundary = content_type.split('boundary=')[1].encode()
        except:
            self.send_json({'error': 'Invalid boundary'}, 400)
            return
        
        body = self.rfile.read(content_length)
        parts = body.split(b'--' + boundary)
        
        filename = None
        file_content = None
        
        for part in parts:
            if b'filename="' in part:
                try:
                    header_end = part.find(b'\r\n\r\n')
                    if header_end == -1:
                        continue
                    headers = part[:header_end].decode('utf-8', errors='replace')
                    content = part[header_end + 4:]
                    
                    fn_start = headers.find('filename="') + 10
                    fn_end = headers.find('"', fn_start)
                    filename = headers[fn_start:fn_end]
                    
                    file_content = content.rstrip(b'\r\n-')
                except Exception as e:
                    print(f"Parse error: {e}")
                break
        
        if not filename or file_content is None:
            self.send_json({'error': 'No file in request'}, 400)
            return
        
        safe_name = os.path.basename(filename)
        if not safe_name:
            safe_name = f"upload_{int(time.time())}"
        
        name, ext = os.path.splitext(safe_name)
        safe_name = f"{name}_{int(time.time())}{ext}"
        
        filepath = os.path.join(UPLOADS_DIR, safe_name)
        with open(filepath, 'wb') as f:
            f.write(file_content)
        
        tokens[token]['used'] = True
        tokens[token]['filename'] = safe_name
        tokens[token]['uploaded_at'] = now.isoformat()
        tokens[token]['size'] = len(file_content)
        save_json(TOKENS_FILE, tokens)
        
        print(f"Uploaded: {safe_name} ({len(file_content)} bytes)")
        self.send_json({'success': True, 'filename': safe_name})

    def create_token(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b'{}'
        
        try:
            data = json.loads(body)
        except:
            data = {}
        
        cleanup_tokens()
        
        token = str(uuid.uuid4())
        now = datetime.now()
        expires = now + timedelta(minutes=TOKEN_TTL_MINUTES)
        
        tokens = load_json(TOKENS_FILE)
        tokens[token] = {
            'created': now.isoformat(),
            'expires': expires.isoformat(),
            'description': data.get('description', ''),
            'used': False
        }
        save_json(TOKENS_FILE, tokens)
        
        url = f"{DOMAIN}/upload/{token}"
        short_url = f"{DOMAIN}?u={token}"
        self.send_json({
            'token': token,
            'url': url,
            'short_url': short_url,
            'html_link': make_link(short_url, "Загрузить"),
            'expires': expires.isoformat()
        })

    def check_token(self, token):
        tokens = load_json(TOKENS_FILE)
        
        if token not in tokens:
            self.send_json({'exists': False, 'error': 'Invalid token'})
            return
        
        data = tokens[token]
        now = datetime.now()
        expired = now > datetime.fromisoformat(data['expires'])
        
        self.send_json({
            'exists': True,
            'used': data.get('used', False),
            'filename': data.get('filename'),
            'expires': data['expires'],
            'expired': expired
        })

    def create_share_link(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b'{}'
        
        try:
            data = json.loads(body)
        except:
            data = {}
        
        filename = os.path.basename(data.get('filename', ''))
        if not filename:
            self.send_json({'error': 'filename required'}, 400)
            return

        source_path = None
        source_session_id = data.get('source_session_id')

        if source_session_id:
            candidate = os.path.join(SESSIONS_DIR, source_session_id, filename)
            if os.path.isfile(candidate):
                source_path = candidate
            else:
                self.send_json({'error': 'source file not found in source_session_id'}, 404)
                return

        if source_path is None:
            upload_candidate = os.path.join(UPLOADS_DIR, filename)
            if os.path.isfile(upload_candidate):
                source_path = upload_candidate

        if source_path is None:
            for existing_sid in os.listdir(SESSIONS_DIR):
                candidate = os.path.join(SESSIONS_DIR, existing_sid, filename)
                if os.path.isfile(candidate):
                    source_path = candidate
                    break

        if source_path is None:
            self.send_json({'error': 'source file not found'}, 404)
            return
        
        cleanup_sessions()
        
        sid = str(uuid.uuid4())
        now = datetime.now()
        expires = now + timedelta(hours=SESSION_TTL_HOURS)
        
        sessions = load_json(SESSIONS_FILE)
        sessions[sid] = {
            'created': now.isoformat(),
            'expires': expires.isoformat(),
            'description': data.get('description', ''),
            'files': [filename]
        }
        save_json(SESSIONS_FILE, sessions)
        
        session_dir = os.path.join(SESSIONS_DIR, sid)
        os.makedirs(session_dir, exist_ok=True)
        shutil.copy2(source_path, os.path.join(session_dir, filename))
        
        url = f"{DOMAIN}/{sid}/{quote(filename, safe='')}"
        download_key = encode_download_key(sid, filename)
        short_url = f"{DOMAIN}/d/{download_key}"
        self.send_json({
            'session_id': sid,
            'url': url,
            'short_url': short_url,
            'html_link': make_link(short_url, "Скачать"),
            'expires': expires.isoformat()
        })


class ReuseAddrServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    cleanup_sessions()
    cleanup_tokens()
    
    print(f"Files server started")
    print(f"Listen: http://{HOST}:{PORT}/")
    print(f"Domain: {DOMAIN}")
    print(f"Upload: {DOMAIN}/upload/<token>")
    print(f"Download: {DOMAIN}/<session>/<file>")
    
    with ReuseAddrServer((HOST, PORT), FileHandler) as httpd:
        httpd.serve_forever()
