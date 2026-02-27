#!/usr/bin/env python3
"""HTTP server with session-based file sharing"""

import http.server
import socketserver
import os
import sys
import json
import uuid
import shutil
from datetime import datetime, timedelta
from urllib.parse import quote, unquote

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
HOST = "172.24.1.204"
DOMAIN = "https://files.netwize.work"
BASE_DIR = "/files"
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SHARED_DIR = os.path.join(BASE_DIR, "shared")
SESSION_FILE = os.path.join(BASE_DIR, "sessions.json")
SESSION_TTL_HOURS = 24

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)

def load_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    with open(SESSION_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)

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

def create_session(description=""):
    cleanup_expired_sessions()
    sid = str(uuid.uuid4())
    session_path = os.path.join(SESSIONS_DIR, sid)
    os.makedirs(session_path, exist_ok=True)
    sessions = load_sessions()
    sessions[sid] = {
        'created': datetime.now().isoformat(),
        'expires': (datetime.now() + timedelta(hours=SESSION_TTL_HOURS)).isoformat(),
        'description': description,
        'files': []
    }
    save_sessions(sessions)
    return sid

def add_file_to_session(sid, filename, content=None, source_path=None):
    session_path = os.path.join(SESSIONS_DIR, sid)
    if not os.path.exists(session_path):
        return None
    
    file_path = os.path.join(session_path, filename)
    
    if content is not None:
        with open(file_path, 'wb') as f:
            if isinstance(content, str):
                f.write(content.encode('utf-8'))
            else:
                f.write(content)
    elif source_path and os.path.exists(source_path):
        shutil.copy2(source_path, file_path)
    else:
        return None
    
    sessions = load_sessions()
    if sid in sessions:
        sessions[sid]['files'].append(filename)
        save_sessions(sessions)
    
    return f"{DOMAIN}/{sid}/{quote(filename)}"

def list_session_files(sid):
    sessions = load_sessions()
    if sid not in sessions:
        return None
    return sessions[sid]['files']

class SessionHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SESSIONS_DIR, **kwargs)
    
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")
    
    def do_GET(self):
        path = unquote(self.path)
        
        if path == '/' or path == '':
            self.list_sessions()
            return
        
        if path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            return
        
        parts = path.strip('/').split('/', 1)
        if len(parts) >= 1 and parts[0]:
            sid = parts[0]
            session_path = os.path.join(SESSIONS_DIR, sid)
            
            if not os.path.exists(session_path):
                self.send_error(404, "Session not found")
                return
            
            if len(parts) == 1:
                self.list_session_files_page(sid)
                return
            
            filename = parts[1]
            file_path = os.path.join(session_path, filename)
            
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.serve_file(file_path, filename)
                return
            else:
                self.send_error(404, "File not found")
                return
        
        self.send_error(404, "Not found")
    
    def list_sessions(self):
        cleanup_expired_sessions()
        sessions = load_sessions()
        
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Shared Files</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; }
        .session { margin: 20px 0; padding: 15px; background: #fafafa; border-left: 4px solid #4CAF50; }
        .session h3 { margin: 0 0 10px 0; }
        .session .meta { font-size: 12px; color: #666; margin-bottom: 10px; }
        .files { list-style: none; padding: 0; }
        .files li { margin: 5px 0; }
        .files a { color: #0066cc; text-decoration: none; }
        .files a:hover { text-decoration: underline; }
        .expired { border-left-color: #f44336; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Shared Files Server</h1>
"""
        
        if sessions:
            for sid, data in sessions.items():
                expires = datetime.fromisoformat(data['expires'])
                is_expired = datetime.now() > expires
                
                html += f"""
        <div class="session {'expired' if is_expired else ''}">
            <h3>Session: {sid[:8]}...</h3>
            <div class="meta">
                Created: {data['created'][:19]} | 
                Expires: {data['expires'][:19]} |
                Files: {len(data['files'])}
            </div>
            <ul class="files">
"""
                for fname in data['files']:
                    url = f"{DOMAIN}/{sid}/{quote(fname)}"
                    html += f'                <li><a href="{url}">{fname}</a></li>\n'
                
                html += """            </ul>
        </div>
"""
        else:
            html += "<p>No active sessions</p>"
        
        html += """
    </div>
</body>
</html>"""
        
        encoded = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
    
    def list_session_files_page(self, sid):
        sessions = load_sessions()
        if sid not in sessions:
            self.send_error(404, "Session not found")
            return
        
        data = sessions[sid]
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Session {sid[:8]}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ margin: 10px 0; }}
        a {{ color: #0066cc; text-decoration: none; font-size: 16px; }}
        a:hover {{ text-decoration: underline; }}
        .meta {{ color: #666; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>Files in Session</h1>
    <div class="meta">
        Session ID: {sid}<br>
        Created: {data['created'][:19]}<br>
        Expires: {data['expires'][:19]}
    </div>
    <ul>
"""
        for fname in data['files']:
            url = f"{DOMAIN}/{sid}/{quote(fname)}"
            html += f'        <li><a href="{url}">{fname}</a></li>\n'
        
        html += """    </ul>
</body>
</html>"""
        
        encoded = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
    
    def serve_file(self, file_path, filename):
        file_size = os.path.getsize(file_path)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(file_size))
        self.end_headers()
        
        with open(file_path, 'rb') as f:
            shutil.copyfileobj(f, self.wfile)

print(f"Files server started")
print(f"Listening on: http://{HOST}:{PORT}/")
print(f"Domain: {DOMAIN}")
print(f"Sessions directory: {SESSIONS_DIR}")
print(f"Session TTL: {SESSION_TTL_HOURS} hours")
print("Press Ctrl+C to stop")

cleanup_expired_sessions()

class ReuseAddrServer(socketserver.TCPServer):
    allow_reuse_address = True

with ReuseAddrServer((HOST, PORT), SessionHandler) as httpd:
    httpd.serve_forever()
