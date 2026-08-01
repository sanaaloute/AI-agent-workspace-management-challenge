"""FastAPI app: serves the single-page UI plus the agent API.

Runnable both as:
    python ui/server.py
    uvicorn ui.server:app
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
import uuid
from pathlib import Path

# Make `agent` importable when run as `python ui/server.py` from anywhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.config import get_settings
from agent.core import Agent
from agent.tools import is_denied_name
from agent.utils import reset_workspace

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("file-agent-server")

SETTINGS = get_settings()
WORKSPACE = SETTINGS.workspace_dir
WORKSPACE_ORIGINAL = SETTINGS.workspace_original_dir
MAX_FILE_BYTES = 100 * 1024  # cap for /api/file responses

app = FastAPI(title="AI File Agent")
app.mount("/static", StaticFiles(directory=ROOT / "ui" / "static"), name="static")

# In-memory sessions: fine for a single-process demo.
sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()


class RunRequest(BaseModel):
    task: str


def _resolve_in_workspace(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents:
        raise HTTPException(status_code=400, detail="path escapes the workspace")
    return p


@app.get("/")
def index() -> FileResponse:
    # no-store: the UI changes often; never let a browser or proxy serve a
    # stale index.html (a stale page looks like "buttons do nothing").
    return FileResponse(
        ROOT / "ui" / "static" / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/run", status_code=202)
def run_task(req: RunRequest):
    task = req.task.strip()
    if not task:
        raise HTTPException(status_code=400, detail="task must be non-empty")

    session_id = uuid.uuid4().hex[:12]
    with _sessions_lock:
        sessions[session_id] = {
            "status": "running",
            "task": task,
            "steps": [],
            "final_answer": None,
            "llm_calls": 0,
            "total_tokens": 0,
        }

    def worker() -> None:
        session = sessions[session_id]
        try:
            agent = Agent(workspace=WORKSPACE, settings=SETTINGS)

            def on_step(record) -> None:
                session["steps"].append(record.to_dict())

            result = agent.run(task, on_step=on_step)
            session["final_answer"] = result.final_answer
            session["llm_calls"] = result.llm_calls
            session["total_tokens"] = result.total_tokens
            # step_limit/aborted_budget are finished runs with a deliverable;
            # "error" (e.g. provider timeout mid-run) is shown as an error.
            session["status"] = "error" if result.status == "error" else "done"
            session["finish_reason"] = result.status
        except Exception as e:
            log.exception("agent run failed")
            session["status"] = "error"
            session["final_answer"] = f"Agent run failed: {e}"

    threading.Thread(target=worker, daemon=True).start()
    return {"session_id": session_id}


@app.get("/api/trace/{session_id}")
def get_trace(session_id: str):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    return {
        "status": session["status"],
        "steps": session["steps"],
        "final_answer": session["final_answer"],
        "llm_calls": session["llm_calls"],
        "total_tokens": session["total_tokens"],
    }


def _tree(dir_path: Path) -> dict:
    node = {"name": dir_path.name, "type": "dir", "children": []}
    try:
        entries = sorted(dir_path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except OSError:
        return node
    for entry in entries:
        if entry.is_dir():
            child = _tree(entry)
            child["path"] = entry.relative_to(WORKSPACE).as_posix()
            node["children"].append(child)
        else:
            node["children"].append(
                {
                    "name": entry.name,
                    "type": "file",
                    "path": entry.relative_to(WORKSPACE).as_posix(),
                    "size": entry.stat().st_size,
                }
            )
    return node


@app.get("/api/files")
def list_files():
    if not WORKSPACE.is_dir():
        raise HTTPException(status_code=500, detail=f"workspace missing: {WORKSPACE}")
    return _tree(WORKSPACE)


@app.get("/api/file")
def read_workspace_file(path: str = Query(...)):
    p = _resolve_in_workspace(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {path}")
    size = p.stat().st_size
    truncated = size > MAX_FILE_BYTES
    with p.open("rb") as fh:
        data = fh.read(MAX_FILE_BYTES)
    return {
        "path": path,
        "size": size,
        "truncated": truncated,
        "content": data.decode("utf-8", errors="replace"),
    }


@app.post("/api/reset")
def reset():
    try:
        reset_workspace(WORKSPACE, WORKSPACE_ORIGINAL)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok", "workspace": str(WORKSPACE)}


# ---------- workspace file management (UI explorer) ----------

def _resolve_writable(path: str) -> Path:
    """Resolve a UI file-management path: sandboxed + denylist-protected."""
    p = _resolve_in_workspace(path)
    if any(is_denied_name(Path(part)) for part in p.relative_to(WORKSPACE).parts):
        raise HTTPException(status_code=403, detail=f"access denied: {path}")
    return p


class FsPathRequest(BaseModel):
    path: str


@app.post("/api/fs/mkdir", status_code=201)
def fs_mkdir(req: FsPathRequest):
    p = _resolve_writable(req.path)
    if p == WORKSPACE:
        raise HTTPException(status_code=400, detail="cannot create the workspace root")
    if p.exists():
        raise HTTPException(status_code=409, detail=f"already exists: {req.path}")
    p.mkdir(parents=True)
    return {"status": "ok", "path": p.relative_to(WORKSPACE).as_posix()}


@app.post("/api/fs/delete")
def fs_delete(req: FsPathRequest):
    p = _resolve_writable(req.path)
    if p == WORKSPACE:
        raise HTTPException(status_code=400, detail="cannot delete the workspace root")
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"not found: {req.path}")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"status": "ok", "deleted": req.path}


@app.post("/api/fs/upload", status_code=201)
async def fs_upload(
    files: list[UploadFile] = File(...),
    dir: str = Query(default="."),
):
    target_dir = _resolve_writable(dir)
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"not a directory: {dir}")
    saved: list[str] = []
    for f in files:
        name = Path(f.filename or "").name  # strip any client-supplied path
        if not name:
            raise HTTPException(status_code=400, detail="uploaded file has no name")
        dest = target_dir / name
        if is_denied_name(dest):
            raise HTTPException(status_code=403, detail=f"access denied: {name}")
        dest.write_bytes(await f.read())
        saved.append(dest.relative_to(WORKSPACE).as_posix())
    return {"status": "ok", "saved": saved}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=SETTINGS.host, port=SETTINGS.port)
