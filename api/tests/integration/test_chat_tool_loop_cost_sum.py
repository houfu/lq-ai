"""Integration: a tool-loop turn's reply row records tokens and cost summed over its rounds.

A chat turn that runs the tool loop calls the model several times. These
tests run the real loop (``run_chat_tool_loop`` is not mocked) against a
stub gateway whose rounds each report different tokens and a different
cost, and read the stored reply row:

* two rounds on the non-streaming send path and on the streamed send path;
* a turn that reaches the tool-call cap and runs the final no-tools round,
  on both send paths;
* a turn that pauses for a tool confirmation after one round and is resumed
  for two more: the reply row covers all three rounds;
* a turn paused before the totals were saved (old ``resume_state`` shape):
  it resumes, its tokens are counted from the resume, and its cost is
  stored as unknown (NULL);
* a round with no cost (an unpriced route): tokens are summed, the stored
  cost is NULL (unknown), not a partial sum;
* failure paths: a loop that raises an ``LQAIError`` on the streamed send or
  on resume writes an error row with no totals; on the non-streaming send it
  writes no row; an MCP-authorization stop writes no row;
* one turn where the API's gateway client parses ``cost_estimate`` from the
  gateway's JSON reply (respx), rather than from a stubbed object.

Worked example used throughout (``_R1`` .. ``_R3``):

    round        prompt  completion  cost (USD)  cost (micros)
    1            100     20          0.0123      12300
    2            180     35          0.0217      21700
    3 (final)    260     410         0.0391      39100
    stored       540     465                     73100  (= 0.0731 USD)
"""

from __future__ import annotations

import contextlib
import json as _json
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.autonomous.guard import ToolResult
from app.chat.tool_schemas import ChatToolAllowlist, ToolSpec
from app.clients.gateway import GatewayClient, set_gateway_client
from app.db.session import get_db
from app.errors import LQAIError, MCPAuthorizationRequired, ProviderUnavailable
from app.main import app
from app.models.chat import Message
from app.models.chat_pending_tool_call import ChatPendingToolCall
from app.models.tool_call_log import ToolCallLog
from app.models.user import User
from app.schemas.gateway import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    FinishReason,
)
from app.security import create_access_token, hash_password
from app.security.encryption import (
    MCP_MASTER_KEY_ENV,
    decrypt_payload_envelope,
    encrypt_payload_envelope,
    generate_master_key,
)

GATEWAY_BASE = "http://test-gateway"
GATEWAY_KEY = "test-gw-key"

SEARCH_FN = "search_case_law"
DELETE_FN = "mcp__files__delete_doc"


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Round:
    prompt: int
    completion: int
    cost: float | None


_R1 = _Round(100, 20, 0.0123)
_R2 = _Round(180, 35, 0.0217)
_R3 = _Round(260, 410, 0.0391)


def _response(
    r: _Round,
    *,
    tool_call: str | None = None,
    text: str = "",
) -> ChatCompletionResponse:
    finish: FinishReason
    if tool_call is not None:
        message = ChatCompletionMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": f"call-{uuid.uuid4().hex[:6]}",
                    "type": "function",
                    "function": {"name": tool_call, "arguments": _json.dumps({"q": "x"})},
                }
            ],
        )
        finish = "tool_calls"
    else:
        message = ChatCompletionMessage(role="assistant", content=text)
        finish = "stop"
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=1_700_000_000,
        model="claude-sonnet-4-6",
        choices=[ChatCompletionChoice(index=0, finish_reason=finish, message=message)],
        usage=ChatCompletionUsage(
            prompt_tokens=r.prompt,
            completion_tokens=r.completion,
            total_tokens=r.prompt + r.completion,
        ),
        routed_inference_tier=3,
        routed_provider="anthropic-prod",
        cost_estimate=r.cost,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mcp_master_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Pending-tool-call payloads are envelope-encrypted under this key."""
    key = generate_master_key()
    monkeypatch.setenv(MCP_MASTER_KEY_ENV, key)
    return key


def _override_get_db(db_session: AsyncSession) -> Callable[[], AsyncIterator[AsyncSession]]:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    gw = GatewayClient(base_url=GATEWAY_BASE, gateway_key=GATEWAY_KEY)
    set_gateway_client(gw)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    set_gateway_client(None)
    await gw.aclose()
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"loop-cost-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Loop Cost Test User",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _h(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


def _frames(body: bytes) -> list[dict[str, Any]]:
    frames = []
    for line in body.decode("utf-8").splitlines():
        line = line.strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        with contextlib.suppress(_json.JSONDecodeError):
            frames.append(_json.loads(line[len("data: ") :]))
    return frames


def _allowlist() -> ChatToolAllowlist:
    search = ToolSpec(
        function_name=SEARCH_FN,
        kind="research",
        provider="cl-prod",
        tool="search_case_law",
        read_only=True,
        destructive=False,
        requires_confirmation=False,
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        description="Search case law.",
    )
    delete = ToolSpec(
        function_name=DELETE_FN,
        kind="mcp",
        provider="files",
        tool="delete_doc",
        read_only=False,
        destructive=True,
        requires_confirmation=True,
        parameters={},
        description="Delete a document.",
    )
    return ChatToolAllowlist(specs={SEARCH_FN: search, DELETE_FN: delete})


@contextlib.contextmanager
def _stub_turn(
    responses: list[ChatCompletionResponse | LQAIError],
    *,
    cap: int | None = None,
    real_gateway_client: bool = False,
) -> Iterator[list[ChatCompletionRequest]]:
    """Run the real loop against ``responses``, one per model round.

    An ``LQAIError`` in ``responses`` is raised for that round. Yields the
    list of requests the loop sent, in order. Tools are stubbed: a
    read-only call returns an empty result; a gated call pauses. With
    ``real_gateway_client`` the client's ``chat_completion`` is left as is
    (the test mocks the gateway's HTTP reply instead).
    """
    sent: list[ChatCompletionRequest] = []
    queue = list(responses)

    async def _chat_completion(
        self: GatewayClient, request: ChatCompletionRequest, **_kw: Any
    ) -> ChatCompletionResponse:
        sent.append(request)
        assert queue, "the loop asked for more rounds than the test stubbed"
        item = queue.pop(0)
        if isinstance(item, LQAIError):
            raise item
        return item

    stack = contextlib.ExitStack()
    with stack:
        if not real_gateway_client:
            stack.enter_context(
                patch.object(GatewayClient, "chat_completion", new=_chat_completion)
            )
        stack.enter_context(
            patch.object(
                GatewayClient,
                "get_citation_engine_judge_model",
                new=AsyncMock(return_value="fast"),
            )
        )
        stack.enter_context(
            patch("app.api.chats.assemble_allowlist", new=AsyncMock(return_value=_allowlist()))
        )
        stack.enter_context(
            patch(
                "app.chat.tool_loop.execute_tool",
                new=AsyncMock(
                    return_value=ToolResult(
                        cost_usd=Decimal("0"), data={"results": []}, outcome="success"
                    )
                ),
            )
        )
        stack.enter_context(
            patch("app.chat.tool_loop.resolve_provider_tier", new=AsyncMock(return_value=2))
        )
        stack.enter_context(
            patch("app.chat.tool_loop.list_servers", new=AsyncMock(return_value=[]))
        )
        stack.enter_context(patch("app.mcp.service.list_servers", new=AsyncMock(return_value=[])))
        if cap is not None:
            settings_obj = MagicMock()
            settings_obj.chat_tool_call_cap = cap
            stack.enter_context(patch("app.chat.tool_loop.get_settings", return_value=settings_obj))
        yield sent
        assert not queue, f"{len(queue)} stubbed round(s) were never requested"


async def _new_chat(client: AsyncClient, user: User) -> str:
    resp = await client.post("/api/v1/chats", headers=_h(user), json={"title": "cost-sum"})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _send(client: AsyncClient, user: User, chat_id: str, *, stream: bool) -> Any:
    resp = await client.post(
        f"/api/v1/chats/{chat_id}/messages",
        headers=_h(user),
        json={"content": "research this", "stream": stream},
    )
    assert resp.status_code == 200, resp.text
    return resp


async def _assistant_rows(db: AsyncSession, chat_id: str) -> list[Message]:
    return list(
        (
            await db.execute(
                select(Message).where(
                    Message.chat_id == uuid.UUID(chat_id), Message.role == "assistant"
                )
            )
        )
        .scalars()
        .all()
    )


async def _assistant_row(db: AsyncSession, chat_id: str) -> Message:
    rows = await _assistant_rows(db, chat_id)
    assert len(rows) == 1, f"expected one assistant row, got {len(rows)}"
    await db.refresh(rows[0])
    return rows[0]


def _assert_totals(row: Message, *rounds: _Round) -> None:
    assert row.error_code is None
    expected_micros: int | None = None
    if all(r.cost is not None for r in rounds):
        # Each round converted to micros once, then summed as integers.
        expected_micros = sum(round(r.cost * 1_000_000) for r in rounds if r.cost is not None)
    # One tuple, so a failure shows tokens and cost together.
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        sum(r.prompt for r in rounds),
        sum(r.completion for r in rounds),
        expected_micros,
    )


# ---------------------------------------------------------------------------
# Two rounds, both send paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
async def test_two_round_turn_non_streaming_sums_tokens_and_cost(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([_response(_R1, tool_call=SEARCH_FN), _response(_R2, text="Answer.")]) as sent:
        resp = await _send(client, db_user, chat_id, stream=False)

    assert len(sent) == 2
    row = await _assistant_row(db_session, chat_id)
    _assert_totals(row, _R1, _R2)
    assert row.prompt_tokens == 280
    assert row.completion_tokens == 55
    assert row.cost_estimate_micros == 34_000
    body = resp.json()
    # The response carries the same totals as the stored row.
    assert body["cost_estimate"] == pytest.approx(0.034)
    assert body["message"]["cost_estimate"] == pytest.approx(0.034)
    assert body["message"]["prompt_tokens"] == 280
    assert body["message"]["completion_tokens"] == 55


@pytest.mark.asyncio
@pytest.mark.integration
async def test_two_round_turn_streaming_sums_tokens_and_cost(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([_response(_R1, tool_call=SEARCH_FN), _response(_R2, text="Answer.")]) as sent:
        resp = await _send(client, db_user, chat_id, stream=True)

    assert len(sent) == 2
    row = await _assistant_row(db_session, chat_id)
    _assert_totals(row, _R1, _R2)
    complete = next(f for f in _frames(resp.content) if f.get("type") == "complete")
    assert complete["message"]["tokens_in"] == 280
    assert complete["message"]["tokens_out"] == 55


# ---------------------------------------------------------------------------
# Cap reached: the final no-tools round is counted too
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True], ids=["non_streaming", "streaming"])
async def test_cap_turn_counts_the_synthesis_round(
    client: AsyncClient, db_user: User, db_session: AsyncSession, stream: bool
) -> None:
    chat_id = await _new_chat(client, db_user)
    with _stub_turn(
        [
            _response(_R1, tool_call=SEARCH_FN),
            _response(_R2, tool_call=SEARCH_FN),
            _response(_R3, text="Summary after the cap."),
        ],
        cap=2,
    ) as sent:
        await _send(client, db_user, chat_id, stream=stream)

    assert len(sent) == 3
    assert sent[2].tool_choice == "none", "third round must be the no-tools synthesis round"
    row = await _assistant_row(db_session, chat_id)
    _assert_totals(row, _R1, _R2, _R3)
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        540,
        465,
        73_100,
    )


# ---------------------------------------------------------------------------
# A round with no cost (unpriced route)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True], ids=["non_streaming", "streaming"])
async def test_unpriced_round_leaves_cost_unknown(
    client: AsyncClient, db_user: User, db_session: AsyncSession, stream: bool
) -> None:
    unpriced = _Round(180, 35, None)
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([_response(_R1, tool_call=SEARCH_FN), _response(unpriced, text="Answer.")]):
        await _send(client, db_user, chat_id, stream=stream)

    row = await _assistant_row(db_session, chat_id)
    # One round is unpriced, so the turn's cost is unknown: NULL, not 12300.
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (280, 55, None)


# ---------------------------------------------------------------------------
# Pause after one round, resume for two more
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True], ids=["non_streaming", "streaming"])
async def test_paused_and_resumed_turn_covers_every_round(
    client: AsyncClient, db_user: User, db_session: AsyncSession, stream: bool
) -> None:
    chat_id = await _new_chat(client, db_user)

    # Send: round 1 proposes a gated call, so the turn pauses.
    with _stub_turn([_response(_R1, tool_call=DELETE_FN)]):
        await _send(client, db_user, chat_id, stream=stream)

    pending = (
        (
            await db_session.execute(
                select(ChatPendingToolCall).where(ChatPendingToolCall.chat_id == uuid.UUID(chat_id))
            )
        )
        .scalars()
        .one()
    )
    state = decrypt_payload_envelope(pending.resume_state)
    assert state["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "priced_cost_micros": 12_300,
        "unpriced_rounds": 0,
        "rounds": 1,
    }
    # No reply row yet: the paused turn has not answered.
    assert (
        await db_session.execute(
            select(Message).where(
                Message.chat_id == uuid.UUID(chat_id), Message.role == "assistant"
            )
        )
    ).scalars().first() is None

    # Resume: round 2 runs a read-only tool, round 3 answers.
    with _stub_turn(
        [_response(_R2, tool_call=SEARCH_FN), _response(_R3, text="Deleted and checked.")]
    ) as sent:
        resp = await client.post(
            f"/api/v1/chats/{chat_id}/tool-calls/{pending.id}",
            headers=_h(db_user),
            json={"decision": "approve"},
        )
    assert resp.status_code == 200, resp.text
    assert len(sent) == 2

    row = await _assistant_row(db_session, chat_id)
    _assert_totals(row, _R1, _R2, _R3)
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        540,
        465,
        73_100,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_second_pause_carries_the_running_totals(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    """A resumed turn that pauses again saves the totals of all rounds so far."""
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([_response(_R1, tool_call=DELETE_FN)]):
        await _send(client, db_user, chat_id, stream=True)
    first = (
        (
            await db_session.execute(
                select(ChatPendingToolCall).where(ChatPendingToolCall.chat_id == uuid.UUID(chat_id))
            )
        )
        .scalars()
        .one()
    )

    with _stub_turn([_response(_R2, tool_call=DELETE_FN)]):
        resp = await client.post(
            f"/api/v1/chats/{chat_id}/tool-calls/{first.id}",
            headers=_h(db_user),
            json={"decision": "deny"},
        )
    assert resp.status_code == 200, resp.text
    gate = next(f for f in _frames(resp.content) if f.get("type") == "tool_confirmation_required")
    second = await db_session.get(ChatPendingToolCall, uuid.UUID(gate["pending_call_id"]))
    assert second is not None
    state = decrypt_payload_envelope(second.resume_state)
    assert state["usage"] == {
        "prompt_tokens": 280,
        "completion_tokens": 55,
        "priced_cost_micros": 34_000,
        "unpriced_rounds": 0,
        "rounds": 2,
    }


# ---------------------------------------------------------------------------
# A turn paused in the old state shape
# ---------------------------------------------------------------------------


async def _seed_pending(
    db_session: AsyncSession,
    user: User,
    chat_id_str: str,
    *,
    usage: dict[str, int] | None,
) -> ChatPendingToolCall:
    """Write a pending row by hand. ``usage=None`` is the pre-change shape."""
    chat_id = uuid.UUID(chat_id_str)
    assistant_message_id = uuid.uuid4()
    state: dict[str, Any] = {
        "messages": [{"role": "user", "content": "delete it"}],
        "calls_used": 0,
        "model": "smart",
        "skill_names": [],
    }
    if usage is not None:
        state["usage"] = usage
    tcl = ToolCallLog(
        origin="chat",
        provider="files",
        tool="delete_doc",
        tier=2,
        intent=None,
        confirmation_state="pending_confirmation",
        outcome="pending",
        cost_usd=None,
        args_digest="deadbeef" * 8,
        user_id=user.id,
        chat_id=chat_id,
        message_id=assistant_message_id,
    )
    db_session.add(tcl)
    await db_session.flush()
    pending = ChatPendingToolCall(
        chat_id=chat_id,
        user_id=user.id,
        assistant_message_id=assistant_message_id,
        function_name=DELETE_FN,
        kind="mcp",
        provider="files",
        tool="delete_doc",
        destructive=True,
        tier=2,
        tool_call_args=encrypt_payload_envelope({"q": "x"}),
        resume_state=encrypt_payload_envelope(state),
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        tool_call_log_id=tcl.id,
    )
    db_session.add(pending)
    await db_session.commit()
    return pending


@pytest.mark.asyncio
@pytest.mark.integration
async def test_turn_paused_in_old_state_shape_stores_cost_unknown_tokens_from_resume(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    """A pending row saved before the totals existed has no ``usage`` key.

    The rounds before the pause were never recorded, so neither total can
    cover the whole turn. Tokens are counted from the resume (a partial
    count, stated in HONEST-STATE). The cost is stored as unknown (NULL),
    because a sum of only the resumed rounds would read as the turn's cost.
    """
    chat_id_str = await _new_chat(client, db_user)
    pending = await _seed_pending(db_session, db_user, chat_id_str, usage=None)

    with _stub_turn([_response(_R2, tool_call=SEARCH_FN), _response(_R3, text="Not deleted.")]):
        resp = await client.post(
            f"/api/v1/chats/{chat_id_str}/tool-calls/{pending.id}",
            headers=_h(db_user),
            json={"decision": "deny"},
        )
    assert resp.status_code == 200, resp.text

    row = await _assistant_row(db_session, chat_id_str)
    assert row.error_code is None
    # Tokens from the resume onward (R2 + R3); cost unknown, not 60 800.
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        440,
        445,
        None,
    )


# ---------------------------------------------------------------------------
# Failure paths: what is and is not recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
async def test_loop_error_on_streamed_send_writes_error_row_without_totals(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    """Round 2 raises an ``LQAIError``: the row has the error code and no totals."""
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([_response(_R1, tool_call=SEARCH_FN), ProviderUnavailable("down")]):
        await _send(client, db_user, chat_id, stream=True)

    row = await _assistant_row(db_session, chat_id)
    assert row.error_code is not None
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        None,
        None,
        None,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_loop_error_on_non_streaming_send_writes_no_row(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([_response(_R1, tool_call=SEARCH_FN), ProviderUnavailable("down")]):
        resp = await client.post(
            f"/api/v1/chats/{chat_id}/messages",
            headers=_h(db_user),
            json={"content": "research this", "stream": False},
        )
    assert resp.status_code >= 400
    assert await _assistant_rows(db_session, chat_id) == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_loop_error_on_resume_writes_error_row_without_totals(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    """Saved totals from before the pause are lost when the resumed loop raises."""
    chat_id = await _new_chat(client, db_user)
    pending = await _seed_pending(
        db_session,
        db_user,
        chat_id,
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "priced_cost_micros": 12_300,
            "unpriced_rounds": 0,
            "rounds": 1,
        },
    )
    with _stub_turn([ProviderUnavailable("down")]):
        resp = await client.post(
            f"/api/v1/chats/{chat_id}/tool-calls/{pending.id}",
            headers=_h(db_user),
            json={"decision": "deny"},
        )
    assert resp.status_code == 200, resp.text

    row = await _assistant_row(db_session, chat_id)
    assert row.error_code is not None
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        None,
        None,
        None,
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True], ids=["non_streaming", "streaming"])
async def test_mcp_authorization_stop_writes_no_row(
    client: AsyncClient, db_user: User, db_session: AsyncSession, stream: bool
) -> None:
    chat_id = await _new_chat(client, db_user)
    with (
        _stub_turn([_response(_R1, tool_call=SEARCH_FN)]),
        patch(
            "app.chat.tool_loop.execute_tool",
            new=AsyncMock(side_effect=MCPAuthorizationRequired("cl-prod")),
        ),
    ):
        await _send(client, db_user, chat_id, stream=stream)
    assert await _assistant_rows(db_session, chat_id) == []


# ---------------------------------------------------------------------------
# The API's gateway client parses cost_estimate from the gateway's JSON
# ---------------------------------------------------------------------------


def _raw_round(prompt: int, completion: int, cost: float, *, tool: str | None) -> dict[str, Any]:
    """A gateway response body as JSON, not a parsed model object."""
    message: dict[str, Any] = {"role": "assistant", "content": "Answer."}
    finish = "stop"
    if tool is not None:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": tool, "arguments": "{}"}}
            ],
        }
        finish = "tool_calls"
    return {
        "id": "chatcmpl-raw",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": "claude-sonnet-4-6",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
        "routed_inference_tier": 3,
        "routed_provider": "anthropic-prod",
        "routed_model": "claude-sonnet-4-6",
        "cost_estimate": cost,
    }


@pytest.mark.asyncio
@pytest.mark.integration
@respx.mock
async def test_cost_is_parsed_from_gateway_json_by_the_real_client(
    client: AsyncClient, db_user: User, db_session: AsyncSession
) -> None:
    """``GatewayClient.chat_completion`` is not stubbed; the gateway's HTTP reply is."""
    route = respx.post(f"{GATEWAY_BASE}/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=_raw_round(100, 20, 0.0123, tool=SEARCH_FN)),
            httpx.Response(200, json=_raw_round(180, 35, 0.0217, tool=None)),
        ]
    )
    chat_id = await _new_chat(client, db_user)
    with _stub_turn([], real_gateway_client=True):
        await _send(client, db_user, chat_id, stream=False)

    assert route.call_count == 2
    row = await _assistant_row(db_session, chat_id)
    assert (row.prompt_tokens, row.completion_tokens, row.cost_estimate_micros) == (
        280,
        55,
        34_000,
    )
