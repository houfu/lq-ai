"""Guards on ``ChatToolLoop``: no round after a failed round, read-only state.

The scenarios and stubs are those of ``test_tool_loop_request_golden.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.autonomous.guard import ToolResult
from app.chat import tool_loop
from app.chat.tool_loop import ChatToolLoop, run_chat_tool_loop
from app.errors import InternalError, ResearchNotConfigured
from tests.chat.test_tool_loop_request_golden import (
    SCENARIOS,
    Scenario,
    _call,
    _resp,
    loop_kwargs,
    scenario_patches,
)

# One round in which the model asks for two reads.
_TWO_READS = Scenario(
    [
        _resp(
            1,
            calls=[
                _call("a1", "mcp__s__read", {"q": "x"}),
                _call("a2", "mcp__s__read", {"q": "y"}),
            ],
        ),
        _resp(2, text="never sent"),
    ]
)


def _second_read_fails(error: BaseException) -> AsyncMock:
    seen: list[dict[str, Any]] = []

    async def _run(*_a: Any, **kwargs: Any) -> ToolResult:
        seen.append(kwargs["args"])
        if len(seen) == 2:
            raise error
        return ToolResult(data={"ok": True})

    return AsyncMock(side_effect=_run)


@pytest.mark.asyncio
async def test_no_round_runs_again_after_a_round_raised() -> None:
    """A read that ran before the error is not run a second time."""
    error = ResearchNotConfigured("not configured")
    execute = _second_read_fails(error)
    gateway, stack = scenario_patches(_TWO_READS)
    with stack, patch("app.chat.tool_loop.execute_tool", new=execute):
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(_TWO_READS, gateway))
        with pytest.raises(ResearchNotConfigured):
            await loop.next_round()
        with pytest.raises(InternalError):
            await loop.next_round()

    assert gateway.chat_completion.call_count == 1
    assert [c.kwargs["args"] for c in execute.call_args_list] == [{"q": "x"}, {"q": "y"}]
    assert loop.calls_used == 0
    assert not loop.done


@pytest.mark.asyncio
async def test_run_chat_tool_loop_raises_the_same_exception_object_unchanged() -> None:
    error = ResearchNotConfigured("not configured")
    gateway, stack = scenario_patches(_TWO_READS)
    with (
        stack,
        patch("app.chat.tool_loop.execute_tool", new=_second_read_fails(error)),
        pytest.raises(ResearchNotConfigured) as info,
    ):
        await run_chat_tool_loop(MagicMock(), **loop_kwargs(_TWO_READS, gateway))

    assert info.value is error
    assert str(info.value) == "not configured"
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    assert not info.value.__suppress_context__
    # The innermost frame is still the tool stub that raised.
    tb = info.value.__traceback__
    assert tb is not None
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code.co_name == "_run"


@pytest.mark.asyncio
async def test_cancellation_propagates_as_cancellation_and_fails_the_loop() -> None:
    sc = SCENARIOS["tool_round_then_answer"]
    gateway, stack = scenario_patches(sc)
    started = asyncio.Event()

    async def _hang(*_a: Any, **_k: Any) -> Any:
        started.set()
        await asyncio.Event().wait()

    gateway.chat_completion.side_effect = _hang
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        task = asyncio.ensure_future(loop.next_round())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        # Bounded, so a loop that re-sends the round fails here, not hangs.
        with pytest.raises(InternalError):
            await asyncio.wait_for(loop.next_round(), timeout=2)
    assert gateway.chat_completion.call_count == 1


@pytest.mark.parametrize("name", ["outcome", "done", "calls_used", "allowlist"])
def test_governing_state_cannot_be_assigned(name: str) -> None:
    sc = SCENARIOS["tool_round_then_answer"]
    gateway, stack = scenario_patches(sc)
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
    before = getattr(loop, name)
    with pytest.raises(AttributeError):
        setattr(loop, name, None)
    assert getattr(loop, name) is before


@pytest.mark.asyncio
async def test_server_list_is_fetched_once_per_turn() -> None:
    """Three rounds over an allowlist with a connector tool: one fetch."""
    sc = SCENARIOS["two_tool_rounds_then_cap"]
    gateway, stack = scenario_patches(sc)
    with stack:
        list_servers = cast(AsyncMock, tool_loop.list_servers)
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        assert list_servers.call_count == 0
        while not loop.done:
            await loop.next_round()
        assert list_servers.call_count == 1
        assert list_servers.call_args.kwargs == {"request_id": "req-1"}
    assert gateway.chat_completion.call_count == 3
