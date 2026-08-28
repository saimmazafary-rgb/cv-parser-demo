#!/usr/bin/env python3
"""Minimal stdio MCP server exposing Gemini image/video understanding and
generation to Claude Code.

Standard library only. Reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the
environment. Models default to gemini-2.5-pro (understanding),
gemini-3-pro-image-preview (image generation) and veo-3.1-generate-preview
(video generation); override with GEMINI_MODEL / GEMINI_IMAGE_MODEL /
GEMINI_VIDEO_MODEL.

Tools:
  gemini_analyze_image   - inline-uploads an image and asks Gemini about it
  gemini_analyze_video   - uploads a video via the Files API, waits for it to
                           finish processing, then asks Gemini about it
  gemini_generate_image  - text-to-image, or image editing when input images
                           are supplied; writes the result to disk
  gemini_generate_video  - text-to-video (or image-to-video) with Veo; polls
                           the long-running operation and downloads the file
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
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
VIDEO_MODEL = os.environ.get("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview")
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


def resolve_out(path, default_ext):
    path = os.path.expanduser(path)
    if not os.path.splitext(path)[1]:
        path += default_ext
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    return path


def generate_image(args):
    """Text-to-image, or editing when input_images are given."""
    parts = [
        media_part(p, "image/png") for p in (args.get("input_images") or [])
    ]
    parts.append({"text": args["prompt"]})
    model = args.get("model") or IMAGE_MODEL
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    if args.get("aspect_ratio"):
        body["generationConfig"]["imageConfig"] = {
            "aspectRatio": args["aspect_ratio"]
        }
    result, _ = request(
        f"{API_ROOT}/v1beta/models/{model}:generateContent?key={api_key()}",
        data=body,
    )
    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"No candidates returned: {json.dumps(result)[:1000]}")

    written, notes = [], []
    out = resolve_out(args["out_path"], ".png")
    stem, ext = os.path.splitext(out)
    for part in candidates[0].get("content", {}).get("parts", []):
        blob = part.get("inlineData") or part.get("inline_data")
        if blob:
            target = out if not written else f"{stem}_{len(written) + 1}{ext}"
            with open(target, "wb") as fh:
                fh.write(base64.b64decode(blob["data"]))
            written.append(target)
        elif part.get("text"):
            notes.append(part["text"].strip())
    if not written:
        raise RuntimeError(
            "Model returned no image. Text was: " + (" ".join(notes) or "(none)")
        )
    lines = ["Wrote " + ", ".join(written)]
    if notes:
        lines.append("Model note: " + " ".join(notes))
    return "\n".join(lines)


def generate_video(args, poll_timeout=900):
    """Veo text-to-video / image-to-video via the long-running operation API."""
    model = args.get("model") or VIDEO_MODEL
    instance = {"prompt": args["prompt"]}
    if args.get("input_image"):
        part = media_part(args["input_image"], "image/png")
        blob = part.get("inline_data")
        if not blob:
            raise RuntimeError("Seed image is too large to send inline")
        instance["image"] = {
            "bytesBase64Encoded": blob["data"],
            "mimeType": blob["mime_type"],
        }
    parameters = {}
    for key, field in (("aspect_ratio", "aspectRatio"),
                       ("negative_prompt", "negativePrompt"),
                       ("resolution", "resolution")):
        if args.get(key):
            parameters[field] = args[key]

    operation, _ = request(
        f"{API_ROOT}/v1beta/models/{model}:predictLongRunning?key={api_key()}",
        data={"instances": [instance], "parameters": parameters},
    )
    name = operation.get("name")
    if not name:
        raise RuntimeError(f"No operation returned: {json.dumps(operation)[:1000]}")

    deadline = time.time() + poll_timeout
    while not operation.get("done"):
        if time.time() > deadline:
            raise RuntimeError(
                f"Video still rendering after {poll_timeout}s. Operation: {name}"
            )
        time.sleep(10)
        operation, _ = request(f"{API_ROOT}/v1beta/{name}?key={api_key()}")
    if operation.get("error"):
        raise RuntimeError(f"Veo failed: {json.dumps(operation['error'])[:1000]}")

    response = operation.get("response", {})
    samples = (
        response.get("generateVideoResponse", {}).get("generatedSamples")
        or response.get("generatedSamples")
        or response.get("videos")
        or []
    )
    if not samples:
        raise RuntimeError(f"No video in response: {json.dumps(response)[:1000]}")

    out = resolve_out(args["out_path"], ".mp4")
    stem, ext = os.path.splitext(out)
    written = []
    for sample in samples:
        video = sample.get("video", sample)
        target = out if not written else f"{stem}_{len(written) + 1}{ext}"
        if video.get("bytesBase64Encoded"):
            data = base64.b64decode(video["bytesBase64Encoded"])
        else:
            uri = video.get("uri") or video.get("gcsUri")
            if not uri:
                raise RuntimeError(f"Sample has no video data: {json.dumps(sample)[:500]}")
            sep = "&" if "?" in uri else "?"
            req = urllib.request.Request(f"{uri}{sep}alt=media&key={api_key()}")
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
        with open(target, "wb") as fh:
            fh.write(data)
        written.append(target)
    return "Wrote " + ", ".join(written)


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
    {
        "name": "gemini_generate_image",
        "description": (
            "Generate an image from a text prompt with Gemini's image model and "
            "save it to out_path. Pass input_images to edit, restyle, or combine "
            "existing images instead of starting from scratch."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "What to generate, or how to edit the inputs.",
                },
                "out_path": {
                    "type": "string",
                    "description": "Where to write the PNG. Extra images get _2, _3 suffixes.",
                },
                "input_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional local image paths to edit or use as reference.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": 'Optional, e.g. "1:1", "16:9", "9:16".',
                },
                "model": {"type": "string", "description": f"Default {IMAGE_MODEL}."},
            },
            "required": ["prompt", "out_path"],
        },
    },
    {
        "name": "gemini_generate_video",
        "description": (
            "Generate a video from a text prompt (or animate a still image) with "
            "Veo and save it to out_path. Takes a few minutes: the call blocks "
            "while polling. Requires an API key with billing enabled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Scene description, including camera and audio cues.",
                },
                "out_path": {
                    "type": "string",
                    "description": "Where to write the MP4.",
                },
                "input_image": {
                    "type": "string",
                    "description": "Optional local image to animate (image-to-video).",
                },
                "negative_prompt": {"type": "string", "description": "What to avoid."},
                "aspect_ratio": {
                    "type": "string",
                    "description": 'Optional, e.g. "16:9" or "9:16".',
                },
                "resolution": {
                    "type": "string",
                    "description": 'Optional, e.g. "720p" or "1080p".',
                },
                "model": {"type": "string", "description": f"Default {VIDEO_MODEL}."},
            },
            "required": ["prompt", "out_path"],
        },
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
        elif name == "gemini_generate_image":
            text = generate_image(args)
        elif name == "gemini_generate_video":
            text = generate_video(args)
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
