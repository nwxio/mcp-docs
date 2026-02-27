#!/usr/bin/env python3
"""
One-time upload server with token-based authentication
"""

import os
import sys
import json
import uuid
import time
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename

HOST = "172.24.1.204"
PORT = 8766
DOMAIN = "https://files.netwize.work"
UPLOADS_DIR = "/files/uploads"
TOKENS_FILE = "/files/tokens.json"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
TOKEN_TTL_MINUTES = 30

os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)


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
    return len(expired)


def create_token(description=""):
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
        'description': description,
        'used': False,
        'filename': None
    }
    save_tokens(tokens)
    return token, expires


def use_token(token):
    tokens = load_tokens()
    if token not in tokens:
        return False, "Invalid token"
    data = tokens[token]
    if datetime.now() > datetime.fromisoformat(data['expires']):
        del tokens[token]
        save_tokens(tokens)
        return False, "Token expired"
    if data['used']:
        return False, "Token already used"
    return True, data


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>File Upload</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #1a1a2e; margin-bottom: 10px; font-size: 28px; }
        .subtitle { color: #666; margin-bottom: 30px; font-size: 14px; }
        .dropzone {
            border: 3px dashed #ccc;
            border-radius: 12px;
            padding: 60px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            background: #fafafa;
        }
        .dropzone:hover, .dropzone.dragover {
            border-color: #4CAF50;
            background: #f0fff0;
        }
        .dropzone.dragover {
            transform: scale(1.02);
        }
        .dropzone-icon { font-size: 48px; margin-bottom: 10px; }
        .dropzone-text { color: #666; font-size: 16px; }
        .dropzone-hint { color: #999; font-size: 12px; margin-top: 10px; }
        input[type="file"] { display: none; }
        .file-info {
            background: #e3f2fd;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            display: none;
        }
        .file-info.show { display: block; }
        .file-name { font-weight: bold; color: #1976d2; }
        .file-size { color: #666; font-size: 12px; }
        .btn {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 20px;
        }
        .btn-upload {
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
        }
        .btn-upload:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(76,175,80,0.4); }
        .btn-upload:disabled { background: #ccc; cursor: not-allowed; transform: none; box-shadow: none; }
        .progress {
            width: 100%;
            height: 6px;
            background: #e0e0e0;
            border-radius: 3px;
            margin-top: 20px;
            display: none;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #4CAF50, #8BC34A);
            width: 0%;
            transition: width 0.3s;
        }
        .success {
            text-align: center;
            padding: 40px;
            display: none;
        }
        .success.show { display: block; }
        .success-icon { font-size: 64px; margin-bottom: 20px; }
        .success-text { color: #4CAF50; font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .success-hint { color: #666; font-size: 14px; }
        .error {
            background: #ffebee;
            border-radius: 8px;
            padding: 20px;
            color: #c62828;
            text-align: center;
            display: none;
        }
        .error.show { display: block; }
        .timer {
            text-align: center;
            margin-top: 20px;
            color: #999;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div id="uploadForm">
            <h1>📤 Upload File</h1>
            <p class="subtitle">One-time secure file upload</p>
            
            <div class="dropzone" id="dropzone">
                <div class="dropzone-icon">📁</div>
                <div class="dropzone-text">Drag & drop file here</div>
                <div class="dropzone-hint">or click to browse • max 50 MB</div>
                <input type="file" id="fileInput" name="file">
            </div>
            
            <div class="file-info" id="fileInfo">
                <div class="file-name" id="fileName"></div>
                <div class="file-size" id="fileSize"></div>
            </div>
            
            <div class="progress" id="progress">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            
            <button class="btn btn-upload" id="uploadBtn" disabled>Upload File</button>
            
            <div class="timer" id="timer"></div>
        </div>
        
        <div class="success" id="success">
            <div class="success-icon">✅</div>
            <div class="success-text">Upload Complete!</div>
            <div class="success-hint">File has been received. This link is now invalid.</div>
        </div>
        
        <div class="error" id="error">
            <div id="errorText"></div>
        </div>
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
        const error = document.getElementById('error');
        const errorText = document.getElementById('errorText');
        const timer = document.getElementById('timer');
        
        let selectedFile = null;
        
        // Timer countdown
        const expiresTs = {{ expires_ts }};
        function updateTimer() {
            const nowTs = Math.floor(Date.now() / 1000);
            const diff = expiresTs - nowTs;
            if (diff <= 0) {
                timer.textContent = "⚠️ Link expired";
                uploadBtn.disabled = true;
                return;
            }
            const mins = Math.floor(diff / 60);
            const secs = Math.floor(diff % 60);
            timer.textContent = `⏱️ Link expires in ${mins}m ${secs}s`;
        }
        updateTimer();
        setInterval(updateTimer, 1000);
        
        // Drag and drop
        dropzone.addEventListener('click', () => fileInput.click());
        
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                handleFile(e.dataTransfer.files[0]);
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                handleFile(e.target.files[0]);
            }
        });
        
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
            
            try {
                const xhr = new XMLHttpRequest();
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percent = (e.loaded / e.total) * 100;
                        progressBar.style.width = percent + '%';
                    }
                });
                
                xhr.addEventListener('load', () => {
                    if (xhr.status === 200) {
                        uploadForm.style.display = 'none';
                        success.classList.add('show');
                    } else {
                        const resp = JSON.parse(xhr.responseText);
                        showError(resp.error || 'Upload failed');
                    }
                });
                
                xhr.addEventListener('error', () => {
                    showError('Network error');
                });
                
                xhr.open('POST', window.location.href);
                xhr.send(formData);
            } catch (e) {
                showError(e.message);
            }
        });
        
        function showError(msg) {
            uploadForm.style.display = 'none';
            error.classList.add('show');
            errorText.textContent = msg;
        }
    </script>
</body>
</html>
'''


@app.route('/upload/<token>', methods=['GET', 'POST'])
def upload(token):
    # Validate token
    valid, data = use_token(token)
    if not valid:
        return render_template_string('''
            <!DOCTYPE html>
            <html><head><title>Error</title>
            <style>
                body { font-family: Arial; background: #1a1a2e; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                .error { background: white; padding: 40px; border-radius: 16px; text-align: center; }
                h1 { color: #c62828; }
                p { color: #666; }
            </style>
            </head><body><div class="error"><h1>⚠️ Invalid Link</h1><p>This upload link is invalid or has expired.</p></div></body></html>
        ''')
    
    if request.method == 'GET':
        expires_ts = data.get('expires_ts', int(datetime.fromisoformat(data['expires']).timestamp()))
        return render_template_string(HTML_TEMPLATE, expires=data['expires'], expires_ts=expires_ts)
    
    # POST - handle upload
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Save file
    filename = secure_filename(file.filename)
    if not filename:
        filename = f"upload_{int(time.time())}"
    
    # Add timestamp to avoid conflicts
    name, ext = os.path.splitext(filename)
    filename = f"{name}_{int(time.time())}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    
    file.save(filepath)
    
    # Mark token as used
    tokens = load_tokens()
    tokens[token]['used'] = True
    tokens[token]['filename'] = filename
    tokens[token]['uploaded_at'] = datetime.now().isoformat()
    tokens[token]['size'] = os.path.getsize(filepath)
    save_tokens(tokens)
    
    print(f"[{datetime.now().isoformat()}] File uploaded: {filename} ({os.path.getsize(filepath)} bytes)")
    
    return jsonify({'success': True, 'filename': filename})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/create_token', methods=['POST'])
def api_create_token():
    """Internal API for MCP server to create tokens"""
    # Simple auth via localhost only
    if request.remote_addr not in ['127.0.0.1', '::1', '172.24.1.204']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    description = request.json.get('description', '') if request.json else ''
    token, expires = create_token(description)
    url = f"{DOMAIN}/upload/{token}"
    
    return jsonify({
        'token': token,
        'url': url,
        'expires': expires.isoformat()
    })


@app.route('/api/check/<token>', methods=['GET'])
def api_check(token):
    """Check if token has been used"""
    if request.remote_addr not in ['127.0.0.1', '::1', '172.24.1.204']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    tokens = load_tokens()
    if token not in tokens:
        return jsonify({'exists': False, 'error': 'Invalid token'})
    
    data = tokens[token]
    return jsonify({
        'exists': True,
        'used': data['used'],
        'filename': data.get('filename'),
        'expires': data['expires'],
        'expired': datetime.now() > datetime.fromisoformat(data['expires'])
    })


if __name__ == '__main__':
    print(f"Upload server starting on {HOST}:{PORT}")
    print(f"Domain: {DOMAIN}")
    print(f"Uploads directory: {UPLOADS_DIR}")
    print(f"Token TTL: {TOKEN_TTL_MINUTES} minutes")
    app.run(host=HOST, port=PORT, debug=False)
