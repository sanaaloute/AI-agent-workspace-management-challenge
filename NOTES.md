# NOTES

**Loop & termination.** The loop in `agent/core.py` runs at most 15 steps. It
stops early as soon as the model returns a message with no tool calls — that
message is the final answer. If the cap is hit, the agent makes one last LLM
call with tools disabled, asking for a best-effort answer from what it has
learned, and marks the run `step_limit` — the user always gets a deliverable,
never a silent hang. 15 is enough for T1/T2 (search → a few reads → one or two
writes) with headroom, small enough to bound cost of a confused model.

**Context strategy.** Full message history is kept, but everything entering it
is pre-truncated at the tool layer: `read_file` never returns more than ~5000
chars (plus a metadata line with total lines / truncation flags),
`search_content` caps at 50 matches with short line previews, `list_directory`
caps at 200 lines. What is *not* put into context: whole files, file bytes
beyond the page requested, and directory metadata beyond names. This keeps
even the 1.3 MB `server.log` cheap: the agent greps it with `search_content`
and reads a small window around the hits.

**Key trade-off.** Paginated reads + substring search instead of
embeddings/RAG. At this scale (a few dozen files, one big log) grep is exact,
has zero extra dependencies, needs no index build, and its results are
inspectable in the trace — reliability and debuggability beat semantic recall
here. RAG would start paying off at thousands of files or fuzzy queries.

**Injection defense.** Initially this was prompt wording only; it is now
structural: every file-content tool result is wrapped in explicit
BEGIN/END FILE DATA markers the prompt references, and a filename denylist
(`.env`, `*.key`, `*.pem`, `id_rsa*`) hard-refuses secret-looking files at
the tool layer, so even a fully jailbroken model cannot read them through
the tools. The residual risk is the model itself obeying injected text —
markers reduce it, they cannot eliminate it.

**Known missing.** No streaming: the UI polls the trace endpoint every second
instead of SSE/WebSocket, which adds ~1 s of latency per step but keeps the
server stateless and the frontend trivial. Also missing: persistent memory
across sessions — everything is in-memory and lost on restart.
