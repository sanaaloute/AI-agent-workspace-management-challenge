"""End-to-end agent-loop test with a FAKE LLM (no API key, no frameworks).

The fake LLM returns scripted responses: search -> read -> write -> final
text answer. Verifies the hand-written loop executes tools, records trace
steps, tracks usage, and terminates. Also verifies the step-cap path.

Run from repo root:  .venv/Scripts/python tests/fake_llm_loop.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import Agent


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d


class FakeToolCall:
    def __init__(self, i, name, args: dict):
        self.id = f"call_{i}"
        self.function = type("F", (), {"name": name, "arguments": json.dumps(args)})()


class FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5


class FakeResponse:
    def __init__(self, message):
        self.choices = [type("C", (), {"message": message})()]
        self.usage = FakeUsage()


def make_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="agent_test_ws_"))
    (ws / "docs").mkdir()
    (ws / "docs" / "a.md").write_text("alpha file about penguins", encoding="utf-8")
    (ws / "docs" / "b.md").write_text("beta file, nothing relevant", encoding="utf-8")
    return ws


failures = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- scripted run: search -> read -> write -> final answer -----------------
ws = make_workspace()
agent = Agent(workspace=ws, model="fake", client=None)

script = [
    FakeResponse(FakeMessage(tool_calls=[FakeToolCall(1, "search_content", {"query": "penguin"})])),
    FakeResponse(FakeMessage(tool_calls=[FakeToolCall(2, "read_file", {"path": "docs/a.md"})])),
    FakeResponse(FakeMessage(tool_calls=[FakeToolCall(3, "write_file", {"path": "report.md", "content": "# Report\npenguins found in docs/a.md"})])),
    FakeResponse(FakeMessage(content="Done: wrote report.md summarizing the penguin file.")),
]
calls = {"n": 0}


def fake_call(messages, use_tools=True):
    resp = script[min(calls["n"], len(script) - 1)]
    calls["n"] += 1
    return resp


agent._call_llm = fake_call
records = []
result = agent.run("index the penguin file", on_step=records.append)

check("loop terminated with final answer", result.final_answer.startswith("Done:"))
check("3 trace steps recorded", len(result.steps) == 3, f"got {len(result.steps)}")
check("step tools in order", [s.tool for s in result.steps] == ["search_content", "read_file", "write_file"])
check("on_step callback fired", len(records) == 3)
check("llm_calls counted", result.llm_calls == 4, f"got {result.llm_calls}")
check("token usage tracked", result.prompt_tokens == 40 and result.completion_tokens == 20)
check("write_file actually wrote", (ws / "report.md").read_text(encoding="utf-8").startswith("# Report"))
check("result_summary capped", all(len(s.result_summary) <= 203 for s in result.steps))

# --- step-cap path: model never stops calling tools ------------------------
ws2 = make_workspace()
agent2 = Agent(workspace=ws2, model="fake", client=None, max_steps=3)


def looping_call(messages, use_tools=True):
    if not use_tools:
        return FakeResponse(FakeMessage(content="best-effort answer at step limit"))
    return FakeResponse(FakeMessage(tool_calls=[FakeToolCall(9, "list_directory", {"path": "."})]))


agent2._call_llm = looping_call
result2 = agent2.run("loop forever")
check("step cap -> step_limit status", result2.status == "step_limit")
check("step cap -> final nudge answer", result2.final_answer == "best-effort answer at step limit")
check("step cap -> max_steps * 1 tool steps", len(result2.steps) == 3)
check("step cap -> llm calls = max_steps + 1", result2.llm_calls == 4)

# --- token budget path ------------------------------------------------------
ws3 = make_workspace()
agent3 = Agent(workspace=ws3, model="fake", client=None, token_budget=10)
agent3._call_llm = looping_call
result3 = agent3.run("spend tokens")
check("budget -> aborted_budget status", result3.status == "aborted_budget")
check("budget -> graceful final answer", "token budget" in result3.final_answer)

# --- LLM call raises mid-run: graceful error, never a hang ------------------
ws4 = make_workspace()
agent4 = Agent(workspace=ws4, model="fake", client=None)
state4 = {"n": 0}


def flaky_call(messages, use_tools=True):
    state4["n"] += 1
    if state4["n"] == 2:
        raise TimeoutError("simulated provider timeout")
    return FakeResponse(FakeMessage(tool_calls=[FakeToolCall(5, "list_directory", {"path": "."})]))


agent4._call_llm = flaky_call
result4 = agent4.run("fail on the second call")
check("llm error -> error status", result4.status == "error")
check("llm error -> graceful final answer", "failed" in result4.final_answer.lower())
check("llm error -> partial steps kept", len(result4.steps) == 1, f"got {len(result4.steps)}")

shutil.rmtree(ws, ignore_errors=True)
shutil.rmtree(ws2, ignore_errors=True)
shutil.rmtree(ws3, ignore_errors=True)
shutil.rmtree(ws4, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL FAKE-LLM LOOP TESTS PASSED")
