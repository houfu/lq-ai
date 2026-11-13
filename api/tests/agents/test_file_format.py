"""Agent file format v1: every rule, accepted and refused.

Pure unit tests: no database, no network.
"""

from __future__ import annotations

import pytest

from app.agents import (
    MAX_BODY_BYTES,
    MAX_FILE_BYTES,
    MAX_FRONT_MATTER_BYTES,
    MAX_SKILLS,
    ROUNDS_LIMIT_FIELD,
    AgentFileCheck,
    AgentFileInvalid,
    KnowledgeRef,
    SkillRef,
    fingerprint_agent_text,
    parse_agent_file,
    validate_agent_file,
)
from app.errors import CODE_VALIDATION_ERROR, LQAIError, ValidationError

MINIMAL = "schema: 1\nname: my-agent\ndescription: Use it for tests.\ntools: chat\n"


def file_text(front: str = MINIMAL, body: str = "") -> str:
    return f"---\n{front}---\n{body}"


def with_line(line: str) -> str:
    return file_text(MINIMAL + line + "\n")


def check(text: str, mode: str = "store") -> AgentFileCheck:
    return validate_agent_file(text, mode=mode)  # type: ignore[arg-type]


def refused(text: str, mode: str = "store") -> dict[str, str]:
    result = check(text, mode)
    assert result.agent is None, "expected the file to be refused"
    assert result.problems
    return {p.field: p.message for p in result.problems}


def accepted(text: str, mode: str = "store") -> AgentFileCheck:
    result = check(text, mode)
    assert result.problems == (), result.problems
    assert result.agent is not None
    return result


# --- The smallest file -------------------------------------------------------


def test_smallest_valid_file_has_schema_name_description_and_tools() -> None:
    agent = accepted(file_text()).agent
    assert agent is not None
    assert agent.schema_version == 1
    assert agent.name == "my-agent"
    assert agent.description == "Use it for tests."
    assert agent.tools == "chat"


def test_defaults_when_optional_fields_are_absent() -> None:
    agent = accepted(file_text()).agent
    assert agent is not None
    assert agent.title == "my-agent"
    assert agent.model is None
    assert agent.skills == ()
    assert agent.knowledge == (KnowledgeRef(name="matter"),)
    assert agent.limits.max_tool_calls is None
    assert agent.metadata == {}
    assert agent.version is None
    assert agent.instructions == ""
    assert agent.has_instructions is False


@pytest.mark.parametrize("missing", ["schema", "name", "description", "tools"])
def test_each_required_field_is_refused_when_absent(missing: str) -> None:
    front = "".join(line + "\n" for line in MINIMAL.splitlines() if not line.startswith(missing))
    problems = refused(file_text(front))
    assert missing in problems
    assert "required" in problems[missing]


def test_all_problems_are_reported_not_only_the_first() -> None:
    problems = refused(file_text("name: Bad Name\nworkspace: own\nfoo: 1\n"))
    assert {"schema", "name", "description", "tools", "workspace", "foo"} <= set(problems)


# --- schema ------------------------------------------------------------------


@pytest.mark.parametrize("value", ["2", "'1'", "1.0", "true", "0", "[1]"])
def test_schema_other_than_the_number_one_is_refused(value: str) -> None:
    problems = refused(file_text(MINIMAL.replace("schema: 1", f"schema: {value}")))
    assert "must be the number 1" in problems["schema"]


# --- name --------------------------------------------------------------------


@pytest.mark.parametrize("name", ["a", "nda-comparer", "x1", "a-b-c", "a" * 64, "a--b", "a-"])
def test_name_accepts_lowercase_letters_digits_and_hyphens_from_a_letter(name: str) -> None:
    agent = accepted(file_text(MINIMAL.replace("my-agent", name))).agent
    assert agent is not None
    assert agent.name == name


@pytest.mark.parametrize("name", ["1abc", "-abc", "Abc", "a_b", "a b", "a.b", "é", "''"])
def test_name_with_other_characters_is_refused(name: str) -> None:
    problems = refused(file_text(MINIMAL.replace("my-agent", name)))
    assert "lowercase letters, digits and hyphens" in problems["name"]


def test_name_over_64_characters_is_refused() -> None:
    problems = refused(file_text(MINIMAL.replace("my-agent", "a" * 65)))
    assert "at most 64" in problems["name"]


def test_name_that_is_not_text_is_refused() -> None:
    problems = refused(file_text(MINIMAL.replace("my-agent", "123")))
    assert "must be text" in problems["name"]


# --- description and title ---------------------------------------------------


def test_title_is_kept_when_given() -> None:
    agent = accepted(with_line("title: My Agent")).agent
    assert agent is not None
    assert agent.title == "My Agent"


@pytest.mark.parametrize("field", ["title", "description"])
@pytest.mark.parametrize("value", ["''", "'   '"])
def test_empty_text_fields_are_refused(field: str, value: str) -> None:
    front = MINIMAL.replace("description: Use it for tests.\n", "") + (
        "description: Use it for tests.\n" if field == "title" else ""
    )
    problems = refused(file_text(front + f"{field}: {value}\n"))
    assert "empty" in problems[field]


@pytest.mark.parametrize("value", ["2026-11-13", "12", "[a]", "null"])
def test_description_that_is_not_text_is_refused(value: str) -> None:
    front = MINIMAL.replace("Use it for tests.", value)
    problems = refused(file_text(front))
    assert "must be text" in problems["description"]


# --- metadata ----------------------------------------------------------------


def test_metadata_is_a_map_of_text() -> None:
    agent = accepted(with_line("metadata: {author: Jane Tan, team: legal}")).agent
    assert agent is not None
    assert agent.metadata == {"author": "Jane Tan", "team": "legal"}


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ("metadata: [a, b]", "metadata"),
        ("metadata: text", "metadata"),
        ("metadata: {count: 3}", "metadata.count"),
        ("metadata: {nested: {a: b}}", "metadata.nested"),
    ],
)
def test_metadata_that_is_not_a_map_of_text_is_refused(line: str, field: str) -> None:
    problems = refused(with_line(line))
    assert field in problems


# --- author (API R43) --------------------------------------------------------


def test_author_is_not_a_field_and_points_to_metadata() -> None:
    problems = refused(with_line("author: Jane Tan"))
    assert "not a field" in problems["author"]
    assert "metadata" in problems["author"]


# --- model -------------------------------------------------------------------


@pytest.mark.parametrize("model", ["local", "smart", "local-fast", "anthropic/claude-x", "a/b/c:1"])
def test_model_alias_or_provider_model_is_accepted_in_store_mode(model: str) -> None:
    agent = accepted(with_line(f"model: {model}")).agent
    assert agent is not None
    assert agent.model == model


@pytest.mark.parametrize("model", ["'two words'", "/x", "x/", "a//b", "''", "null", "3", "[a]"])
def test_malformed_model_is_refused(model: str) -> None:
    problems = refused(with_line(f"model: {model}"))
    assert "model" in problems


def test_repo_mode_refuses_provider_model_and_accepts_an_alias() -> None:
    problems = refused(with_line("model: anthropic/claude-x"), mode="repo")
    assert "alias" in problems["model"]
    accepted(with_line("model: local"), mode="repo")


# --- skills ------------------------------------------------------------------


def test_skills_accept_names_and_optional_entries() -> None:
    agent = accepted(
        with_line("skills: [nda-snapshot, {name: msa-snapshot, optional: true}, {name: x1}]")
    ).agent
    assert agent is not None
    assert agent.skills == (
        SkillRef(name="nda-snapshot"),
        SkillRef(name="msa-snapshot", optional=True),
        SkillRef(name="x1"),
    )


def test_empty_skills_list_means_no_list() -> None:
    agent = accepted(with_line("skills: []")).agent
    assert agent is not None
    assert agent.skills == ()


def test_skills_up_to_the_limit_are_accepted_and_one_more_is_refused() -> None:
    names = ", ".join(f"s{i}" for i in range(MAX_SKILLS))
    accepted(with_line(f"skills: [{names}]"))
    problems = refused(with_line(f"skills: [{names}, extra]"))
    assert f"at most {MAX_SKILLS}" in problems["skills"]


@pytest.mark.parametrize(
    ("line", "field", "words"),
    [
        ("skills: nda-snapshot", "skills", "must be a list"),
        ("skills: [Bad_Name]", "skills[0]", "not a skill name"),
        ("skills: [a, a]", "skills[1]", "listed twice"),
        ("skills: [{name: a}, a]", "skills[1]", "listed twice"),
        ("skills: [3]", "skills[0]", "skill's name"),
        ("skills: [{optional: true}]", "skills[0]", "needs a `name`"),
        ("skills: [{name: a, optional: maybe}]", "skills[0].optional", "true"),
        ("skills: [{name: a, version: 2}]", "skills[0]", "not a field of a skill entry"),
    ],
)
def test_bad_skills_entries_are_refused(line: str, field: str, words: str) -> None:
    problems = refused(with_line(line))
    assert words in problems[field]


def test_always_on_a_skill_is_reserved() -> None:
    problems = refused(with_line("skills: [{name: a, always: true}]"))
    assert "reserved" in problems["skills[0].always"]


# --- knowledge ---------------------------------------------------------------


def test_knowledge_none_is_a_bare_word() -> None:
    agent = accepted(with_line("knowledge: none")).agent
    assert agent is not None
    assert agent.knowledge == "none"


def test_knowledge_matter_is_accepted() -> None:
    agent = accepted(with_line("knowledge: [matter]")).agent
    assert agent is not None
    assert agent.knowledge == (KnowledgeRef(name="matter"),)


@pytest.mark.parametrize(
    ("line", "field", "words"),
    [
        ("knowledge: [none]", "knowledge[0]", "stands alone"),
        ("knowledge: [matter, none]", "knowledge[1]", "stands alone"),
        ("knowledge: []", "knowledge", "knowledge: none"),
        ("knowledge: matter", "knowledge", "must be `none` or a list"),
        ("knowledge: [matter, matter]", "knowledge[1]", "listed twice"),
        ("knowledge: [{name: matter, optional: true}]", "knowledge[0]", "cannot be optional"),
        ("knowledge: [3]", "knowledge[0]", "is `matter`"),
    ],
)
def test_bad_knowledge_is_refused(line: str, field: str, words: str) -> None:
    problems = refused(with_line(line))
    assert words in problems[field]


@pytest.mark.parametrize(
    "line",
    ["knowledge: [nda-positions]", "knowledge: [matter, {name: nda-positions, optional: true}]"],
)
def test_named_knowledge_bases_are_refused_until_stage_2(line: str) -> None:
    problems = refused(with_line(line))
    message = next(m for f, m in problems.items() if f.startswith("knowledge["))
    assert "not supported yet" in message
    assert "Stage 2" in message


def test_optional_does_not_let_a_later_stage_item_save() -> None:
    problems = refused(with_line("knowledge: [{name: nda-positions, optional: true}]"))
    assert "Stage 2" in problems["knowledge[0]"]


# --- tools -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "words"),
    [
        ("none", "Stage 3"),
        ("[research]", "Stage 3"),
        ("[research, connector:docstore]", "Stage 3"),
        ("[{name: 'connector:docstore', optional: true}]", "Stage 3"),
        ("[chat]", "stand alone"),
        ("[chat, research]", "stand alone"),
        ("[none]", "stand alone"),
        ("everything", "must be `chat`"),
        ("3", "must be `chat`"),
    ],
)
def test_tools_other_than_chat_are_refused(value: str, words: str) -> None:
    problems = refused(file_text(MINIMAL.replace("tools: chat", f"tools: {value}")))
    assert words in problems["tools"]


# --- limits ------------------------------------------------------------------


def test_rounds_limit_field_name_is_one_constant() -> None:
    assert ROUNDS_LIMIT_FIELD == "max_tool_calls"


@pytest.mark.parametrize("value", [1, 6, 20, 500])
def test_rounds_limit_is_a_whole_number_of_one_or_more(value: int) -> None:
    agent = accepted(with_line(f"limits: {{{ROUNDS_LIMIT_FIELD}: {value}}}")).agent
    assert agent is not None
    assert agent.limits.max_tool_calls == value


def test_empty_limits_is_accepted() -> None:
    agent = accepted(with_line("limits: {}")).agent
    assert agent is not None
    assert agent.limits.max_tool_calls is None


@pytest.mark.parametrize("value", ["0", "-1", "2.5", "true", "'6'", "null"])
def test_bad_rounds_limit_is_refused(value: str) -> None:
    problems = refused(with_line(f"limits: {{{ROUNDS_LIMIT_FIELD}: {value}}}"))
    assert "1 or more" in problems[f"limits.{ROUNDS_LIMIT_FIELD}"]


@pytest.mark.parametrize("key", ["max_subagents", "max_subagent_tool_calls", "max_result_chars"])
def test_sub_agent_limits_are_reserved(key: str) -> None:
    problems = refused(with_line(f"limits: {{{key}: 3}}"))
    assert "reserved" in problems[f"limits.{key}"]


def test_unknown_limit_is_refused_and_limits_must_be_a_map() -> None:
    assert "not a limit" in refused(with_line("limits: {max_spend: 3}"))["limits.max_spend"]
    assert "must be a set of fields" in refused(with_line("limits: 6"))["limits"]


# --- reserved and unknown fields ---------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "history: chat",
        "workspace: own",
        "subagents: [clause-checker@1]",
        "use_as: tool",
        "memory: true",
        "permissions: all",
    ],
)
def test_reserved_fields_are_refused_with_the_word_reserved(line: str) -> None:
    key = line.split(":")[0]
    problems = refused(with_line(line))
    assert "reserved" in problems[key]


def test_memory_points_to_workspace_and_history() -> None:
    message = refused(with_line("memory: true"))["memory"]
    assert "`workspace`" in message
    assert "`history`" in message


def test_exit_test_step_4_workspace_own_is_refused_as_reserved() -> None:
    with pytest.raises(AgentFileInvalid) as info:
        parse_agent_file(with_line("workspace: own"))
    assert "reserved" in info.value.problems[0].message


@pytest.mark.parametrize("line", ["foo: 1", "maxTurns: 3", "Name: x", "1: x", "true: x"])
def test_unknown_fields_are_refused(line: str) -> None:
    result = check(with_line(line))
    assert result.agent is None
    assert any("not a field" in p.message or "must be text" in p.message for p in result.problems)


# --- version: store and repo modes (annex A3 point 17) -----------------------


def test_store_mode_ignores_version_with_a_notice_and_removes_its_line() -> None:
    text = file_text("schema: 1\nversion: 7   # set by hand\n" + MINIMAL.split("\n", 1)[1])
    result = accepted(text, mode="store")
    assert result.agent is not None
    assert result.agent.version is None
    assert [n.field for n in result.notices] == ["version"]
    assert "version" not in result.agent.text
    assert result.agent.text == file_text()
    assert result.agent.fingerprint == fingerprint_agent_text(file_text())


def test_store_mode_removes_a_version_that_spans_lines() -> None:
    text = file_text(MINIMAL + "version:\n  - 1\n  - 2\nmodel: local\n")
    result = accepted(text, mode="store")
    assert result.agent is not None
    assert result.agent.text == file_text(MINIMAL + "model: local\n")


def test_store_mode_ignores_any_version_value() -> None:
    accepted(with_line("version: not-a-number"), mode="store")


def test_store_mode_refuses_version_it_cannot_remove_cleanly() -> None:
    flow = file_text("{schema: 1, name: a, description: d, tools: chat, version: 2}\n")
    assert "version" in refused(flow, mode="store")


def test_repo_mode_keeps_version() -> None:
    result = accepted(with_line("version: 3"), mode="repo")
    assert result.agent is not None
    assert result.agent.version == 3
    assert result.notices == ()
    assert "version: 3" in result.agent.text


@pytest.mark.parametrize("value", ["0", "-2", "1.5", "true", "'1'"])
def test_repo_mode_refuses_a_bad_version(value: str) -> None:
    assert "whole number" in refused(with_line(f"version: {value}"), mode="repo")["version"]


def test_repo_mode_version_is_optional() -> None:
    result = accepted(file_text(), mode="repo")
    assert result.agent is not None
    assert result.agent.version is None


# --- body --------------------------------------------------------------------


def test_body_is_kept_exactly() -> None:
    body = "You compare NDAs.\n\n1. Search.\n"
    agent = accepted(file_text(body=body)).agent
    assert agent is not None
    assert agent.instructions == body
    assert agent.has_instructions is True


@pytest.mark.parametrize("ending", ["---", "---\n", "---  \n", "---\n\n  \n"])
def test_empty_or_blank_body_is_valid(ending: str) -> None:
    agent = accepted(f"---\n{MINIMAL}{ending}").agent
    assert agent is not None
    assert agent.has_instructions is False


def test_body_at_the_cap_is_accepted_and_one_byte_more_is_refused() -> None:
    accepted(file_text(body="a" * MAX_BODY_BYTES))
    problems = refused(file_text(body="a" * (MAX_BODY_BYTES + 1)))
    assert "at most" in problems["body"]


def test_body_cap_counts_bytes_not_characters() -> None:
    problems = refused(file_text(body="é" * (MAX_BODY_BYTES // 2 + 1)))
    assert "body" in problems


def test_front_matter_over_its_cap_is_refused() -> None:
    padding = "# " + "x" * MAX_FRONT_MATTER_BYTES + "\n"
    problems = refused(file_text(MINIMAL + padding))
    assert "at most" in problems["front matter"]


def test_file_over_the_total_cap_is_refused_before_parsing() -> None:
    problems = refused("x" * (MAX_FILE_BYTES + 1))
    assert "at most" in problems["file"]


# --- structure and YAML ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no front matter",
        "\n---\nschema: 1\n---\n",
        "---\nschema: 1\nname: a\n",
        "﻿" + "---\n" + MINIMAL + "---\n",
    ],
)
def test_file_without_proper_front_matter_is_refused(text: str) -> None:
    assert "file" in refused(text)


def test_front_matter_that_is_not_a_map_is_refused() -> None:
    assert "set of fields" in refused("---\n- a\n- b\n---\n")["front matter"]


def test_empty_front_matter_reports_the_required_fields() -> None:
    problems = refused("---\n---\n")
    assert {"schema", "name", "description", "tools"} <= set(problems)


def test_invalid_yaml_is_refused_with_a_line_number() -> None:
    message = refused(file_text(MINIMAL + "skills: [a\n"))["front matter"]
    assert "not valid YAML" in message
    assert "line" in message


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        ("name: other\n", "appears twice"),
        ("'name': other\n", "appears twice"),
        ("limits: {max_tool_calls: 1, max_tool_calls: 2}\n", "appears twice"),
        ("skills: [{name: a, name: b}]\n", "appears twice"),
    ],
)
def test_duplicate_keys_are_refused(extra: str, words: str) -> None:
    assert words in refused(file_text(MINIMAL + extra))["front matter"]


def test_anchors_and_aliases_are_refused() -> None:
    text = file_text(MINIMAL + "metadata: &m {a: b}\ntitle: *m\n")
    assert "Anchors and aliases" in refused(text)["front matter"]


def test_merge_keys_are_refused() -> None:
    text = file_text(MINIMAL + "limits: {<<: {max_tool_calls: 2}}\n")
    assert "Merge keys" in refused(text)["front matter"]


def test_python_tags_are_refused() -> None:
    text = file_text(MINIMAL + "title: !!python/object:os.system x\n")
    assert "not valid YAML" in refused(text)["front matter"]


def test_comments_are_kept_in_the_saved_text() -> None:
    text = file_text(MINIMAL + "# a comment\n")
    agent = accepted(text).agent
    assert agent is not None
    assert "# a comment" in agent.text


# --- line endings and the fingerprint (annex A4) -----------------------------


def test_crlf_and_lf_files_parse_the_same_and_share_a_fingerprint() -> None:
    lf = file_text(body="Line one.\nLine two.\n")
    crlf = lf.replace("\n", "\r\n")
    a = accepted(lf).agent
    b = accepted(crlf).agent
    assert a is not None and b is not None
    assert a.text == b.text == lf
    assert a.fingerprint == b.fingerprint == fingerprint_agent_text(lf)


def test_fingerprint_is_sha256_hex_of_the_normalised_text() -> None:
    assert fingerprint_agent_text("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert fingerprint_agent_text("a\r\nb\rc\n") == fingerprint_agent_text("a\nb\nc\n")


def test_a_changed_comment_changes_the_fingerprint() -> None:
    a = accepted(file_text(MINIMAL + "# one\n")).agent
    b = accepted(file_text(MINIMAL + "# two\n")).agent
    assert a is not None and b is not None
    assert a.fingerprint != b.fingerprint


def test_key_order_is_not_normalised() -> None:
    lines = MINIMAL.splitlines(keepends=True)
    a = accepted(file_text("".join(lines))).agent
    b = accepted(file_text("".join(reversed(lines)))).agent
    assert a is not None and b is not None
    assert a.fingerprint != b.fingerprint


# --- the exception -----------------------------------------------------------


def test_parse_raises_the_project_validation_error_with_every_problem() -> None:
    with pytest.raises(AgentFileInvalid) as info:
        parse_agent_file(file_text("name: Bad\n"))
    error = info.value
    assert isinstance(error, ValidationError)
    assert isinstance(error, LQAIError)
    assert error.effective_code == CODE_VALIDATION_ERROR
    fields = {p["field"] for p in error.details["problems"]}
    assert {"schema", "name", "description", "tools"} <= fields
    assert all(set(p) == {"field", "message"} for p in error.details["problems"])


def test_parse_returns_the_file_when_valid() -> None:
    assert parse_agent_file(file_text()).name == "my-agent"


def test_validate_never_raises_for_non_text_input() -> None:
    result = validate_agent_file(3)  # type: ignore[arg-type]
    assert result.agent is None
    assert result.problems[0].field == "file"


def test_text_with_a_lone_surrogate_is_refused() -> None:
    assert "not valid text" in refused(file_text(body="\ud800"))["file"]


def test_metadata_keys_must_be_text() -> None:
    assert "must be text" in refused(with_line("metadata: {1: a}"))["metadata"]


def test_long_values_are_shortened_in_messages() -> None:
    message = refused(file_text(MINIMAL.replace("my-agent", "B" * 64)))["name"]
    assert "..." in message
    assert "B" * 64 not in message


def test_check_result_and_notice_serialise_plainly() -> None:
    result = check(with_line("version: 2"))
    assert result.ok
    assert result.notices[0].as_dict()["field"] == "version"
    assert not check(with_line("workspace: own")).ok


def test_store_mode_keeps_a_comment_after_the_version_line() -> None:
    text = file_text("schema: 1\nversion: |\n  2\n# kept\n" + MINIMAL.split("\n", 1)[1])
    result = accepted(text, mode="store")
    assert result.agent is not None
    assert result.agent.text == file_text("schema: 1\n# kept\n" + MINIMAL.split("\n", 1)[1])
