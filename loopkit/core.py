from __future__ import annotations
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from loopkit.schemas import (
    MAX_STEPS,
    SEARCH_RETRY,
    SEARCH_TIMEOUT_SECONDS,
    ActionPlan,
    FinalAnswer,
    Observation,
    TokenUsage,
    TraceRecord,
    Citation,
)
from loopkit.tools.calculator import SafeCalculator
from loopkit.tools.web_search import WebSearchTool
from loopkit.privacy import TraceWriter
from loopkit.llm import LLMPlanner

class AgentState:
    """Encapsulates running agent state across iterations."""
    def __init__(self, question: str, run_id: Optional[str] = None):
        self.question = question
        self.run_id = run_id or f"loopkit_run_{int(time.time())}_{id(self) % 1000}"
        self.history: List[Dict[str, Any]] = []
        self.retrieved_sources: List[Citation] = []
        self.step = 0
        self.start_time = datetime.now(timezone.utc).isoformat()

class LoopKitController:
    """Controller implementing the three explicit phases:
    1. Validate: Strict schema check & tool registry verification before execution.
    2. Execute: Sandboxed, timed execution catching all exceptions into observations.
    3. Decide: State integration, confidence assessment, and loop progression.
    """

    def __init__(
        self,
        search_tool: Optional[WebSearchTool] = None,
        calc_tool: Optional[SafeCalculator] = None,
    ):
        self.search_tool = search_tool or WebSearchTool(
            timeout_seconds=SEARCH_TIMEOUT_SECONDS,
            max_retries=SEARCH_RETRY,
        )
        self.calc_tool = calc_tool or SafeCalculator()
        self.registry = {
            "web_search": self.search_tool.search,
            "calculator": self.calc_tool.evaluate,
        }

    # ==================== PHASE 1: VALIDATE ====================
    def validate(self, raw_action: Any) -> Tuple[bool, str, Optional[ActionPlan]]:
        """Rejects malformed JSON and unauthorized tools before execution."""
        if not isinstance(raw_action, dict):
            return False, "rejected: model output is not a valid JSON object", None

        # Check for injected malformed marker or missing action structure
        if "__raw_malformed__" in raw_action:
            return False, f"rejected: malformed JSON from model. Expected schema with 'tool' or 'final_answer'", None

        has_tool = "tool" in raw_action and raw_action["tool"] is not None
        has_final = "final_answer" in raw_action and raw_action["final_answer"] is not None

        if not has_tool and not has_final:
            return False, "rejected: decision must provide either 'tool' or 'final_answer'", None

        if has_final:
            try:
                fa_raw = raw_action["final_answer"]
                if not isinstance(fa_raw, dict):
                    return False, "rejected: 'final_answer' must be a JSON object", None
                final_answer = FinalAnswer(**fa_raw)
                return True, "passed", ActionPlan(final_answer=final_answer)
            except Exception as e:
                return False, f"rejected: invalid final_answer schema ({str(e)})", None

        # Validate tool action
        tool_name = raw_action.get("tool")
        if tool_name not in self.registry:
            allowed = list(self.registry.keys())
            return False, f"rejected: unknown tool '{tool_name}'. Allowed tools: {allowed}", None

        tool_input = raw_action.get("tool_input")
        if tool_input is None:
            return False, f"rejected: tool '{tool_name}' requires 'tool_input' string", None

        if not isinstance(tool_input, str):
            tool_input = str(tool_input)

        try:
            plan = ActionPlan(tool=tool_name, tool_input=tool_input)
            return True, "passed", plan
        except Exception as e:
            return False, f"rejected: invalid tool action schema ({str(e)})", None

    # ==================== PHASE 2: EXECUTE ====================
    def execute(self, tool_name: str, tool_input: str) -> Observation:
        """Runs exactly one tool call per step with strict error catching."""
        tool_func = self.registry.get(tool_name)
        if not tool_func:
            return Observation(
                status="error",
                sources=[],
                summary=f"Controller error: tool '{tool_name}' is not in registry.",
            )

        try:
            raw_res = tool_func(tool_input)

            if tool_name == "web_search":
                status = raw_res.get("status", "ok")
                sources = raw_res.get("sources", [])
                summary = raw_res.get("summary", "")
                flag = raw_res.get("suspicious_content_flag", False)
                return Observation(
                    status=status,
                    sources=sources,
                    summary=summary,
                    suspicious_content_flag=flag,
                )

            elif tool_name == "calculator":
                status = raw_res.get("status", "ok")
                if status == "ok":
                    return Observation(
                        status="ok",
                        sources=[],
                        summary=raw_res.get("summary", f"Result: {raw_res.get('result')}"),
                    )
                else:
                    return Observation(
                        status="error",
                        sources=[],
                        summary=f"Calculator error: {raw_res.get('error')}",
                    )

        except Exception as ex:
            # Absolute safety net: never let any tool exception crash the loop
            return Observation(
                status="error",
                sources=[],
                summary=f"Unhandled tool failure in '{tool_name}': {type(ex).__name__}: {str(ex)}",
            )

    # ==================== PHASE 3: DECIDE ====================
    def decide_confidence(self, state: AgentState, last_obs: Observation) -> str:
        """Assesses evidence state confidence: HIGH, MEDIUM, or LOW."""
        if not state.retrieved_sources:
            return "LOW"

        # If any tool returned an error or sources conflict
        if last_obs.status == "error":
            return "MEDIUM" if len(state.retrieved_sources) > 0 else "LOW"

        has_official = any(".gov" in s.url or ".edu" in s.url or "official" in s.title.lower() for s in state.retrieved_sources)
        if has_official and len(state.retrieved_sources) >= 2:
            return "HIGH"
        elif len(state.retrieved_sources) >= 1:
            return "MEDIUM"
        return "LOW"

    def force_final_answer(self, state: AgentState) -> FinalAnswer:
        """Honest fallback when step limit (MAX_STEPS) is exhausted."""
        evidence_snippets = []
        for s in state.retrieved_sources:
            snippet_preview = s.snippet[:120] + "..." if s.snippet and len(s.snippet) > 120 else (s.snippet or "")
            evidence_snippets.append(f"- {s.title} ({s.url}): {snippet_preview}")

        evidence_text = "\n".join(evidence_snippets) if evidence_snippets else "No authoritative sources retrieved."

        return FinalAnswer(
            best_answer_so_far=(
                f"Provisional findings for '{state.question}':\n"
                f"Based on partial evidence gathered before reaching the operational limit:\n{evidence_text}"
            ),
            confidence="LOW" if not state.retrieved_sources else "MEDIUM",
            confidence_gap=(
                f"Operational limit of {MAX_STEPS} steps reached before full verification. "
                "Additional search cycles or official verification required."
            ),
            focused_clarification=(
                "Please provide direct official documentation, specific year, or clarify constraints to resolve remaining ambiguity."
            ),
            citations=state.retrieved_sources,
        )


class HandWrittenAgentLoop:
    """The hand-written Plan -> Act -> Observe -> Repeat execution engine."""

    def __init__(
        self,
        planner: LLMPlanner,
        controller: Optional[LoopKitController] = None,
        trace_writer: Optional[TraceWriter] = None,
        max_steps: int = MAX_STEPS,
    ):
        self.planner = planner
        self.controller = controller or LoopKitController()
        self.trace_writer = trace_writer or TraceWriter()
        self.max_steps = max_steps

    def run(self, question: str, trace_filename: Optional[str] = None) -> FinalAnswer:
        """Runs the loop until final answer is returned or max_steps is hit."""
        state = AgentState(question=question)
        if trace_filename is None:
            trace_filename = f"{state.run_id}.jsonl"

        # Hand-written Core Loop: Plan -> Act -> Observe -> Repeat
        step = 0
        while step < self.max_steps:
            # 1. Plan
            raw_action, token_usage = self.planner.plan({
                "question": state.question,
                "history": state.history,
                "retrieved_sources": [c.model_dump() for c in state.retrieved_sources],
            })

            # 2. Validate
            is_valid, validation_msg, action = self.controller.validate(raw_action)

            if not is_valid:
                # Malformed output or unknown tool -> log error observation, re-plan
                err_obs = Observation(
                    status="error",
                    sources=[],
                    summary=f"Validation failed: {validation_msg}. Please review tool schemas and re-plan.",
                )
                state.history.append({
                    "step": step + 1,
                    "action": raw_action,
                    "validation": validation_msg,
                    "result": err_obs.summary,
                })

                self.trace_writer.write_step(
                    TraceRecord(
                        run_id=state.run_id,
                        step=step + 1,
                        planned_action=raw_action if isinstance(raw_action, dict) else {"raw": str(raw_action)},
                        validation=validation_msg,
                        observation={"status": "error", "sources": [], "summary": err_obs.summary},
                        confidence_after_step="LOW",
                        token_usage=token_usage,
                        next_step="re-plan",
                    ),
                    trace_filename,
                )
                step += 1
                continue

            # Check if planner decided to finalize
            if action and action.final_answer:
                # Record final step trace
                self.trace_writer.write_step(
                    TraceRecord(
                        run_id=state.run_id,
                        step=step + 1,
                        planned_action={"final_answer": action.final_answer.best_answer_so_far[:60]},
                        validation="passed",
                        observation={"status": "ok", "sources": [c.url for c in action.final_answer.citations], "summary": "Final answer returned by planner."},
                        confidence_after_step=action.final_answer.confidence,
                        token_usage=token_usage,
                        next_step="completed",
                    ),
                    trace_filename,
                )
                return action.final_answer

            # 3. Act (Execute chosen tool)
            tool_name = action.tool
            tool_input = action.tool_input
            obs = self.controller.execute(tool_name, tool_input)

            # Store any discovered sources
            if tool_name == "web_search" and obs.status == "ok":
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                for src_url in obs.sources:
                    if not any(c.url == src_url for c in state.retrieved_sources):
                        state.retrieved_sources.append(
                            Citation(title=f"Source ({tool_input[:30]})", url=src_url, retrieved_date=today, snippet=obs.summary[:150])
                        )

            # 4. Observe & Decide
            conf = self.controller.decide_confidence(state, obs)
            next_step_hint = "final_answer" if conf == "HIGH" else "web_search | calculator | final_answer"

            state.history.append({
                "step": step + 1,
                "action": f"{tool_name}({tool_input})",
                "validation": "passed",
                "result": obs.summary,
            })

            # Record step trace
            self.trace_writer.write_step(
                TraceRecord(
                    run_id=state.run_id,
                    step=step + 1,
                    planned_action={"tool": tool_name, "input": tool_input},
                    validation="passed",
                    observation={
                        "status": obs.status,
                        "sources": obs.sources,
                        "summary": obs.summary[:200] + ("..." if len(obs.summary) > 200 else ""),
                    },
                    confidence_after_step=conf,
                    token_usage=token_usage,
                    next_step=next_step_hint,
                ),
                trace_filename,
            )

            step += 1

        # Hit MAX_STEPS ceiling -> honest fallback
        forced_answer = self.controller.force_final_answer(state)
        self.trace_writer.write_step(
            TraceRecord(
                run_id=state.run_id,
                step=self.max_steps,
                planned_action={"force_stop": "MAX_STEPS reached"},
                validation="passed: forced fallback",
                observation={
                    "status": "ok",
                    "sources": [c.url for c in forced_answer.citations],
                    "summary": f"Exhausted {self.max_steps} steps. Synthesized honest partial answer.",
                },
                confidence_after_step=forced_answer.confidence,
                token_usage=TokenUsage(),
                next_step="stopped_safely",
            ),
            trace_filename,
        )
        return forced_answer
