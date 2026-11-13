"""Agent file format v1: property tests.

* any name that matches the rule (lowercase letters, digits and hyphens,
  starting with a letter, at most 64) is accepted, and any other text is
  refused;
* the fingerprint does not depend on the line endings the file arrived with;
* saving is stable: validating the saved text again gives the same text and
  fingerprint;
* the validator never raises, whatever text it is given.
"""

from __future__ import annotations

import re

from hypothesis import given, strategies as st

from app.agents import NAME_MAX_LENGTH, fingerprint_agent_text, validate_agent_file

_RULE = re.compile(r"^[a-z][a-z0-9-]*$")

valid_names = st.from_regex(r"\A[a-z][a-z0-9-]{0,63}\Z")
# Hypothesis leaves out surrogates by default, so every value is encodable.
any_text = st.text(max_size=80)


def agent_text(name: str, body: str = "", version: int | None = None) -> str:
    version_line = f"version: {version}\n" if version is not None else ""
    return (
        "---\nschema: 1\n"
        f"{version_line}"
        f"name: {name}\n"
        "description: A property test.\n"
        "tools: chat\n"
        f"---\n{body}"
    )


@given(valid_names)
def test_every_name_matching_the_rule_is_accepted(name: str) -> None:
    result = validate_agent_file(agent_text(name))
    assert result.agent is not None
    assert result.agent.name == name


@given(any_text)
def test_names_outside_the_rule_are_refused(name: str) -> None:
    quoted = '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
    result = validate_agent_file(agent_text(quoted))
    matches = bool(_RULE.fullmatch(name)) and len(name) <= NAME_MAX_LENGTH
    assert (result.agent is not None) == matches


@given(st.lists(st.text(alphabet="abc é#:-", max_size=20), max_size=6))
def test_fingerprint_ignores_line_endings(lines: list[str]) -> None:
    lf = "\n".join(lines)
    assert fingerprint_agent_text(lf) == fingerprint_agent_text(lf.replace("\n", "\r\n"))
    assert fingerprint_agent_text(lf) == fingerprint_agent_text(lf.replace("\n", "\r"))


@given(
    valid_names,
    st.text(max_size=200),
    st.one_of(st.none(), st.integers(min_value=1, max_value=10_000)),
)
def test_saving_the_saved_text_again_changes_nothing(
    name: str, body: str, version: int | None
) -> None:
    first = validate_agent_file(agent_text(name, body, version), mode="store")
    assert first.agent is not None
    second = validate_agent_file(first.agent.text, mode="store")
    assert second.agent is not None
    assert second.agent.text == first.agent.text
    assert second.agent.fingerprint == first.agent.fingerprint
    assert second.notices == ()


@given(st.text(max_size=400))
def test_validator_never_raises(text: str) -> None:
    for mode in ("store", "repo"):
        result = validate_agent_file(text, mode=mode)
        assert (result.agent is None) == bool(result.problems)


@given(st.text(alphabet="-:abc{}[]&*!<>#'\" \n\t1", max_size=200))
def test_validator_never_raises_on_yaml_like_front_matter(front: str) -> None:
    result = validate_agent_file(f"---\n{front}\n---\n")
    assert (result.agent is None) == bool(result.problems)
