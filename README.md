# AI File Agent

[中文文档](README.zh-CN.md)

A general-purpose file agent: give it a natural-language task and it operates
on a `workspace/` directory through five tools (list, read, search, write,
move). The agent loop — model returns tool calls → execute → append results →
decide continue/stop — is **hand-written Python**. No LangChain / LangGraph /
CrewAI / Agents SDK / `tool_runner`; the `openai` SDK is used only as an HTTP
client against any OpenAI-compatible endpoint.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # set LLM_PROVIDER (openai | openrouter | ollama)
                         # and LLM_API_KEY; LLM_BASE_URL / LLM_MODEL optional
```

Run a task from the CLI (workspace path is configurable; writes `trace.jsonl`
with one `{"step","tool","args","result_summary"}` JSON object per step):

```bash
python cli.py --workspace ./workspace --task "Find every file mentioning 'Project Falcon' and build falcon_index.md grouped by month"
```

Run the web demo:

```bash
docker compose up -d --build     # -> http://localhost:8000
# or bare metal: uvicorn ui.server:app
```

Deploying behind nginx on a VPS: see `deploy/`.

## Features

- Hand-written tool-calling loop: 15-step cap, stops when the model stops
  calling tools, best-effort final answer when the cap or token budget is hit
- Five workspace-sandboxed tools; `..` escapes and secret-looking filenames
  (`.env`, `*.key`, `*.pem`, ...) are refused at the tool layer
- Prompt-injection hardening: file content is wrapped in explicit
  untrusted-data markers and treated as data, never as instructions
- Big-file strategy: paginated `read_file` + substring `search_content`, so a
  1.3 MB log never enters the context whole
- Web UI: chat-style task thread, live step-by-step mission log (tool, args,
  result summary), collapsible file explorer with file viewer, create folder /
  upload / delete / reset, draggable sidebars, LLM-call and token counters
- Three LLM providers by config only: OpenAI, OpenRouter, Ollama Cloud
  (hosted ollama.com API, not a local daemon)
- Dummy workspace generator (`scripts/generate_workspace.py`, 32 files) with
  built-in traps: injection bait, a huge log, conflicting dates, decoys

## Security / abuse prevention (public demo)

The demo API is unauthenticated by design; abuse is bounded by a per-session
token budget (`TOKEN_BUDGET`, default 200k tokens — the run aborts gracefully)
and nginx rate limiting on `/api/` (`deploy/nginx-http-snippet.conf`). All
file operations are sandboxed to the workspace.

## Not done / with 2 more hours

- No streaming (SSE/WebSocket) — the UI polls `/api/trace` once a second.
- No persistent memory across sessions; sessions live in an in-memory dict.
- No auth at all on the demo API; per-user rate limiting only via nginx.

Design notes (loop termination, context strategy, trade-offs): see `NOTES.md`.
