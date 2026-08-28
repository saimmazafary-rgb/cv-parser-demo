# Gemini media tools for Claude Code

`gemini_mcp.py` is a small stdio [MCP](https://modelcontextprotocol.io) server
that lets Claude Code **generate** images and videos with Gemini and Veo, and
**analyze** local images and videos. Standard library only — no pip install.

> **A Google AI Pro subscription is not API access.** The subscription covers
> the Gemini app; this server talks to the Gemini API, which is billed against
> an AI Studio key. Image generation and understanding have a free tier; **Veo
> video generation requires billing enabled on the key.**

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

| Tool | Use | Default model |
|------|-----|---------------|
| `gemini_generate_image` | text→image, or edit/restyle/combine images you pass in | `gemini-3-pro-image-preview` |
| `gemini_generate_video` | text→video, or animate a still image | `veo-3.1-generate-preview` |
| `gemini_analyze_image` | OCR, screenshots, charts, scanned CVs | `gemini-2.5-pro` |
| `gemini_analyze_video` | summarize, transcribe, describe what happens | `gemini-2.5-pro` |

Every tool takes an optional `model`; the defaults come from `GEMINI_IMAGE_MODEL`,
`GEMINI_VIDEO_MODEL`, and `GEMINI_MODEL`. Generation tools take `prompt` and
`out_path` (extension optional — `.png`/`.mp4` is added, and parent directories
are created). Analysis tools take `path` and `prompt`.

Just ask in plain language once the server is connected:

> Generate a 16:9 hero image of a desk with scattered CVs, save it to `assets/hero.png`.
> Take `assets/hero.png` and make the lighting warmer.
> Make a 9:16 video of the camera slowly pushing in on that desk, save to `assets/hero.mp4`.
> Use Gemini to read the text out of `samples/scan.jpg`.

## How it works

- **Image generation** is one `generateContent` call with
  `responseModalities: ["TEXT", "IMAGE"]`; returned `inlineData` parts are
  base64-decoded straight to disk. Passing `input_images` puts them in the same
  request, which is how editing works — there is no separate edit endpoint.
- **Video generation** posts to `:predictLongRunning`, then polls the operation
  every 10 s (up to 15 min) and downloads the finished file. Expect a few
  minutes per clip; the tool call blocks for that whole time.
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
