"""Agent file format v1: the store's saved text is the agent that was parsed.

For every file accepted in ``store`` mode, validating the saved text again
must give the same parsed agent, the same saved text and the same
fingerprint, with no ``version`` notice the second time. The files are built
from awkward pieces: ``version`` written many ways and in any position,
comments on and around it, block scalars, flow values, Unicode line breaks
written raw or escaped, and CRLF line endings.
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, strategies as st

from app.agents import AgentFileCheck, validate_agent_file

REQUIRED = ["schema: 1", "name: my-agent", "description: d", "tools: chat"]

OPTIONAL = [
    "title: Kept",
    'title: "Kept \\u2028 escaped"',
    "# a comment",
    "# version: 9",
    "metadata:\n  a: b\n  # inside\n  c: d",
    "metadata: {a: b}",
    "skills:\n  - nda-snapshot\n  - {name: msa-snapshot, optional: true}",
    "knowledge: none",
    "model: local   # a comment",
    "limits: {max_tool_calls: 3}",
    'title: "a\u2028b"',
    "# a\u2029b",
]

VERSIONS = [
    "version: 2",
    "version: 2   # a comment on the version line",
    "version: '2'",
    "version:",
    "version: |\n  2\n  3",
    "version: >-\n  two\n\n  three",
    "version:\n  - 1\n  - 2",
    "version: {a: 1}",
    "version: [1,\n  2]",
    '"version": 2',
    'version: "a\u2028b"',
]


def check_round_trip(text: str) -> AgentFileCheck:
    first = validate_agent_file(text, mode="store")
    if first.agent is None:
        return first
    second = validate_agent_file(first.agent.text, mode="store")
    assert second.agent is not None, (first.agent.text, second.problems)
    assert second.agent == first.agent
    assert second.agent.text == first.agent.text
    assert second.agent.fingerprint == first.agent.fingerprint
    assert all(n.field != "version" for n in second.notices)
    return first


@given(
    st.lists(st.sampled_from(OPTIONAL), max_size=3, unique=True),
    st.sampled_from(VERSIONS),
    st.randoms(use_true_random=False),
    st.booleans(),
    st.sampled_from(["", "Body\n", "Body\n\n  indented\n", "Line one.\r\nLine two.\r\n"]),
)
def test_saved_text_revalidates_to_the_same_agent(
    optional: list[str],
    version: str,
    rng: random.Random,
    crlf: bool,
    body: str,
) -> None:
    lines = [*REQUIRED, *optional, version]
    rng.shuffle(lines)
    text = "---\n" + "\n".join(lines) + "\n---\n" + body
    if crlf:
        text = text.replace("\n", "\r\n")
    check_round_trip(text)


# Review 3, finding 1: a raw line separator above the version line.
REVIEW_3_INPUT = (
    '---\nschema: 1\ndescription: "a\u2028b"\nversion: 2\nname: my-agent\n'
    "tools: chat\ntitle: Kept\n---\nBody\n"
)

ACCEPTED_TABLE = [
    "---\nversion: 2\nschema: 1\nname: a\ndescription: d\ntools: chat\n---\n",
    "---\nschema: 1\nname: a\ndescription: d\ntools: chat\nversion: 2\n---\n",
    "---\nschema: 1\nname: a\ndescription: d\ntools: chat\nversion: 2 # mine\n---\n",
    "---\nschema: 1\nversion: |\n  2\n# kept\nname: a\ndescription: d\ntools: chat\n---\n",
    "---\r\nschema: 1\r\nversion: 2\r\nname: a\r\ndescription: d\r\ntools: chat\r\n---\r\nB\r\n",
    "---\nschema: 1\nname: a\ndescription: >\n  long\n  text\nversion: 3\ntools: chat\n---",
    '---\nschema: 1\nname: a\ndescription: "a\\u2028b"\nversion: 2\ntools: chat\n---\n',
]


@pytest.mark.parametrize("text", ACCEPTED_TABLE)
def test_awkward_files_round_trip(text: str) -> None:
    result = check_round_trip(text)
    assert result.agent is not None, result.problems
    assert [n.field for n in result.notices] == ["version"]


def test_the_review_3_input_is_refused() -> None:
    result = validate_agent_file(REVIEW_3_INPUT, mode="store")
    assert result.agent is None
    assert "a line separator (U+2028)" in result.problems[0].message


@pytest.mark.parametrize(
    ("char", "words"), [("\u2028", "a line separator"), ("\u2029", "a paragraph separator")]
)
@pytest.mark.parametrize(
    "line", ['title: "a{c}b"', "title: a{c}b", "# a{c}b", "metadata:\n  note: a{c}b"]
)
def test_raw_unicode_line_breaks_are_refused_in_the_front_matter(
    char: str, words: str, line: str
) -> None:
    text = "---\nschema: 1\nname: a\ndescription: d\ntools: chat\n" + line.format(c=char)
    result = validate_agent_file(text + "\n---\n", mode="store")
    assert result.agent is None
    assert [p.field for p in result.problems] == ["front matter"]
    message = result.problems[0].message
    number = 6 + line.count(chr(10))
    assert message.startswith(f"Line {number} contains {words} (U+{ord(char):04X})")
    assert "Replace it with an ordinary line break or a space" in message


def test_raw_unicode_line_breaks_stay_legal_in_the_body() -> None:
    text = "---\nschema: 1\nname: a\ndescription: d\ntools: chat\n---\na\u2028b\n"
    assert validate_agent_file(text, mode="store").agent is not None
