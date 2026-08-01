"""CLI entrypoint: python cli.py --workspace ./workspace --task "..."

Prints each step live and writes trace.jsonl (one JSON object per line).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.config import get_settings
from agent.core import Agent, StepRecord


def main() -> int:
    parser = argparse.ArgumentParser(description="Hand-written file agent (CLI).")
    parser.add_argument("--workspace", default=None,
                        help="workspace directory (default: WORKSPACE_DIR env or ./workspace)")
    parser.add_argument("--task", required=True, help="natural-language task")
    parser.add_argument("--max-steps", type=int, default=None,
                        help="max agent steps (default: MAX_STEPS env or 15)")
    parser.add_argument("--trace", default="./trace.jsonl", help="trace output file")
    args = parser.parse_args()

    load_dotenv()
    settings = get_settings()

    workspace = Path(args.workspace) if args.workspace else settings.workspace_dir
    if not workspace.is_dir():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 2

    trace_path = Path(args.trace)
    trace_file = trace_path.open("w", encoding="utf-8")

    def on_step(record: StepRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        trace_file.write(line + "\n")
        trace_file.flush()
        print(f"[step {record.step}] {record.tool}({json.dumps(record.args, ensure_ascii=False)})")
        print(f"    -> {record.result_summary}")

    agent = Agent(
        workspace=workspace,
        max_steps=args.max_steps,  # None -> settings.max_steps
        settings=settings,
    )
    print(f"Task: {args.task}\nWorkspace: {workspace.resolve()}")
    print(f"Provider: {settings.llm_provider} | model: {agent.model}\n")

    try:
        result = agent.run(args.task, on_step=on_step)
    except Exception as e:
        trace_file.close()
        print(f"\nAgent run failed: {e}", file=sys.stderr)
        return 1

    summary = {
        "final_answer": result.final_answer,
        "status": result.status,
        "llm_calls": result.llm_calls,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
    }
    trace_file.write(json.dumps(summary, ensure_ascii=False) + "\n")
    trace_file.close()

    print("\n=== FINAL ANSWER ===")
    print(result.final_answer)
    print(
        f"\nstatus={result.status} | llm_calls={result.llm_calls} | "
        f"tokens: prompt={result.prompt_tokens} completion={result.completion_tokens} "
        f"total={result.total_tokens}"
    )
    print(f"trace written to {trace_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
