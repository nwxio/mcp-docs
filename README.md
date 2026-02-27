# MCP Docs 

MCPDocs is a multi-server toolkit for document processing, file upload/download workflows, and session-based file sharing.

It is designed for MCP-compatible AI clients and includes:

- MCP servers for document I/O, upload links, file processing, and sharing.
- An HTTP file backend for one-time uploads and downloadable share links.
- Demo file generators for testing real DOCX/XLSX/PDF/CSV/TXT workflows.

## Key Capabilities

- Read and create document formats (`txt`, `csv`, `docx`, `xlsx`, `pdf`).
- Create one-time upload links (TTL-based, single use).
- Process uploaded files with type autodetection.
- Share files with expiring session links.
- Generate downloadable short links.
- Operate all of the above through MCP tools.

## Components

### MCP servers

1. `mcp_server.py` (`Server("doc-tools")`)
   - General document tools:
     - `read_txt`, `read_csv`, `read_docx`, `read_xlsx`, `read_pdf`
     - `create_txt`, `create_csv`, `create_docx`, `create_xlsx`
     - `append_to_txt`, `append_to_csv`
     - `list_directory`, `get_file_info`

2. `file_upload_server.py` (`Server("file-upload")`)
   - One-time upload flow tools:
     - `create_upload_link`, `check_upload`, `process_upload`, `list_uploads`, `delete_upload`

3. `file_processor_server.py` (`Server("file-processor")`)
   - Upload folder scanning and processing:
     - `scan_uploads`, `process_uploaded_file`, `process_all_uploads`, `get_upload_path`

4. `file_share_server.py` (`Server("file-share")`)
   - Session-based sharing tools:
     - `share_file`, `create_and_share`, `create_binary_and_share`
     - `create_session`, `list_sessions`, `get_session_links`, `cleanup_sessions`, `share_directory`

### HTTP backend

- `files_server.py` (recommended backend)
  - Handles upload pages, token checks, session-based downloads, short links, and basic API endpoints.
  - Default bind: `172.24.1.204:8765`
  - Default public domain in links: `https://files.your-server.work`
  - Storage root: `/files`

### Legacy/alternative servers

- `unified_server.py` - alternative combined upload/download server.
- `file_server.py` - session-based download server.
- `upload_server.py` - Flask-based upload server.
- `serve.py` - simple static download server.

## Architecture

1. MCP clients connect to one or more stdio MCP servers.
2. Upload/share MCP servers use filesystem state in `/files`.
3. HTTP file backend serves upload forms and download links.
4. Session and token metadata is persisted in JSON files:
   - `/files/sessions.json`
   - `/files/tokens.json`

## Requirements

### Python

- Python 3.11+

### Python packages

Install baseline dependencies:

```bash
pip install -r requirements.txt
```

Install additional runtime dependencies used by upload/share/preview paths:

```bash
pip install flask requests reportlab pillow werkzeug
```

Notes:

- `requirements.txt` includes core document stack (`mcp`, `python-docx`, `openpyxl`, `pdfplumber`, `pandas`).
- `reportlab` is required for `create_binary_and_share` PDF generation.
- `Pillow` is required for image metadata processing in `file_processor_server.py`.

## Quick Start

### 1) Prepare environment

```bash
cd /home/projects/mcpdocs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install flask requests reportlab pillow werkzeug
```

### 2) Prepare storage directories

```bash
sudo mkdir -p /files/sessions /files/shared /files/uploads
sudo chmod -R 777 /files
```

### 3) Start HTTP file backend

```bash
python files_server.py
```

Health check:

```bash
curl http://172.24.1.204:8765/health
```

### 4) Start MCP servers (in separate terminals)

```bash
python mcp_server.py
python file_upload_server.py
python file_processor_server.py
python file_share_server.py
```

### 5) Add servers to OpenCode (CLI method)

Run this for each MCP server you want to connect:

```bash
opencode mcp add
```

Use these command values when prompted:

- `doc-tools`: `/home/projects/mcpdocs/.venv/bin/python /home/projects/mcpdocs/mcp_server.py`
- `file-upload`: `/home/projects/mcpdocs/.venv/bin/python /home/projects/mcpdocs/file_upload_server.py`
- `file-processor`: `/home/projects/mcpdocs/.venv/bin/python /home/projects/mcpdocs/file_processor_server.py`
- `file-share`: `/home/projects/mcpdocs/.venv/bin/python /home/projects/mcpdocs/file_share_server.py`

### 6) Verify MCP connection

```bash
opencode mcp list
```

Expected: all added servers show as connected.

## OpenCode MCP Configuration Example

Use absolute paths in your MCP config:

```json
{
  "mcpServers": {
    "doc-tools": {
      "command": "/home/projects/mcpdocs/.venv/bin/python",
      "args": ["/home/projects/mcpdocs/mcp_server.py"]
    },
    "file-upload": {
      "command": "/home/projects/mcpdocs/.venv/bin/python",
      "args": ["/home/projects/mcpdocs/file_upload_server.py"]
    },
    "file-processor": {
      "command": "/home/projects/mcpdocs/.venv/bin/python",
      "args": ["/home/projects/mcpdocs/file_processor_server.py"]
    },
    "file-share": {
      "command": "/home/projects/mcpdocs/.venv/bin/python",
      "args": ["/home/projects/mcpdocs/file_share_server.py"]
    }
  }
}
```

## End-to-End Flows

### Flow A: Upload -> Process -> Share

1. Call `create_upload_link`.
2. User uploads file via generated URL.
3. Poll `check_upload` until uploaded.
4. Read content with `process_upload` or `process_uploaded_file`.
5. Share with `share_file` or `create_and_share`.

### Flow B: Direct document generation

1. Create file via `create_txt` / `create_csv` / `create_docx` / `create_xlsx`.
2. Verify with `get_file_info` or `read_*` tools.
3. Publish via `share_file`.

## HTTP Endpoints (files_server.py)

- `GET /health` - backend health.
- `GET /upload/<token>` - upload page for one-time token.
- `POST /upload/<token>` - submit upload.
- `POST /api/create_token` (or `/api/token`) - create upload token.
- `GET|POST /api/check/<token>` - check upload token status.
- `POST /api/share` - create session-based share link.
- `GET /d/<download_key>` - short download bridge URL.
- `GET /<session_id>/<filename>` - direct download.

## Demo Data

Generate realistic test documents:

```bash
python create_test_files.py
```

Output is created in `test_files/` and includes DOCX/XLSX/PDF/CSV/TXT samples.

## Project Structure

```text
mcpdocs/
├── README.md
├── requirements.txt
├── mcp_server.py
├── file_upload_server.py
├── file_processor_server.py
├── file_share_server.py
├── files_server.py
├── unified_server.py
├── file_server.py
├── upload_server.py
├── serve.py
├── create_test_files.py
├── test_files/
└── uploads/
```

## Operational Notes

- Hardcoded values (`HOST`, `DOMAIN`, `BASE_DIR`) are currently set inside scripts.
- If deploying to another host/domain, update constants in server files.
- Session TTL defaults to 24 hours; upload token TTL defaults to 30 minutes.
- Max upload size defaults to 50 MB.

## Security Notes

- Upload links are single-use and time-limited.
- Files are stored on local disk under `/files`.
- APIs in `upload_server.py` allow localhost/internal host checks only.
- For public deployment, add reverse proxy auth/rate limiting/TLS controls as needed.

## Troubleshooting

- `create_upload_link` fails:
  - Ensure `files_server.py` is running at `http://172.24.1.204:8765`.
- `process_upload` says file not found:
  - Confirm upload completed (`check_upload`) and file exists in `/files/uploads`.
- No share links returned:
  - Verify write permissions for `/files/sessions` and `/files/sessions.json`.
- PDF/image features failing:
  - Install missing extras: `reportlab` and `pillow`.

## License

No license file is currently included in this repository.
Add a `LICENSE` file before publishing publicly on GitHub.
