"""The requests the tool loop sends the gateway, pinned to a recorded file.

``fixtures/tool_loop_requests_golden.json`` was written by running these
scenarios through ``run_chat_tool_loop`` on the commit before the loop
was split into rounds (``6457caa5e``). This test runs the same scenarios
on the current code and compares every request the gateway stub received,
field by field, and a summary of the outcome. A change to what the loop
sends, or in what order, fails here.

To re-record (only when a change to the requests is intended)::

    .venv/bin/python -c "from tests.chat.test_tool_loop_request_golden import write_golden; write_golden()"
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.autonomous.guard import ToolResult
from app.chat import tool_loop
from app.chat.tool_loop import (
    LoopConfirmation,
    LoopFinal,
    LoopMcpAuth,
    LoopUsage,
    run_chat_tool_loop,
)
from app.chat.tool_schemas import ChatToolAllowlist, ToolSpec
from app.errors import MCPAuthorizationRequired, ToolTierRefused
from app.schemas.gateway import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    FinishReason,
)

GOLDEN = Path(__file__).parent / "fixtures" / "tool_loop_requests_golden.json"


def _call(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _resp(
    n: int, *, calls: list[dict[str, Any]] | None = None, text: str | None = None
) -> ChatCompletionResponse:
    finish: FinishReason = "tool_calls" if calls else "stop"
    return ChatCompletionResponse(
        id=f"r{n}",
        created=1_700_000_000,
        model="m",
        choices=[
            ChatCompletionChoice(
                index=0,
                finish_reason=finish,
                message=ChatCompletionMessage(
                    role="assistant", content=text, tool_calls=calls or None
                ),
            )
        ],
        usage=ChatCompletionUsage(prompt_tokens=10 * n, completion_tokens=n, total_tokens=11 * n),
        cost_estimate=0.001 * n,
        routed_inference_tier=2,
        routed_provider="p",
    )


def _allowlist() -> ChatToolAllowlist:
    return ChatToolAllowlist(
        specs={
            "mcp__s__read": ToolSpec(
                function_name="mcp__s__read",
                kind="mcp",
                provider="s",
                tool="read",
                read_only=True,
                destructive=False,
                requires_confirmation=False,
                parameters={"type": "object", "properties": {"q": {"type": "string"}}},
                description="read",
            ),
            "mcp__s__delete": ToolSpec(
                function_name="mcp__s__delete",
                kind="mcp",
                provider="s",
                tool="delete",
                read_only=False,
                destructive=True,
                requires_confirmation=True,
                parameters={"type": "object", "properties": {"id": {"type": "string"}}},
                description="delete",
            ),
        }
    )


# What ``execute_tool`` does, call by call: "ok" returns a result, "auth"
# raises ``MCPAuthorizationRequired``, "refused" raises ``ToolTierRefused``.
_EXEC_DEFAULT = ["ok"] * 20


def _base_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="smart",
        messages=[
            ChatCompletionMessage(role="system", content="sys"),
            ChatCompletionMessage(role="user", content="question"),
        ],
        temperature=0.2,
    )


class Scenario:
    def __init__(
        self,
        responses: list[ChatCompletionResponse],
        *,
        calls_used: int = 0,
        cap: int = 8,
        execute: list[str] | None = None,
        usage: LoopUsage | None = None,
    ) -> None:
        self.responses = responses
        self.calls_used = calls_used
        self.cap = cap
        self.execute = execute or _EXEC_DEFAULT
        self.usage = usage


_RAW: dict[str, Any] = {
    # Round 1: one call run, one unknown name. Round 2: two calls run, the
    # cap of 3 is reached. Round 3: the no-tools synthesis round.
    "two_tool_rounds_then_cap": (
        [
            _resp(
                1,
                calls=[_call("a1", "mcp__s__read", {"q": "x"}), _call("a2", "nope", {})],
            ),
            _resp(
                2,
                calls=[
                    _call("b1", "mcp__s__read", {"q": "y"}),
                    _call("b2", "mcp__s__read", {"q": "z"}),
                ],
            ),
            _resp(3, text="synthesised"),
        ],
        0,
        3,
    ),
    # One tool round, then a plain answer.
    "tool_round_then_answer": (
        [_resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})]), _resp(2, text="answer")],
        0,
        8,
    ),
    # Every call in the round has an unknown name: straight to synthesis.
    "all_unknown_then_synthesis": (
        [_resp(1, calls=[_call("a1", "nope", {})]), _resp(2, text="from nothing")],
        0,
        8,
    ),
    # Resumed with the cap already reached: one synthesis round only.
    "resumed_at_cap": ([_resp(1, text="resumed")], 8, 8),
}

SCENARIOS: dict[str, Scenario] = {
    name: Scenario(responses, calls_used=used, cap=cap)
    for name, (responses, used, cap) in _RAW.items()
}
SCENARIOS.update(
    {
        # Round 1 runs a read. Round 2 runs a read, then proposes a delete:
        # the turn pauses for confirmation and the call after it is dropped.
        "read_then_confirmation_pause": Scenario(
            [
                _resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})]),
                _resp(
                    2,
                    calls=[
                        _call("b1", "mcp__s__read", {"q": "y"}),
                        _call("b2", "mcp__s__delete", {"id": "7"}),
                        _call("b3", "mcp__s__read", {"q": "never"}),
                    ],
                ),
            ]
        ),
        # Round 1 runs a read; round 2's call needs MCP authorization.
        "read_then_mcp_auth_pause": Scenario(
            [
                _resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})]),
                _resp(2, calls=[_call("b1", "mcp__s__read", {"q": "y"})]),
            ],
            execute=["ok", "auth"],
        ),
        # A tier refusal counts as a governed call and the loop goes on.
        "tier_refused_then_answer": Scenario(
            [_resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})]), _resp(2, text="ok")],
            execute=["refused"],
        ),
        # A resumed turn with carried totals and calls already used.
        "resumed_with_usage": Scenario(
            [
                _resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})]),
                _resp(2, text="resumed answer"),
            ],
            calls_used=1,
            cap=2,
            usage=LoopUsage(prompt_tokens=5, completion_tokens=6, priced_cost_micros=7, rounds=1),
        ),
    }
)


def _execute_mock(plan: list[str]) -> AsyncMock:
    steps = iter(enumerate(plan))

    async def _run(*_a: Any, **_k: Any) -> ToolResult:
        i, what = next(steps)
        if what == "auth":
            raise MCPAuthorizationRequired("s")
        if what == "refused":
            raise ToolTierRefused(provider="s", tool="read", tier=3, ceiling=1)
        return ToolResult(data={"n": i})

    return AsyncMock(side_effect=_run)


def scenario_patches(sc: Scenario) -> tuple[AsyncMock, Any]:
    """Return the gateway stub and a context manager with the loop's patches."""
    gateway = AsyncMock()
    gateway.chat_completion.side_effect = list(sc.responses)
    settings = MagicMock()
    settings.chat_tool_call_cap = sc.cap
    stack = ExitStack()
    stack.enter_context(patch("app.chat.tool_loop.list_servers", new=AsyncMock(return_value=[])))
    stack.enter_context(patch("app.chat.tool_loop.execute_tool", new=_execute_mock(sc.execute)))
    stack.enter_context(patch("app.chat.tool_loop.get_settings", return_value=settings))
    stack.enter_context(
        patch("app.chat.tool_loop.resolve_provider_tier", new=AsyncMock(return_value=2))
    )
    return gateway, stack


def loop_kwargs(sc: Scenario, gateway: Any) -> dict[str, Any]:
    """The keyword arguments the scenario passes to the loop."""
    return {
        "user": MagicMock(),
        "gateway": gateway,
        "base_request": _base_request(),
        "allowlist": _allowlist(),
        "assistant_message_id": uuid.UUID(int=1),
        "calls_used": sc.calls_used,
        "request_id": "req-1",
        "usage": sc.usage,
    }


def summarize(outcome: Any) -> dict[str, Any]:
    """A JSON-safe summary of an outcome."""
    assert isinstance(outcome, LoopFinal | LoopConfirmation | LoopMcpAuth)
    summary: dict[str, Any] = {
        "type": type(outcome).__name__,
        "calls_used": outcome.calls_used,
        "messages": outcome.messages,
    }
    if isinstance(outcome, LoopFinal):
        assert outcome.usage is not None
        summary.update(
            text=outcome.text,
            usage=outcome.usage.to_state(),
            tool_sources=len(outcome.tool_sources),
        )
    elif isinstance(outcome, LoopConfirmation):
        summary.update(
            spec=outcome.spec.function_name,
            args=outcome.args,
            args_summary=outcome.args_summary,
            tier=outcome.tier,
            usage=outcome.usage.to_state(),
        )
    else:
        summary.update(server=outcome.server, usage=outcome.usage.to_state())
    return summary


async def run_scenario(name: str) -> dict[str, Any]:
    """Run one scenario through ``run_chat_tool_loop``; return what was sent."""
    sc = SCENARIOS[name]
    gateway, stack = scenario_patches(sc)
    with stack:
        execute = cast(AsyncMock, tool_loop.execute_tool)
        outcome = await run_chat_tool_loop(MagicMock(), **loop_kwargs(sc, gateway))
        tool_calls = [c.kwargs["args"] for c in execute.call_args_list]
    summary = summarize(outcome)
    return {
        "requests": [
            {
                "request": c.args[0].model_dump(mode="json"),
                "request_id": c.kwargs.get("request_id"),
            }
            for c in gateway.chat_completion.call_args_list
        ],
        "tool_calls": tool_calls,
        "outcome": summary,
    }


def write_golden() -> None:
    """Record the golden file from the current code."""

    async def _all() -> dict[str, Any]:
        return {name: await run_scenario(name) for name in SCENARIOS}

    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(asyncio.run(_all()), indent=2, sort_keys=True) + "\n")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_requests_match_recorded_golden(name: str) -> None:
    golden = json.loads(GOLDEN.read_text())
    got = json.loads(json.dumps(await run_scenario(name), sort_keys=True))
    assert got == golden[name]
