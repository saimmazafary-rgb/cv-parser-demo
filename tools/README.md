# Gemini Pro media tool for Claude Code

`gemini_mcp.py` is a small stdio [MCP](https://modelcontextprotocol.io) server
that lets Claude Code send local **images and videos** to Gemini Pro and read
back the answer. Standard library only — no pip install.

## Setup

1. Get an API key at <https://aistudio.google.com/apikey>.
2. Export it in the shell you launch Claude Code from:

   ```bash
   export GEMINI_API_KEY=your-key-here
   ```

3. The server is already registered in [`.mcp.json`](../.mcp.json) at the repo
   root. Start `claude` in this directory and approve the `gemini-media` server
   when prompted. Check it with `/mcp`.

To register it globally instead of per-project:

```bash
claude mcp add gemini-media --scope user \
  --env GEMINI_API_KEY=$GEMINI_API_KEY \
  -- python3 /absolute/path/to/tools/gemini_mcp.py
```

## Tools

| Tool | Use |
|------|-----|
| `gemini_analyze_image` | png / jpg / webp / gif / heic — OCR, screenshots, charts, scanned CVs |
| `gemini_analyze_video` | mp4 / mov / webm / … — summarize, transcribe, describe what happens |

Both take `path` (local file), `prompt`, and optional `model`
(default `gemini-2.5-pro`, overridable with `GEMINI_MODEL`).

Just ask in plain language once the server is connected:

> Use Gemini to read the text out of `samples/scan.jpg`.
> Use Gemini to summarize what happens in `~/Desktop/demo.mp4`.

## How it works

- Files at or under 15 MB are sent inline as base64.
- Larger files (most videos) go through the Gemini **Files API** with a
  resumable upload; the server then polls until the file leaves `PROCESSING`
  before asking the question. Uploaded files expire after ~48 h on Google's side.
- Errors come back as MCP tool errors with the API's message, so a bad key or
  an unsupported format is visible in the transcript rather than silent.

## Manual smoke test

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 tools/gemini_mcp.py
```

## Note on limits

Gemini samples video at ~1 frame/second and counts both frames and audio
toward the context window, so very long videos may need trimming. Media is sent
to Google's API — don't point it at files you can't share with a third party.
