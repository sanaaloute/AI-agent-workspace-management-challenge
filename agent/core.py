"""The hand-written agent loop.

Control flow (model returns tool calls -> execute -> append results ->
decide continue/stop) lives entirely here; the `openai` SDK is used only
as a chat-completions HTTP client. No agent framework is involved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from openai import OpenAI

from .config import Settings, get_settings
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, WorkspaceTools

RESULT_SUMMARY_CHARS = 200

FINAL_NUDGE = (
    "You have reached the step limit. Do NOT call any more tools. "
    "Give your best-effort final answer now based on what you have learned "
    "so far, and state clearly that the step limit was reached."
)


@dataclass
class StepRecord:
    step: int
    tool: str
    args: dict
    result_summary: str

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "tool": self.tool,
            "args": self.args,
            "result_summary": self.result_summary,
        }


@dataclass
class RunResult:
    final_answer: str
    steps: list[StepRecord] = field(default_factory=list)
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    status: str = "done"  # done | step_limit | aborted_budget | error

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Agent:
    def __init__(
        self,
        workspace: str | Path | None = None,
        model: Optional[str] = None,
        max_steps: Optional[int] = None,
        token_budget: Optional[int] = None,
        client: Optional[OpenAI] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.tools = WorkspaceTools(workspace or self.settings.workspace_dir)
        self.model = model or self.settings.model
        self.max_steps = max_steps if max_steps is not None else self.settings.max_steps
        self.token_budget = token_budget if token_budget is not None else self.settings.token_budget
        self.client = client  # lazy: OpenAI client created on first real LLM call

    # -- the single place that talks to the LLM ---------------------------

    def _call_llm(self, messages: list[dict], use_tools: bool = True):
        if self.client is None:
            self.client = self._build_client()
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if use_tools:
            kwargs["tools"] = TOOL_SCHEMAS
        return self.client.chat.completions.create(**kwargs)

    def _build_client(self) -> OpenAI:
        """OpenAI SDK client pointed at the configured provider."""
        s = self.settings
        if not s.api_key:
            # Fail fast: never let the SDK guess a key from its own env
            # defaults and silently call the wrong provider.
            raise ValueError(
                f"No LLM API key configured: set LLM_API_KEY in .env "
                f"(LLM_PROVIDER={s.llm_provider!r}, endpoint {s.base_url})."
            )
        headers = None
        if s.llm_provider == "openrouter":
            # Optional OpenRouter attribution headers.
            headers = {
                "HTTP-Referer": s.openrouter_referer,
                "X-Title": s.openrouter_title,
            }
        return OpenAI(
            api_key=s.api_key,
            base_url=s.base_url,
            default_headers=headers,
            # Explicit timeout: the SDK default is 600s per attempt with
            # retries, so a hung provider connection looks like a frozen
            # agent for tens of minutes. Fail fast instead.
            timeout=s.llm_timeout,
            max_retries=2,
        )

    # -- the loop ----------------------------------------------------------

    def run(
        self,
        task: str,
        on_step: Optional[Callable[[StepRecord], None]] = None,
    ) -> RunResult:
        result = RunResult(final_answer="")
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        def track_usage(resp) -> None:
            result.llm_calls += 1
            usage = getattr(resp, "usage", None)
            if usage is not None:
                result.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                result.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

        final_answer: Optional[str] = None

        for step_no in range(1, self.max_steps + 1):
            try:
                resp = self._call_llm(messages)
            except Exception as e:
                # A failed/hung LLM call must never freeze the run: report
                # what happened and keep the partial trace as the deliverable.
                result.status = "error"
                final_answer = (
                    f"The LLM request at step {step_no} failed: {e}. "
                    f"The run stopped with {len(result.steps)} completed tool "
                    "step(s); partial findings are in the trace. This is "
                    "usually a provider timeout or connectivity issue — "
                    "re-run the task to retry."
                )
                break
            track_usage(resp)

            if self.token_budget and result.total_tokens > self.token_budget:
                result.status = "aborted_budget"
                break

            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                # Model answered in plain text: task finished.
                final_answer = msg.content or ""
                break

            # Append the assistant turn (with tool calls) to history.
            messages.append(msg.model_dump(exclude_none=True))

            for tc in tool_calls:
                name = tc.function.name
                raw_args = tc.function.arguments or ""
                tool_result = self.tools.execute(name, raw_args)

                try:
                    args_dict = json.loads(raw_args) if raw_args.strip() else {}
                    if not isinstance(args_dict, dict):
                        args_dict = {"_raw": raw_args[:RESULT_SUMMARY_CHARS]}
                except json.JSONDecodeError:
                    args_dict = {"_raw": raw_args[:RESULT_SUMMARY_CHARS]}

                summary = tool_result
                if len(summary) > RESULT_SUMMARY_CHARS:
                    summary = summary[:RESULT_SUMMARY_CHARS] + "..."
                record = StepRecord(
                    step=step_no, tool=name, args=args_dict, result_summary=summary
                )
                result.steps.append(record)
                if on_step:
                    on_step(record)

                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                )

        if final_answer is None:
            if result.status == "aborted_budget":
                final_answer = (
                    "Run aborted: the per-session token budget "
                    f"({self.token_budget}) was exceeded after {result.llm_calls} "
                    "LLM call(s). Partial findings are in the trace; please "
                    "re-run with a narrower task or a higher budget."
                )
            else:
                # Step cap hit: one final LLM call, no tools, best-effort answer.
                result.status = "step_limit"
                messages.append({"role": "user", "content": FINAL_NUDGE})
                try:
                    resp = self._call_llm(messages, use_tools=False)
                    track_usage(resp)
                    final_answer = resp.choices[0].message.content or ""
                except Exception as e:
                    final_answer = f"Step limit reached and final answer call failed: {e}"

        result.final_answer = final_answer
        return result
