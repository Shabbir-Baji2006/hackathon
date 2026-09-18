from __future__ import annotations
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root automatically
load_dotenv(Path(__file__).parent / ".env")

from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
import groq

from loopkit.core import HandWrittenAgentLoop, LoopKitController
from loopkit.llm import GroqPlanner
from demo_runner import DemoSuite, create_dynamic_mock_planner

app = FastAPI(title="LoopKit Agent Dashboard")

BASE_DIR     = Path(__file__).parent.resolve()
WEB_DIR      = BASE_DIR / "web"
STATIC_DIR   = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
EVIDENCE_DIR = BASE_DIR / "demo_evidence"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), auto_reload=True, cache_size=0)

SCENARIOS_META = [
    {"id": "a", "title": "Clear Analytical Research",    "desc": "EU Horizon Europe budget split across 3 pillars.", "tag": "RESEARCH + MATH", "category": "chain"},
    {"id": "b", "title": "Missing Input Detection",      "desc": "California scholarship with missing student AGI.",  "tag": "LOW CONFIDENCE", "category": "uncertainty"},
    {"id": "c", "title": "Conflicting Sources",          "desc": "Old vs revised government notice — source conflict.","tag": "CONFLICT DETECT", "category": "uncertainty"},
    {"id": "d", "title": "Search Timeout + Retry",       "desc": "Simulated 8s timeout with 1 automatic retry.",     "tag": "ERROR RECOVERY", "category": "recovery"},
    {"id": "e", "title": "Malformed JSON Recovery",      "desc": "Controller rejects bad output, agent re-plans.",   "tag": "VALIDATION FAIL", "category": "recovery"},
    {"id": "f", "title": "Pure Math Calculation",        "desc": "Skips web search, routes directly to calculator.","tag": "CALCULATOR", "category": "math"},
    {"id": "g", "title": "Adversarial Prompt Block",     "desc": "Prompt injection hits hard MAX_STEPS safety cap.", "tag": "SAFETY LIMIT", "category": "safety"},
    {"id": "chaining", "title": "Autonomous Tool Chain", "desc": "Search market caps then calculate the average.",   "tag": "TOOL CHAIN", "category": "chain"},
]

class QueryRequest(BaseModel):
    query: str

def get_planner_info() -> Dict[str, str]:
    """Returns current planner mode for UI status display."""
    groq_key = os.getenv("GROQ_API_KEY")

    if groq_key and groq_key != "your_groq_api_key_here":
        model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        return {"mode": "groq", "label": f"Groq / {model} (Live)", "status": "live"}
    else:
        return {"mode": "mock", "label": "Mock Planner (Demo)", "status": "demo"}

def read_trace_file(trace_filename: str) -> List[Dict[str, Any]]:
    path = EVIDENCE_DIR / trace_filename
    if not path.exists():
        return []
    traces = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                try:
                    traces.append(json.loads(line_str))
                except Exception:
                    pass
    return traces

def generate_langchain_comparison(query_desc: str, step_count: int) -> str:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key or groq_key == "your_groq_api_key_here":
        return f"LoopKit explicitly completed this in {step_count} steps. LangChain would likely obscure this trace in a black box."
    try:
        client = groq.Groq(api_key=groq_key)
        model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        prompt = f"Our hand-written loop just solved this query or scenario: '{query_desc}' in {step_count} steps using explicit JSON validation and a deterministic state machine. Write a 2-sentence comparison of how our transparent loop handled this cleanly, and how a bloated framework like LangChain would have likely handled it (e.g., using hidden ReAct prompts, opaque abstraction layers, unpredictable agent executors, or silent hallucination). Write only the 2 sentences."
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150
        )
        return res.choices[0].message.content.strip()
    except Exception:
        return f"LoopKit explicitly completed this in {step_count} steps. LangChain would likely obscure this trace in a black box."

def _render(name: str, request: Request, **ctx):
    template = env.get_template(name)
    planner = get_planner_info()
    return HTMLResponse(template.render(request=request, planner=planner, **ctx))

# ── Page Routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return _render("index.html", request, scenarios=SCENARIOS_META)

# ── API Routes ─────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    return {"planner": get_planner_info(), "tools": ["web_search", "calculator"], "version": "1.0.0"}

@app.get("/api/scenarios")
async def get_scenarios():
    return {"scenarios": SCENARIOS_META}

@app.post("/api/run-scenario/{scenario_id}")
async def run_scenario_endpoint(scenario_id: str):
    suite = DemoSuite(evidence_dir=str(EVIDENCE_DIR))
    method_name = f"run_scenario_{scenario_id.lower()}"
    if not hasattr(suite, method_name):
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")

    try:
        runner = getattr(suite, method_name)
        final_ans = runner()
        traces = read_trace_file(f"scenario_{scenario_id.lower()}.jsonl")
        
        comp_text = generate_langchain_comparison(f"Scenario {scenario_id}", len(traces))

        return {
            "scenario_id": scenario_id,
            "final_answer": final_ans.model_dump(),
            "traces": traces,
            "planner": get_planner_info(),
            "langchain_comparison": comp_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario execution failed: {str(e)}")

@app.post("/api/query")
async def execute_custom_query(req: QueryRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(query) > 500:
        raise HTTPException(status_code=400, detail="Query too long (max 500 chars).")

    groq_key = os.getenv("GROQ_API_KEY")

    try:
        if groq_key and groq_key != "your_groq_api_key_here":
            planner = GroqPlanner()
        else:
            planner = create_dynamic_mock_planner(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize planner: {str(e)}")

    controller = LoopKitController()
    agent = HandWrittenAgentLoop(planner=planner, controller=controller)

    trace_file = f"trace_web_{os.getpid()}.jsonl"
    trace_path = EVIDENCE_DIR / trace_file
    if trace_path.exists():
        trace_path.unlink()

    try:
        final_ans = agent.run(query, trace_filename=trace_file)
        traces = read_trace_file(trace_file)
        
        comp_text = generate_langchain_comparison(query, len(traces))

        return {
            "query": query,
            "final_answer": final_ans.model_dump(),
            "traces": traces,
            "planner": get_planner_info(),
            "langchain_comparison": comp_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8002, reload=False)
