"""The tool loop hands control back after each round (``ChatToolLoop``).

The scenarios and stubs are those of ``test_tool_loop_request_golden.py``:
the same gateway responses, ``execute_tool`` stub and cap setting.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.chat import tool_loop
from app.chat.tool_loop import (
    ChatToolLoop,
    LoopConfirmation,
    LoopFinal,
    LoopMcpAuth,
    LoopRound,
    run_chat_tool_loop,
)
from app.errors import GatewayUnreachable, InternalError, ResearchNotConfigured
from tests.chat.test_tool_loop_request_golden import (
    SCENARIOS,
    Scenario,
    _call,
    _resp,
    loop_kwargs,
    scenario_patches,
)


async def _step_all(loop: ChatToolLoop) -> list[LoopRound]:
    rounds: list[LoopRound] = []
    while not loop.done:
        rounds.append(await loop.next_round())
    return rounds


def _execute_mock() -> AsyncMock:
    return cast(AsyncMock, tool_loop.execute_tool)


@pytest.mark.asyncio
async def test_caller_sees_one_result_per_round_in_order() -> None:
    sc = SCENARIOS["two_tool_rounds_then_cap"]
    gateway, stack = scenario_patches(sc)
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        rounds = await _step_all(loop)

    # Checked after the turn has ended, so a shared usage object would show.
    assert [r.number for r in rounds] == [1, 2, 3]
    assert [r.tools_offered for r in rounds] == [True, True, False]
    assert [r.tool_names for r in rounds] == [
        ("mcp__s__read", "nope"),
        ("mcp__s__read", "mcp__s__read"),
        (),
    ]
    assert [r.governed_calls for r in rounds] == [1, 2, 0]
    assert [r.calls_used for r in rounds] == [1, 3, 3]
    assert [r.usage.rounds for r in rounds] == [1, 2, 3]
    assert [(r.usage.prompt_tokens, r.usage.completion_tokens) for r in rounds] == [
        (10, 1),
        (30, 3),
        (60, 6),
    ]
    assert [r.usage.cost_micros for r in rounds] == [1_000, 3_000, 6_000]
    assert [r.outcome is None for r in rounds] == [True, True, False]
    final = rounds[-1].outcome
    assert isinstance(final, LoopFinal)
    assert final.text == "synthesised"
    assert final.usage == rounds[-1].usage
    assert all(r.usage is not loop.usage for r in rounds)


@pytest.mark.asyncio
async def test_round_numbers_restart_on_resume_while_usage_counts_the_turn() -> None:
    sc = SCENARIOS["resumed_with_usage"]
    gateway, stack = scenario_patches(sc)
    with stack:
        rounds = await _step_all(ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway)))

    assert [r.number for r in rounds] == [1, 2]
    assert [r.usage.rounds for r in rounds] == [2, 3]
    assert [r.tools_offered for r in rounds] == [True, False]
    assert rounds[0].calls_used == 2


@pytest.mark.parametrize(
    ("name", "names", "kind"),
    [
        (
            "read_then_confirmation_pause",
            ("mcp__s__read", "mcp__s__delete", "mcp__s__read"),
            LoopConfirmation,
        ),
        ("read_then_mcp_auth_pause", ("mcp__s__read",), LoopMcpAuth),
    ],
)
@pytest.mark.asyncio
async def test_pause_is_the_outcome_of_the_round_that_paused(
    name: str, names: tuple[str, ...], kind: type
) -> None:
    sc = SCENARIOS[name]
    gateway, stack = scenario_patches(sc)
    with stack:
        rounds = await _step_all(ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway)))

    assert len(rounds) == 2
    assert rounds[0].outcome is None
    assert rounds[0].tool_names == ("mcp__s__read",)
    last = rounds[1]
    assert isinstance(last.outcome, kind)
    assert last.tool_names == names
    # The pause keeps today's count: the round that paused adds nothing to
    # calls_used, though one call in it reached governance.
    assert last.calls_used == 1
    assert last.governed_calls == 1
    assert last.usage.rounds == 2


@pytest.mark.parametrize(("stop_after", "executed"), [(1, 1), (2, 3)])
@pytest.mark.asyncio
async def test_caller_that_stops_after_round_n_sends_no_further_request(
    stop_after: int, executed: int
) -> None:
    sc = SCENARIOS["two_tool_rounds_then_cap"]
    gateway, stack = scenario_patches(sc)
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        for _ in range(stop_after):
            step = await loop.next_round()
            assert step.outcome is None
        execute_calls = _execute_mock().call_count

    assert gateway.chat_completion.call_count == stop_after
    assert execute_calls == executed
    assert not loop.done
    # What was gathered stays readable on the loop.
    assert loop.calls_used == executed
    assert loop.usage.rounds == stop_after


async def _plain(sc: Scenario) -> tuple[Any, list[Any], list[Any]]:
    gateway, stack = scenario_patches(sc)
    with stack:
        outcome = await run_chat_tool_loop(MagicMock(), **loop_kwargs(sc, gateway))
        tools = [c.kwargs["args"] for c in _execute_mock().call_args_list]
    return outcome, [c.args[0] for c in gateway.chat_completion.call_args_list], tools


async def _stepped(sc: Scenario) -> tuple[Any, list[Any], list[Any]]:
    gateway, stack = scenario_patches(sc)
    with stack:
        rounds = await _step_all(ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway)))
        tools = [c.kwargs["args"] for c in _execute_mock().call_args_list]
    assert all(r.outcome is None for r in rounds[:-1])
    return rounds[-1].outcome, [c.args[0] for c in gateway.chat_completion.call_args_list], tools


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@pytest.mark.asyncio
async def test_stepped_outcome_equals_plain_call(name: str) -> None:
    """Final answer, cap with its synthesis round, both pauses, and the rest."""
    plain = await _plain(SCENARIOS[name])
    stepped = await _stepped(SCENARIOS[name])
    assert type(stepped[0]) is type(plain[0])
    assert stepped[0] == plain[0]
    assert stepped[1] == plain[1]
    assert stepped[2] == plain[2]


@pytest.mark.asyncio
async def test_gateway_error_in_a_round_propagates_as_today() -> None:
    sc = Scenario([_resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})])])

    def _gateway_with_error() -> tuple[AsyncMock, Any]:
        gateway, stack = scenario_patches(sc)
        gateway.chat_completion.side_effect = [
            sc.responses[0],
            GatewayUnreachable("down"),
        ]
        return gateway, stack

    gateway, stack = _gateway_with_error()
    with stack, pytest.raises(GatewayUnreachable):
        await run_chat_tool_loop(MagicMock(), **loop_kwargs(sc, gateway))
    assert gateway.chat_completion.call_count == 2

    gateway, stack = _gateway_with_error()
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        first = await loop.next_round()
        assert first.outcome is None
        with pytest.raises(GatewayUnreachable):
            await loop.next_round()
    assert gateway.chat_completion.call_count == 2


@pytest.mark.asyncio
async def test_tool_error_in_a_round_propagates_as_today() -> None:
    sc = Scenario([_resp(1, calls=[_call("a1", "mcp__s__read", {"q": "x"})])])
    failing = AsyncMock(side_effect=ResearchNotConfigured("no"))

    gateway, stack = scenario_patches(sc)
    with (
        stack,
        patch("app.chat.tool_loop.execute_tool", new=failing),
        pytest.raises(ResearchNotConfigured),
    ):
        await run_chat_tool_loop(MagicMock(), **loop_kwargs(sc, gateway))
    assert gateway.chat_completion.call_count == 1

    gateway, stack = scenario_patches(sc)
    with stack, patch("app.chat.tool_loop.execute_tool", new=failing):
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        with pytest.raises(ResearchNotConfigured):
            await loop.next_round()
    assert gateway.chat_completion.call_count == 1


@pytest.mark.asyncio
async def test_next_round_after_the_end_raises() -> None:
    sc = SCENARIOS["tool_round_then_answer"]
    gateway, stack = scenario_patches(sc)
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        await _step_all(loop)
        with pytest.raises(InternalError):
            await loop.next_round()
    assert gateway.chat_completion.call_count == 2


@pytest.mark.asyncio
async def test_rounds_hand_back_inside_a_streamed_response_generator() -> None:
    """The shape works where the streamed send runs the loop: in the generator.

    Each frame records how many gateway requests had been sent when it was
    yielded, so the body shows round N's frame went out before round N+1's
    request, even though the test client reads the body whole.
    """
    sc = SCENARIOS["two_tool_rounds_then_cap"]
    gateway, stack = scenario_patches(sc)

    async def _generate() -> AsyncIterator[bytes]:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        while not loop.done:
            step = await loop.next_round()
            frame = {
                "round": step.number,
                "tools": list(step.tool_names),
                "requests_sent": gateway.chat_completion.call_count,
            }
            yield f"data: {json.dumps(frame)}\n\n".encode()
        assert isinstance(loop.outcome, LoopFinal)
        yield f"data: {json.dumps({'text': loop.outcome.text})}\n\n".encode()

    app = FastAPI()

    @app.get("/stream")
    async def _stream() -> StreamingResponse:
        return StreamingResponse(_generate(), media_type="text/event-stream")

    with stack:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/stream")

    frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    assert frames == [
        {"round": 1, "tools": ["mcp__s__read", "nope"], "requests_sent": 1},
        {"round": 2, "tools": ["mcp__s__read", "mcp__s__read"], "requests_sent": 2},
        {"round": 3, "tools": [], "requests_sent": 3},
        {"text": "synthesised"},
    ]


@pytest.mark.asyncio
async def test_next_round_reads_base_request_as_it_is_when_the_round_starts() -> None:
    """A caller may rebind the request between rounds; the next round uses it.

    No caller does this yet; the test pins that the loop does not keep a
    private copy taken at the start.
    """
    sc = SCENARIOS["tool_round_then_answer"]
    gateway, stack = scenario_patches(sc)
    with stack:
        loop = ChatToolLoop(MagicMock(), **loop_kwargs(sc, gateway))
        await loop.next_round()
        loop.base_request = loop.base_request.model_copy(update={"temperature": 0.9})
        await loop.next_round()

    sent = [c.args[0] for c in gateway.chat_completion.call_args_list]
    assert [r.temperature for r in sent] == [0.2, 0.9]
