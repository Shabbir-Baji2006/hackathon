from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, Field

# Operational Limits
MAX_STEPS = 6
SEARCH_RETRY = 1
SEARCH_TIMEOUT_SECONDS = 8
MAX_QUERY_LENGTH = 150

class Citation(BaseModel):
    title: str = Field(..., description="Title of the source")
    url: str = Field(..., description="Direct URL of the authoritative source")
    retrieved_date: str = Field(..., description="Date when source was retrieved (YYYY-MM-DD)")
    snippet: Optional[str] = Field(None, description="Relevant excerpt or data point")

class FinalAnswer(BaseModel):
    best_answer_so_far: str = Field(
        ...,
        description="Synthesized strictly from retrieved evidence, never asserted as more certain than evidence supports."
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        ...,
        description="HIGH: current authoritative sources cover question and all inputs present. MEDIUM: relevant authoritative source exists but non-critical detail missing. LOW: no authoritative source, conflict, or key input missing."
    )
    confidence_gap: str = Field(
        ...,
        description="Explanation of what is missing, stale, or conflicting."
    )
    focused_clarification: Optional[str] = Field(
        None,
        description="Targeted question asking strictly for missing fields when confidence is MEDIUM/LOW. Omitted on HIGH confidence."
    )
    citations: List[Citation] = Field(
        default_factory=list,
        description="List of cited sources backing the answer."
    )

class ActionPlan(BaseModel):
    tool: Optional[Literal["web_search", "calculator"]] = Field(
        None,
        description="Name of tool to execute: 'web_search' or 'calculator'. Must be None if final_answer is provided."
    )
    tool_input: Optional[str] = Field(
        None,
        description="Input string for the selected tool (e.g. search query or arithmetic expression)."
    )
    final_answer: Optional[FinalAnswer] = Field(
        None,
        description="Structured final answer if sufficient evidence is gathered or stopping."
    )

class Observation(BaseModel):
    status: Literal["ok", "error"]
    sources: List[str] = Field(default_factory=list)
    summary: str
    suspicious_content_flag: bool = False

class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0

class TraceRecord(BaseModel):
    run_id: str
    step: int
    planned_action: Dict[str, Any]
    validation: str
    observation: Dict[str, Any]
    confidence_after_step: Literal["HIGH", "MEDIUM", "LOW"]
    token_usage: TokenUsage
    next_step: str
