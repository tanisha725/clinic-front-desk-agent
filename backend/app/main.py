"""REST API. POST /agent/run is the graded endpoint; the /api routes feed the UI."""

import json
import traceback
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, llm, records
from .tools import TOOLS, ClinicStore

ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_BUILD = ROOT / "frontend" / "dist"

app = FastAPI(title="Sunrise Clinic front desk agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    conversation_id: str
    today: date          # rejects anything that is not YYYY-MM-DD with a 422
    turns: list[str]


class ToolRequest(BaseModel):
    today: date = date(2026, 10, 1)
    arguments: dict


@app.post("/agent/run")
def agent_run(request: RunRequest):
    today = request.today.isoformat()
    try:
        result, extra = agent.run_conversation(request.conversation_id, today, request.turns)
    except Exception:
        # A bug must not become a 500 or a half-finished answer: hand the call to a human.
        traceback.print_exc()
        result, extra = agent.failed_safely(request.conversation_id, today, request.turns)
    records.save(request.conversation_id, today, request.turns, result, extra)
    return result


@app.post("/tools/{name}")
def call_tool(name: str, request: ToolRequest):
    """Call one tool directly against a fresh copy of clinic.json (nothing is kept)."""
    result = ClinicStore(request.today.isoformat()).call(name, request.arguments)
    return JSONResponse(result, status_code=200 if result["ok"] else 422)


@app.get("/api/health")
def health():
    return {"ok": True, "reader": "llm" if llm.enabled() else "rules",
            "model": llm.MODEL if llm.enabled() else None, "tools": sorted(TOOLS)}


@app.get("/api/handoffs")
def handoff_queue():
    return records.queue()


@app.post("/api/handoffs/{conversation_id}/resolve")
def resolve_handoff(conversation_id: str):
    if not records.resolve(conversation_id):
        raise HTTPException(404, f"no handoff for conversation {conversation_id!r}")
    return records.queue()


@app.get("/api/conversations")
def list_conversations():
    return records.summaries()


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    record = records.get(conversation_id)
    if not record:
        raise HTTPException(404, f"no conversation {conversation_id!r} has been run yet")
    return record


@app.get("/api/samples")
def samples():
    """The example and adversarial scripts, so the UI can replay them."""
    scripts = []
    for folder in ("conversations", "adversarial"):
        for path in sorted((ROOT / folder).glob("*.json")):
            script = json.loads(path.read_text(encoding="utf-8"))
            scripts.append({"id": script["id"], "today": script["today"], "turns": script["turns"],
                            "description": script.get("description", "")})
    return scripts


# Serve the built React app from the same server, so one process is the whole product.
if FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_BUILD, html=True), name="frontend")
