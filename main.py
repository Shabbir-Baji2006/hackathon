from __future__ import annotations
import os
import sys
import argparse
from dotenv import load_dotenv

from loopkit.core import HandWrittenAgentLoop, LoopKitController
from loopkit.llm import OpenAIPlanner
from loopkit.privacy import cleanup_old_traces
from loopkit.schemas import FinalAnswer

def format_final_answer(ans: FinalAnswer) -> str:
    lines = []
    lines.append("=" * 65)
    lines.append("               LOOPKIT AGENT FINAL REPORT")
    lines.append("=" * 65)
    lines.append(f"\n[1] BEST ANSWER SO FAR:\n{ans.best_answer_so_far}")
    lines.append(f"\n[2] CONFIDENCE: {ans.confidence}")
    lines.append(f"    CONFIDENCE GAP / CONFLICTS: {ans.confidence_gap}")
    
    if ans.focused_clarification:
        lines.append(f"\n[3] FOCUSED CLARIFICATION (REQUIRED NEXT INPUT):\n{ans.focused_clarification}")
    else:
        lines.append("\n[3] FOCUSED CLARIFICATION: None needed (HIGH confidence answer backed by authoritative sources).")

    if ans.citations:
        lines.append("\n[4] CITATIONS & AUTHORITATIVE EVIDENCE:")
        for idx, c in enumerate(ans.citations, 1):
            lines.append(f"    [{idx}] {c.title}")
            lines.append(f"        URL: {c.url}")
            lines.append(f"        Retrieved Date: {c.retrieved_date}")
            if c.snippet:
                lines.append(f"        Excerpt: {c.snippet[:120]}...")
    lines.append("=" * 65)
    return "\n".join(lines)

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="LoopKit: Evidence-Aware Research & Verify Agent")
    parser.add_argument("query", nargs="?", help="Analytical or research question to investigate")
    parser.add_argument("--cleanup-traces", action="store_true", help="Delete traces older than 7 days")
    parser.add_argument("--provider", choices=["openai", "simulated"], default="openai", help="LLM backend provider")
    args = parser.parse_args()

    if args.cleanup_traces:
        deleted = cleanup_old_traces()
        print(f"Cleaned up {deleted} trace files older than 7 days.")
        return

    query = args.query
    if not query:
        print("Error: Please provide a question to investigate. Example:")
        print("  python main.py \"What is the market size of quantum computing in 2024 and projected CAGR to 2030?\"")
        sys.exit(1)

    print(f"\nInitializing LoopKit Agent...")
    print(f"Question: {query}\n")

    if args.provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Warning: OPENAI_API_KEY not found in environment or .env.")
            print("Falling back to simulated demonstration mode. To use real OpenAI API, set OPENAI_API_KEY in .env.")
            from demo_runner import create_dynamic_mock_planner
            planner = create_dynamic_mock_planner(query)
        else:
            planner = OpenAIPlanner()
    else:
        from demo_runner import create_dynamic_mock_planner
        planner = create_dynamic_mock_planner(query)

    controller = LoopKitController()
    agent = HandWrittenAgentLoop(planner=planner, controller=controller)

    trace_file = f"trace_cli_{int(os.getpid())}.jsonl"
    final_answer = agent.run(query, trace_filename=trace_file)

    print(format_final_answer(final_answer))
    print(f"\nDetailed execution trace saved to: demo_evidence/{trace_file}")

if __name__ == "__main__":
    main()
