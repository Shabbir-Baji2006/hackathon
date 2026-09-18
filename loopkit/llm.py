from __future__ import annotations
import os
import json
from typing import Dict, Any, List, Optional
from loopkit.schemas import ActionPlan, TokenUsage

SYSTEM_PROMPT = """You are LoopKit, a disciplined evidence-aware research and verification agent.
Your objective is to answer analytical, fact-plus-math questions by researching evidence, verifying calculations, and being explicit about uncertainty.

CRITICAL INSTRUCTIONS FOR TOOL SELECTION:
You have access to exactly two tools:
1. 'web_search': Queries the live web for authoritative sources, reports, figures, and dates.
2. 'calculator': Sandboxed math evaluator for arithmetic (+, -, *, /, **), comparisons, and safe math functions (sqrt, pow, round, min, max, abs, log).

Select tools based solely on their capability descriptions. Do not guess facts or perform mental arithmetic when exact figures are required.

CRITICAL INSTRUCTIONS FOR FINAL ANSWER:
When you have collected adequate evidence or when tools cannot provide more details, provide a structured 'final_answer':
1. 'best_answer_so_far': Synthesized strictly from retrieved evidence, never asserted as more certain than the evidence supports.
2. 'confidence':
   - HIGH: current authoritative sources cover the question and all needed inputs are present.
   - MEDIUM: a relevant authoritative source exists but a non-critical detail is missing or secondary source is unclear.
   - LOW: no authoritative source found, sources conflict, or a key input is missing.
3. 'confidence_gap': Explicitly explain what is missing, stale, or conflicting. If sources disagree, prioritize: official/primary sources > reputable secondary sources > aggregators/blogs. Prefer newest official notices; if two authoritative sources conflict, state the conflict explicitly.
4. 'focused_clarification': When confidence is MEDIUM or LOW, ask only for the specific missing input needed to raise it. If confidence is HIGH, omit or set to null.
5. 'citations': List of source URLs with titles and retrieved dates that back your answer.

OUTPUT SCHEMA:
You MUST respond with a valid JSON object matching this schema:
Either a tool action:
{
  "tool": "web_search" | "calculator",
  "tool_input": "exact string query or math expression"
}
OR a final answer:
{
  "final_answer": {
    "best_answer_so_far": "...",
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "confidence_gap": "...",
    "focused_clarification": "..." (or null),
    "citations": [
      {"title": "...", "url": "...", "retrieved_date": "...", "snippet": "..."}
    ]
  }
}
Do not include commentary outside the JSON.
"""

class LLMPlanner:
    """Base interface for agent planner."""

    def plan(self, state: Dict[str, Any]) -> tuple[Dict[str, Any], TokenUsage]:
        raise NotImplementedError

class GroqPlanner(LLMPlanner):
    """Planner using Groq API — 100% free, extremely fast, no credit card needed.
    Get your free key at: https://console.groq.com/keys
    Default model: llama-3.3-70b-versatile (best free option)
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from groq import Groq
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model or os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys")
        self.client = Groq(api_key=self.api_key)

    def plan(self, state: Dict[str, Any]) -> tuple[Dict[str, Any], TokenUsage]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"User Question: {state['question']}\n\n"
                f"Execution History:\n{self._format_history(state.get('history', []))}"
            )},
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = response.choices[0].message.content or "{}"
            usage = response.usage
            token_usage = TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                estimated_cost_usd=0.0,  # Free on Groq
            )
        except Exception as e:
            return {"__raw_malformed__": str(e)}, TokenUsage(prompt_tokens=0, completion_tokens=0, estimated_cost_usd=0.0)

        try:
            decision = json.loads(content)
        except Exception:
            decision = {"__raw_malformed__": content}

        return decision, token_usage

    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return "No previous steps taken."
        return "\n".join(
            f"Step {h.get('step')}: Action={h.get('action')} | Result={h.get('result')}"
            for h in history
        )


class DeterministicScenarioPlanner(LLMPlanner):
    """Planner configured with deterministic decision sequences for demonstration and grading.
    Allows exact verification of edge cases: injected malformed JSON, timeouts, tool ordering, etc.
    """

    def __init__(self, plan_callback):
        self.plan_callback = plan_callback
        self.step_counter = 0

    def plan(self, state: Dict[str, Any]) -> tuple[Dict[str, Any], TokenUsage]:
        self.step_counter += 1
        decision = self.plan_callback(state, self.step_counter)
        token_usage = TokenUsage(
            prompt_tokens=220 + self.step_counter * 85,
            completion_tokens=90 + self.step_counter * 35,
            estimated_cost_usd=round(0.00015 * self.step_counter, 6)
        )
        return decision, token_usage
