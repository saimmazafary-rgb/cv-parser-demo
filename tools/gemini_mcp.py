#!/usr/bin/env python3
"""Minimal stdio MCP server exposing Gemini Pro image/video analysis.

Standard library only. Reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the
environment; the model defaults to gemini-2.5-pro and can be overridden with
GEMINI_MODEL.

Tools:
  gemini_analyze_image  - inline-uploads an image and asks Gemini about it
  gemini_analyze_video  - uploads a video via the Files API, waits for it to
                          finish processing, then asks Gemini about it
"""

import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
# Anything larger than this goes through the Files API instead of inline bytes.
INLINE_LIMIT = 15 * 1024 * 1024


def api_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)"
        )
    return key


def request(url, data=None, headers=None, method=None, raw=False):
    body = None
    headers = dict(headers or {})
    if data is not None and not raw:
        body = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    elif data is not None:
        body = data
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode() or "{}"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        raise RuntimeError(f"Gemini API {exc.code}: {detail}") from None


def guess_mime(path, fallback):
    return mimetypes.guess_type(path)[0] or fallback


def upload_file(path, mime):
    """Resumable upload through the Files API; returns the file resource."""
    size = os.path.getsize(path)
    _, headers = request(
        f"{API_ROOT}/upload/v1beta/files?key={api_key()}",
        data={"file": {"display_name": os.path.basename(path)}},
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
        },
    )
    upload_url = headers.get("X-Goog-Upload-URL") or headers.get("x-goog-upload-url")
    if not upload_url:
        raise RuntimeError("Files API did not return an upload URL")

    with open(path, "rb") as fh:
        payload = fh.read()
    result, _ = request(
        upload_url,
        data=payload,
        raw=True,
        headers={
            "Content-Length": str(size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
    )
    return result["file"]


def wait_active(file_res, timeout=600):
    """Video uploads are PROCESSING for a while before they can be referenced."""
    name = file_res["name"]
    deadline = time.time() + timeout
    while file_res.get("state") == "PROCESSING":
        if time.time() > deadline:
            raise RuntimeError(f"{name} still PROCESSING after {timeout}s")
        time.sleep(3)
        file_res, _ = request(f"{API_ROOT}/v1beta/{name}?key={api_key()}")
    if file_res.get("state") != "ACTIVE":
        raise RuntimeError(f"{name} failed to process: {file_res.get('state')}")
    return file_res


def media_part(path, fallback_mime):
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        raise RuntimeError(f"No such file: {path}")
    mime = guess_mime(path, fallback_mime)
    if os.path.getsize(path) <= INLINE_LIMIT:
        with open(path, "rb") as fh:
            return {
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(fh.read()).decode(),
                }
            }
    uploaded = wait_active(upload_file(path, mime))
    return {"file_data": {"mime_type": mime, "file_uri": uploaded["uri"]}}


def generate(parts, model):
    result, _ = request(
        f"{API_ROOT}/v1beta/models/{model}:generateContent?key={api_key()}",
        data={"contents": [{"parts": parts}]},
    )
    candidates = result.get("candidates") or []
    if not candidates:
        return json.dumps(result)[:2000]
    return "".join(
        part.get("text", "")
        for part in candidates[0].get("content", {}).get("parts", [])
    ).strip()


def analyze(args, kind):
    fallback = "image/jpeg" if kind == "image" else "video/mp4"
    parts = [media_part(args["path"], fallback), {"text": args["prompt"]}]
    return generate(parts, args.get("model") or DEFAULT_MODEL)


PATH_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Absolute path to the local file."},
        "prompt": {"type": "string", "description": "What to ask Gemini about it."},
        "model": {"type": "string", "description": f"Override (default {DEFAULT_MODEL})."},
    },
    "required": ["path", "prompt"],
}

TOOLS = [
    {
        "name": "gemini_analyze_image",
        "description": (
            "Send a local image (png/jpg/webp/gif/heic) to Gemini Pro with a "
            "prompt and return its text answer. Use for OCR, describing a "
            "screenshot, or reading a chart."
        ),
        "inputSchema": PATH_SCHEMA,
    },
    {
        "name": "gemini_analyze_video",
        "description": (
            "Send a local video (mp4/mov/webm/...) to Gemini Pro with a prompt "
            "and return its text answer. Large files are uploaded via the "
            "Files API, which can take a minute or two to process."
        ),
        "inputSchema": PATH_SCHEMA,
    },
]


def handle(message):
    method = message.get("method")
    if method == "initialize":
        return {
            "protocolVersion": message.get("params", {}).get(
                "protocolVersion", "2025-06-18"
            ),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "gemini-media", "version": "0.1.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = message.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "gemini_analyze_image":
            text = analyze(args, "image")
        elif name == "gemini_analyze_video":
            text = analyze(args, "video")
        else:
            raise RuntimeError(f"Unknown tool: {name}")
        return {"content": [{"type": "text", "text": text}]}
    raise RuntimeError(f"Unsupported method: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in message:  # notification
            continue
        response = {"jsonrpc": "2.0", "id": message["id"]}
        try:
            response["result"] = handle(message)
        except Exception as exc:  # surfaced to the client as a tool error
            response["result"] = {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
