#!/usr/bin/env python3
"""Unified file server: download + upload on single port"""

import http.server
import socketserver
import os
import sys
import json
import uuid
import shutil
import time
from datetime import datetime, timedelta
from urllib.parse import quote, unquote
from werkzeug.utils import secure_filename

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
HOST = "172.24.1.204"
DOMAIN = "https://files.netwize.work"
BASE_DIR = "/files"
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
SESSION_FILE = os.path.join(BASE_DIR, "sessions.json")
TOKENS_FILE = os.path.join(BASE_DIR, "tokens.json")
SESSION_TTL_HOURS = 24
TOKEN_TTL_MINUTES = 30
MAX_FILE_SIZE = 50 * 1024 * 1024

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

def load_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    with open(SESSION_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)

def cleanup_expired_sessions():
    sessions = load_sessions()
    now = datetime.now()
    expired = []
    for sid, data in sessions.items():
        expires = datetime.fromisoformat(data['expires'])
        if now > expires:
            session_path = os.path.join(SESSIONS_DIR, sid)
            if os.path.exists(session_path):
                shutil.rmtree(session_path)
            expired.append(sid)
    for sid in expired:
        del sessions[sid]
    if expired:
        save_sessions(sessions)

def cleanup_expired_tokens():
    tokens = load_tokens()
    now = datetime.now()
    expired = []
    for token, data in tokens.items():
        expires = datetime.fromisoformat(data['expires'])
        if now > expires:
            expired.append(token)
    for token in expired:
        del tokens[token]
    if expired:
        save_tokens(tokens)

UPLOAD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Upload File</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
        .container { background: white; border-radius: 16px; padding: 40px; max-width: 500px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        h1 { color: #1a1a2e; margin-bottom: 10px; font-size: 28px; }
        .subtitle { color: #666; margin-bottom: 30px; font-size: 14px; }
        .dropzone { border: 3px dashed #ccc; border-radius: 12px; padding: 60px 20px; text-align: center; cursor: pointer; transition: all 0.3s; background: #fafafa; }
        .dropzone:hover { border-color: #4CAF50; background: #f0fff0; }
        .dropzone-icon { font-size: 48px; margin-bottom: 10px; }
        .dropzone-text { color: #666; font-size: 16px; }
        .dropzone-hint { color: #999; font-size: 12px; margin-top: 10px; }
        input[type="file"] { display: none; }
        .file-info { background: #e3f2fd; border-radius: 8px; padding: 15px; margin: 20px 0; display: none; }
        .file-info.show { display: block; }
        .file-name { font-weight: bold; color: #1976d2; }
        .file-size { color: #666; font-size: 12px; }
        .btn { width: 100%; padding: 15px; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; transition: all 0.3s; margin-top: 20px; }
        .btn-upload { background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); color: white; }
        .btn-upload:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(76,175,80,0.4); }
        .btn-upload:disabled { background: #ccc; cursor: not-allowed; transform: none; }
        .progress { width: 100%; height: 6px; background: #e0e0e0; border-radius: 3px; margin-top: 20px; display: none; }
        .progress-bar { height: 100%; background: linear-gradient(90deg, #4CAF50, #8BC34A); width: 0%; transition: width 0.3s; }
        .success { text-align: center; padding: 40px; display: none; }
        .success.show { display: block; }
        .success-icon { font-size: 64px; margin-bottom: 20px; }
        .success-text { color: #4CAF50; font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .success-hint { color: #666; font-size: 14px; }
        .error-box { background: #ffebee; border-radius: 8px; padding: 20px; color: #c62828; text-align: center; display: none; }
        .error-box.show { display: block; }
        .timer { text-align: center; margin-top: 20px; color: #999; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div id="uploadForm">
            <h1>&#x1F4E4; Upload File</h1>
            <p class="subtitle">One-time secure file upload</p>
            <div class="dropzone" id="dropzone">
                <div class="dropzone-icon">&#x1F4C1;</div>
                <div class="dropzone-text">Drag & drop file here</div>
                <div class="dropzone-hint">or click to browse - max 50 MB</div>
                <input type="file" id="fileInput" name="file">
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
            <div class="success-hint">File has been received. This link is now invalid.</div>
        </div>
        <div class="error-box" id="error"><div id="errorText"></div></div>
    </div>
    <script>
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const uploadBtn = document.getElementById('uploadBtn');
        const progress = document.getElementById('progress');
        const progressBar = document.getElementById('progressBar');
        const uploadForm = document.getElementById('uploadForm');
        const success = document.getElementById('success');
        const errorBox = document.getElementById('error');
        const errorText = document.getElementById('errorText');
        const timer = document.getElementById('timer');
        let selectedFile = null;
        const expiresTs = {{ expires_ts }};
        function updateTimer() {
            const nowTs = Math.floor(Date.now() / 1000);
            const diff = expiresTs - nowTs;
            if (diff <= 0) { timer.textContent = "⚠️ Link expired"; uploadBtn.disabled = true; return; }
            const mins = Math.floor(diff / 60);
            const secs = Math.floor(diff % 60);
            timer.textContent = `⏱️ Link expires in ${mins}m ${secs}s`;
        }
        updateTimer();
        setInterval(updateTimer, 1000);
        dropzone.addEventListener('click', () => fileInput.click());
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.style.borderColor = '#4CAF50'; });
        dropzone.addEventListener('dragleave', () => { dropzone.style.borderColor = '#ccc'; });
        dropzone.addEventListener('drop', (e) => { e.preventDefault(); dropzone.style.borderColor = '#ccc'; if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]); });
        fileInput.addEventListener('change', (e) => { if (e.target.files.length) handleFile(e.target.files[0]); });
        function handleFile(file) {
            selectedFile = file;
            fileName.textContent = file.name;
            fileSize.textContent = formatSize(file.size);
            fileInfo.classList.add('show');
            uploadBtn.disabled = false;
        }
        function formatSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }
        uploadBtn.addEventListener('click', async () => {
            if (!selectedFile) return;
            const formData = new FormData();
            formData.append('file', selectedFile);
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
            progress.style.display = 'block';
            const xhr = new XMLHttpRequest();
            xhr.upload.addEventListener('progress', (e) => { if (e.lengthComputable) progressBar.style.width = (e.loaded / e.total * 100) + '%'; });
            xhr.addEventListener('load', () => {
                if (xhr.status === 200) { uploadForm.style.display = 'none'; success.classList.add('show'); }
                else { const resp = JSON.parse(xhr.responseText); showError(resp.error || 'Upload failed'); }
            });
            xhr.addEventListener('error', () => showError('Network error'));
            xhr.open('POST', window.location.href);
            xhr.send(formData);
        });
        function showError(msg) { uploadForm.style.display = 'none'; errorBox.classList.add('show'); errorText.textContent = msg; }
    </script>
</body>
</html>
'''

ERROR_HTML = '''
<!DOCTYPE html>
<html><head><title>Error</title>
<style>body{font-family:Arial;background:#1a1a2e;min-height:100vh;display:flex;align-items:center;justify-content:center;}.error{background:white;padding:40px;border-radius:16px;text-align:center;}h1{color:#c62828;}p{color:#666;}</style>
</head><body><div class="error"><h1>⚠️ Invalid Link</h1><p>This upload link is invalid or has expired.</p></div></body></html>
'''


class UnifiedHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SESSIONS_DIR, **kwargs)
    
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")
    
    def do_GET(self):
        path = unquote(self.path)
        
        if path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        
        # Upload page: /upload/<token>
        if path.startswith('/upload/'):
            token = path[8:].split('?')[0].rstrip('/')
            tokens = load_tokens()
            if token not in tokens:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(ERROR_HTML.encode('utf-8'))
                return
            data = tokens[token]
            if datetime.now() > datetime.fromisoformat(data['expires']):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(ERROR_HTML.encode('utf-8'))
                return
            if data.get('used'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(ERROR_HTML.encode('utf-8'))
                return
            expires_ts = data.get('expires_ts', int(datetime.fromisoformat(data['expires']).timestamp()))
            html = UPLOAD_HTML.replace('{{ expires_ts }}', str(expires_ts))
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return
        
        # List sessions: /
        if path == '/' or path == '':
            self.list_sessions()
            return
        
        # Download: /<session_id>/<filename>
        parts = path.strip('/').split('/', 1)
        if len(parts) >= 1 and parts[0]:
            sid = parts[0]
            session_path = os.path.join(SESSIONS_DIR, sid)
            if not os.path.exists(session_path):
                self.send_error(404, "Session not found")
                return
            if len(parts) == 1:
                self.list_session_files(sid)
                return
            filename = parts[1]
            file_path = os.path.join(session_path, filename)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_file(file_path, filename)
                return
            self.send_error(404, "File not found")
            return
        
        self.send_error(404, "Not found")
    
    def do_POST(self):
        path = unquote(self.path)
        
        # Upload file: /upload/<token>
        if path.startswith('/upload/'):
            token = path[8:].rstrip('/')
            tokens = load_tokens()
            if token not in tokens:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid token"}')
                return
            data = tokens[token]
            if datetime.now() > datetime.fromisoformat(data['expires']) or data.get('used'):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "Token expired or used"}')
                return
            
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > MAX_FILE_SIZE:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "File too large"}')
                return
            
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "No multipart form data"}')
                return
            
            # Parse multipart
            boundary = content_type.split('boundary=')[1].encode()
            body = self.rfile.read(content_length)
            
            # Extract file
            parts = body.split(b'--' + boundary)
            filename = None
            file_content = None
            
            for part in parts:
                if b'filename=' in part:
                    headers, _, content = part.partition(b'\r\n\r\n')
                    fn_match = headers.split(b'filename="')[1].split(b'"')[0]
                    filename = fn_match.decode('utf-8', errors='replace')
                    file_content = content.rstrip(b'\r\n')
                    break
            
            if not filename or file_content is None:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "No file in request"}')
                return
            
            # Save file
            filename = secure_filename(filename) or f"upload_{int(time.time())}"
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"
            filepath = os.path.join(UPLOADS_DIR, filename)
            
            with open(filepath, 'wb') as f:
                f.write(file_content)
            
            # Mark token used
            tokens[token]['used'] = True
            tokens[token]['filename'] = filename
            tokens[token]['uploaded_at'] = datetime.now().isoformat()
            tokens[token]['size'] = len(file_content)
            save_tokens(tokens)
            
            print(f"[{datetime.now().isoformat()}] File uploaded: {filename}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'filename': filename}).encode())
            return
        
        # API: create token
        if path == '/api/create_token':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body) if body else {}
            except:
                data = {}
            
            cleanup_expired_tokens()
            token = str(uuid.uuid4())
            now = datetime.now()
            expires = now + timedelta(minutes=TOKEN_TTL_MINUTES)
            expires_ts = int(expires.timestamp())
            
            tokens = load_tokens()
            tokens[token] = {
                'created': now.isoformat(),
                'expires': expires.isoformat(),
                'expires_ts': expires_ts,
                'description': data.get('description', ''),
                'used': False,
                'filename': None
            }
            save_tokens(tokens)
            
            url = f"{DOMAIN}/upload/{token}"
            response = {'token': token, 'url': url, 'expires': expires.isoformat()}
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            return
        
        # API: check token
        if path.startswith('/api/check/'):
            token = path[11:]
            tokens = load_tokens()
            if token not in tokens:
                response = {'exists': False, 'error': 'Invalid token'}
            else:
                data = tokens[token]
                response = {
                    'exists': True,
                    'used': data.get('used', False),
                    'filename': data.get('filename'),
                    'expires': data['expires'],
                    'expired': datetime.now() > datetime.fromisoformat(data['expires'])
                }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            return
        
        self.send_error(404, "Not found")
    
    def list_sessions(self):
        cleanup_expired_sessions()
        sessions = load_sessions()
        html = """<!DOCTYPE html><html><head><title>Files</title>
<style>body{font-family:Arial,sans-serif;margin:40px;background:#f5f5f5;}.container{max-width:800px;margin:0 auto;background:white;padding:20px;border-radius:8px;}h1{color:#333;}.session{margin:20px 0;padding:15px;background:#fafafa;border-left:4px solid #4CAF50;}.session h3{margin:0 0 10px 0;}.meta{font-size:12px;color:#666;margin-bottom:10px;}.files{list-style:none;padding:0;}.files li{margin:5px 0;}.files a{color:#0066cc;text-decoration:none;}.files a:hover{text-decoration:underline;}</style></head><body><div class="container"><h1>Shared Files</h1>"""
        if sessions:
            for sid, data in sessions.items():
                html += f'<div class="session"><h3>Session: {sid[:8]}...</h3><div class="meta">Files: {len(data["files"])} | Expires: {data["expires"][:19]}</div><ul class="files">'
                for fname in data['files']:
                    url = f"{DOMAIN}/{sid}/{quote(fname)}"
                    html += f'<li><a href="{url}">{fname}</a></li>'
                html += '</ul></div>'
        else:
            html += '<p>No active sessions</p>'
        html += '</div></body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def list_session_files(self, sid):
        sessions = load_sessions()
        if sid not in sessions:
            self.send_error(404, "Session not found")
            return
        data = sessions[sid]
        html = f"""<!DOCTYPE html><html><head><title>Session {sid[:8]}</title>
<style>body{{font-family:Arial,sans-serif;margin:40px;}}ul{{list-style:none;padding:0;}}li{{margin:10px 0;}}a{{color:#0066cc;text-decoration:none;font-size:16px;}}a:hover{{text-decoration:underline;}}.meta{{color:#666;margin-bottom:20px;}}</style></head><body><h1>Files</h1><div class="meta">Session: {sid}<br>Expires: {data['expires'][:19]}</div><ul>"""
        for fname in data['files']:
            url = f"{DOMAIN}/{sid}/{quote(fname)}"
            html += f'<li><a href="{url}">{fname}</a></li>'
        html += '</ul></body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def serve_file(self, filepath, filename):
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(size))
        self.end_headers()
        with open(filepath, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)


class ReuseAddrServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    cleanup_expired_sessions()
    cleanup_expired_tokens()
    print(f"Unified file server started")
    print(f"Listening on: http://{HOST}:{PORT}/")
    print(f"Domain: {DOMAIN}")
    print(f"Upload: {DOMAIN}/upload/<token>")
    print(f"Download: {DOMAIN}/<session>/<file>")
    
    with ReuseAddrServer((HOST, PORT), UnifiedHandler) as httpd:
        httpd.serve_forever()
