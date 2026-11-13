"""Unit tests for the tool loop's token-and-cost sum (``LoopUsage``).

The reply-row behaviour is covered end to end in
``tests/integration/test_chat_tool_loop_cost_sum.py``; these tests pin the
accumulator itself and the loop's use of it without the HTTP layer.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat.tool_loop import (
    LoopConfirmation,
    LoopFinal,
    LoopUsage,
    _round_usage,
    run_chat_tool_loop,
)
from app.chat.tool_schemas import ChatToolAllowlist, ToolSpec
from app.schemas.gateway import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    FinishReason,
)


def _resp(
    prompt: int, completion: int, cost: float | None, *, tool: str | None = None
) -> ChatCompletionResponse:
    finish: FinishReason
    if tool is None:
        message = ChatCompletionMessage(role="assistant", content="done")
        finish = "stop"
    else:
        message = ChatCompletionMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps({})},
                }
            ],
        )
        finish = "tool_calls"
    return ChatCompletionResponse(
        id="x",
        created=0,
        model="m",
        choices=[ChatCompletionChoice(index=0, finish_reason=finish, message=message)],
        usage=ChatCompletionUsage(
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
        ),
        cost_estimate=cost,
    )


# ---------------------------------------------------------------------------
# LoopUsage
# ---------------------------------------------------------------------------


def test_usage_sums_rounds_in_integer_micros() -> None:
    usage = LoopUsage()
    for _ in range(10):
        usage.add_round(*_round_usage(_resp(1, 2, 0.1)))
    assert usage.rounds == 10
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 20
    # Integer micros: exactly 1 USD, not a float sum of ten 0.1s.
    assert usage.cost_micros == 1_000_000
    assert isinstance(usage.cost_micros, int)


def test_unpriced_round_makes_cost_unknown_but_keeps_tokens() -> None:
    usage = LoopUsage()
    usage.add_round(100, 20, 12_300)
    usage.add_round(*_round_usage(_resp(180, 35, None)))
    assert usage.prompt_tokens == 280
    assert usage.completion_tokens == 55
    assert usage.unpriced_rounds == 1
    assert usage.priced_cost_micros == 12_300
    assert usage.cost_micros is None
    assert usage.cost_usd is None


def test_zero_cost_is_known_zero_not_unknown() -> None:
    usage = LoopUsage()
    usage.add_round(*_round_usage(_resp(5, 5, 0.0)))
    assert usage.cost_micros == 0
    assert usage.cost_usd == 0.0


def test_state_round_trip() -> None:
    usage = LoopUsage(
        prompt_tokens=7, completion_tokens=8, priced_cost_micros=9, unpriced_rounds=1, rounds=3
    )
    assert LoopUsage.from_state(usage.to_state()) == usage
    # JSON-safe, as resume_state is stored as JSON.
    assert LoopUsage.from_state(json.loads(json.dumps(usage.to_state()))) == usage


@pytest.mark.parametrize(
    "state",
    [None, {}, "garbage", {"prompt_tokens": "7", "rounds": True, "priced_cost_micros": 1.5}],
)
def test_from_state_defaults_every_missing_or_bad_key_to_zero(state: Any) -> None:
    assert LoopUsage.from_state(state) == LoopUsage()


def test_partial_state_keeps_present_keys() -> None:
    assert LoopUsage.from_state({"prompt_tokens": 4}) == LoopUsage(prompt_tokens=4)


def test_round_usage_tolerates_a_response_without_usage_or_cost() -> None:
    resp = MagicMock()
    resp.usage = None
    resp.cost_estimate = None
    assert _round_usage(resp) == (0, 0, None)


# ---------------------------------------------------------------------------
# run_chat_tool_loop
# ---------------------------------------------------------------------------


def _allowlist() -> ChatToolAllowlist:
    return ChatToolAllowlist(
        specs={
            "mcp__s__delete": ToolSpec(
                function_name="mcp__s__delete",
                kind="mcp",
                provider="s",
                tool="delete",
                read_only=False,
                destructive=True,
                requires_confirmation=True,
                parameters={},
                description="delete",
            )
        }
    )


def _req() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="smart", messages=[ChatCompletionMessage(role="user", content="hi")]
    )


@pytest.mark.asyncio
async def test_resumed_loop_continues_from_carried_totals() -> None:
    carried = LoopUsage(
        prompt_tokens=100, completion_tokens=20, priced_cost_micros=12_300, rounds=1
    )
    gateway = AsyncMock()
    gateway.chat_completion.return_value = _resp(180, 35, 0.0217)

    with patch("app.chat.tool_loop.list_servers", new=AsyncMock(return_value=[])):
        outcome = await run_chat_tool_loop(
            MagicMock(),
            user=MagicMock(),
            gateway=gateway,
            base_request=_req(),
            allowlist=_allowlist(),
            assistant_message_id=uuid.uuid4(),
            usage=carried,
        )

    assert isinstance(outcome, LoopFinal)
    assert outcome.usage is not None
    assert (outcome.usage_prompt, outcome.usage_completion) == (280, 55)
    assert outcome.usage.cost_micros == 34_000
    assert outcome.usage.rounds == 2
    # The caller's object is not changed.
    assert carried.rounds == 1


@pytest.mark.asyncio
async def test_confirmation_outcome_includes_the_proposing_round() -> None:
    gateway = AsyncMock()
    gateway.chat_completion.return_value = _resp(100, 20, 0.0123, tool="mcp__s__delete")

    with (
        patch("app.chat.tool_loop.list_servers", new=AsyncMock(return_value=[])),
        patch("app.chat.tool_loop.resolve_provider_tier", new=AsyncMock(return_value=2)),
    ):
        outcome = await run_chat_tool_loop(
            MagicMock(),
            user=MagicMock(),
            gateway=gateway,
            base_request=_req(),
            allowlist=_allowlist(),
            assistant_message_id=uuid.uuid4(),
        )

    assert isinstance(outcome, LoopConfirmation)
    assert outcome.usage.to_state() == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "priced_cost_micros": 12_300,
        "unpriced_rounds": 0,
        "rounds": 1,
    }
