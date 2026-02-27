#!/usr/bin/env python3
"""Simple HTTP server for file downloads"""

import http.server
import socketserver
import os
import sys
from urllib.parse import quote

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
DIRECTORY = sys.argv[2] if len(sys.argv) > 2 else "."
HOST = "172.24.1.204"
DOMAIN = "https://files.netwize.work"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")
    
    def list_directory(self, path):
        """Custom directory listing with domain URLs"""
        try:
            listdir = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
        
        listdir.sort(key=lambda a: a.lower())
        f = []
        for name in listdir:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
            href = f"{DOMAIN}:{PORT}/{quote(linkname)}"
            f.append(f'<li><a href="{href}">{displayname}</a></li>')
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Directory listing for {HOST}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ margin: 10px 0; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>Download Files</h1>
    <ul>
        {''.join(f)}
    </ul>
</body>
</html>"""
        encoded = html.encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

print(f"Serving files from: {os.path.abspath(DIRECTORY)}")
print(f"URL: http://{HOST}:{PORT}/")
print(f"Download links use: {DOMAIN}:{PORT}/")
print("Press Ctrl+C to stop")

with socketserver.TCPServer((HOST, PORT), Handler) as httpd:
    httpd.serve_forever()
