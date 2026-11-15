"""Agent file format v1: every rule, accepted and refused.

Pure unit tests: no database, no network.
"""

from __future__ import annotations

import pytest

from app.agents import (
    AgentFileCheck,
    AgentFileInvalid,
    AgentFileMode,
    ListedItem,
    fingerprint_agent_text,
    parse_agent_file,
    validate_agent_file,
)
from app.agents.file_format import (
    MAX_BODY_BYTES,
    MAX_FILE_BYTES,
    MAX_FRONT_MATTER_BYTES,
    MAX_SKILLS,
    MODEL_MAX_LENGTH,
    ROUNDS_LIMIT_FIELD,
)
from app.errors import CODE_VALIDATION_ERROR, LQAIError, ValidationError

MINIMAL = "schema: 1\nname: my-agent\ndescription: Use it for tests.\ntools: chat\n"


def file_text(front: str = MINIMAL, body: str = "") -> str:
    return f"---\n{front}---\n{body}"


def with_line(line: str) -> str:
    return file_text(MINIMAL + line + "\n")


def check(text: str, mode: AgentFileMode = "store") -> AgentFileCheck:
    return validate_agent_file(text, mode=mode)


def refused(text: str, mode: AgentFileMode = "store") -> dict[str, str]:
    result = check(text, mode)
    assert result.agent is None, "expected the file to be refused"
    assert result.problems
    return {p.field: p.message for p in result.problems}


def accepted(text: str, mode: AgentFileMode = "store") -> AgentFileCheck:
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
    assert agent.knowledge == (ListedItem(name="matter"),)
    assert agent.limits.max_rounds is None
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


@pytest.mark.parametrize("mode", ["store", "repo"])
def test_model_rules_are_the_same_in_both_modes(mode: AgentFileMode) -> None:
    # Annex A1's "contributed files use aliases only" is for the check on
    # contributed agents, not for either mode here.
    # A repository file must carry `version`; a pasted one need not.
    version = "version: 1\n" if mode == "repo" else ""
    accepted(with_line(version + "model: anthropic/claude-x"), mode=mode)
    accepted(with_line(version + "model: local"), mode=mode)
    assert set(refused(with_line(version + "model: 'two words'"), mode=mode)) == {"model"}


def test_model_length_cap() -> None:
    accepted(with_line("model: " + "a" * MODEL_MAX_LENGTH))
    message = refused(with_line("model: " + "a" * (MODEL_MAX_LENGTH + 1)))["model"]
    assert f"at most {MODEL_MAX_LENGTH} characters" in message


# --- skills ------------------------------------------------------------------


def test_skills_accept_names_and_optional_entries() -> None:
    agent = accepted(
        with_line("skills: [nda-snapshot, {name: msa-snapshot, optional: true}, {name: x1}]")
    ).agent
    assert agent is not None
    assert agent.skills == (
        ListedItem(name="nda-snapshot"),
        ListedItem(name="msa-snapshot", optional=True),
        ListedItem(name="x1"),
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
        ("skills: [{name: a, version: 2}]", "skills[0]", "not one of its fields"),
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
    assert agent.knowledge == (ListedItem(name="matter"),)


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
def test_named_knowledge_bases_are_not_supported_in_this_version(line: str) -> None:
    problems = refused(with_line(line))
    message = next(m for f, m in problems.items() if f.startswith("knowledge["))
    assert "is not supported in this version of LQ.AI" in message
    assert "Stage" not in message


def test_optional_does_not_let_a_not_supported_item_save() -> None:
    # Annex A5(a): refused until the maintainer rules otherwise.
    problems = refused(with_line("knowledge: [{name: nda-positions, optional: true}]"))
    assert "not supported in this version" in problems["knowledge[0]"]


# --- tools -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "words"),
    [
        ("none", "not supported in this version"),
        ("[research]", "not supported in this version"),
        ("[research, connector:docstore]", "not supported in this version"),
        ("[{name: 'connector:docstore', optional: true}]", "not supported in this version"),
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


def test_rounds_limit_is_read_through_the_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents import file_format

    monkeypatch.setattr(file_format, "ROUNDS_LIMIT_FIELD", "max_rounds_renamed")
    agent = accepted(with_line("limits: {max_rounds_renamed: 4}")).agent
    assert agent is not None
    assert agent.limits.max_rounds == 4
    problems = refused(with_line("limits: {max_tool_calls: 4}"))
    assert "`max_rounds_renamed`" in problems["limits.max_tool_calls"]


@pytest.mark.parametrize("value", [1, 6, 20, 500])
def test_rounds_limit_is_a_whole_number_of_one_or_more(value: int) -> None:
    agent = accepted(with_line(f"limits: {{{ROUNDS_LIMIT_FIELD}: {value}}}")).agent
    assert agent is not None
    assert agent.limits.max_rounds == value


def test_empty_limits_is_accepted() -> None:
    agent = accepted(with_line("limits: {}")).agent
    assert agent is not None
    assert agent.limits.max_rounds is None


@pytest.mark.parametrize(
    "value", ["0", "-1", "2.5", "true", "'6'", "null", "010", "0x10", "+1", "1:30", "1_0", "1e3"]
)
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
        parse_agent_file(with_line("workspace: own"), mode="store")
    assert "reserved" in info.value.problems[0].message


@pytest.mark.parametrize("key", ["foo", "maxTurns", "Name"])
def test_unknown_fields_are_refused(key: str) -> None:
    problems = refused(with_line(f"{key}: 1"))
    assert list(problems) == [key]
    assert problems[key].startswith(f"`{key}` is not a field of an agent file.")


@pytest.mark.parametrize(
    ("key", "near"),
    [("descripton", "description"), ("skill", "skills"), ("titel", "title"), ("Name", "name")],
)
def test_a_mistyped_field_gets_the_near_match(key: str, near: str) -> None:
    message = refused(with_line(f"{key}: 1"))[key]
    assert message.endswith(f"Did you mean `{near}`?")


def test_a_field_with_no_near_match_gets_the_list_of_fields() -> None:
    message = refused(with_line("colour: red"))["colour"]
    assert "The fields are `description`, `knowledge`" in message
    for name in ("schema", "name", "title", "tools", "limits", "version"):
        assert f"`{name}`" in message


@pytest.mark.parametrize("line", ["? [a]\n: x", "? {a: b}\n: x", "metadata: {? [a] : b}"])
def test_a_list_or_mapping_as_a_field_name_gets_its_own_message(line: str) -> None:
    message = refused(with_line(line))["front matter"]
    assert "field name written as a list or a set of fields" in message
    assert "tag" not in message


def test_schema_marked_as_text_says_to_remove_the_tag() -> None:
    message = refused(file_text(MINIMAL.replace("schema: 1", "schema: !!str 1")))["schema"]
    assert "marked as text with a tag such as `!!str`" in message
    assert "it is written `1`" not in message


@pytest.mark.parametrize("key", ["null", "~"])
def test_an_empty_field_name_says_what_yaml_read(key: str) -> None:
    message = refused(with_line(f"{key}: x"))["front matter"]
    assert "YAML read as empty" in message


@pytest.mark.parametrize(
    ("key", "words"),
    [("1", "YAML read as the number 1"), ("true", "YAML read as true or false")],
)
def test_field_names_that_are_not_text_are_refused(key: str, words: str) -> None:
    result = check(with_line(f"{key}: x"))
    assert result.agent is None
    assert [p.field for p in result.problems] == ["front matter"]
    assert words in result.problems[0].message


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


def test_store_mode_refuses_one_line_front_matter_with_version() -> None:
    flow = file_text("{schema: 1, name: a, description: d, tools: chat, version: 2}\n")
    message = refused(flow, mode="store")["version"]
    assert "cannot be left out" in message
    assert "removed" not in message
    accepted(flow, mode="repo")
    accepted(file_text("{schema: 1, name: a, description: d, tools: chat}\n"), mode="store")


def test_repo_mode_keeps_version() -> None:
    result = accepted(with_line("version: 3"), mode="repo")
    assert result.agent is not None
    assert result.agent.version == 3
    assert result.notices == ()
    assert "version: 3" in result.agent.text


@pytest.mark.parametrize("value", ["0", "-2", "1.5", "true", "'1'", "01", "0x1"])
def test_repo_mode_refuses_a_bad_version(value: str) -> None:
    assert "whole number" in refused(with_line(f"version: {value}"), mode="repo")["version"]


def test_repo_mode_refuses_a_file_without_version() -> None:
    result = check(file_text(), mode="repo")
    assert result.agent is None
    assert [p.field for p in result.problems] == ["version"]
    message = result.problems[0].message
    assert "`version` is missing" in message
    assert "`version: 1`" in message


def test_repo_mode_reports_a_missing_version_with_the_other_problems() -> None:
    problems = refused(file_text("schema: 1\nname: Bad Name\ntools: chat\n"), mode="repo")
    assert {"version", "name", "description"} <= set(problems)


@pytest.mark.parametrize("value", ["1", "2", "40"])
def test_repo_mode_accepts_a_whole_number_version(value: str) -> None:
    result = accepted(with_line(f"version: {value}"), mode="repo")
    assert result.agent is not None
    assert result.agent.version == int(value)
    assert result.notices == ()


def test_store_mode_saves_a_file_without_version() -> None:
    result = accepted(file_text(), mode="store")
    assert result.agent is not None
    assert result.agent.version is None
    assert result.notices == ()
    assert result.agent.text == file_text()


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
    ],
)
def test_file_without_proper_front_matter_is_refused(text: str) -> None:
    assert "first line must be" in refused(text)["file"] or "not closed" in refused(text)["file"]


def test_byte_order_mark_is_refused_with_its_own_message() -> None:
    assert "byte-order mark" in refused("\ufeff" + file_text())["file"]


def test_front_matter_that_is_not_a_map_is_refused() -> None:
    assert "set of fields" in refused("---\n- a\n- b\n---\n")["front matter"]


def test_empty_front_matter_reports_the_required_fields() -> None:
    problems = refused("---\n---\n")
    assert {"schema", "name", "description", "tools"} <= set(problems)


def test_invalid_yaml_is_refused_with_a_line_number() -> None:
    message = refused(file_text(MINIMAL + "skills: [a\n"))["front matter"]
    assert "cannot be read as YAML" in message
    assert "Line 6" in message


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
    assert "YAML tag" in refused(text)["front matter"]


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
        parse_agent_file(file_text("name: Bad\n"), mode="store")
    error = info.value
    assert isinstance(error, ValidationError)
    assert isinstance(error, LQAIError)
    assert error.effective_code == CODE_VALIDATION_ERROR
    fields = {p["field"] for p in error.details["problems"]}
    assert {"schema", "name", "description", "tools"} <= fields
    assert all(set(p) == {"field", "message"} for p in error.details["problems"])


def test_parse_returns_the_file_when_valid() -> None:
    assert parse_agent_file(file_text(), mode="store").name == "my-agent"


def test_validate_never_raises_for_non_text_input() -> None:
    result = validate_agent_file(3, mode="store")  # type: ignore[arg-type]
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


def test_mode_is_a_required_keyword() -> None:
    with pytest.raises(TypeError):
        validate_agent_file(file_text())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        parse_agent_file(file_text())  # type: ignore[call-arg]


# --- characters (review 1, findings 1 and 8) ---------------------------------


@pytest.mark.parametrize(
    ("text", "field"),
    [
        (file_text(MINIMAL + 'title: "a\\0b"\n'), "title"),
        (file_text(MINIMAL + "title: a\x00b\n"), "front matter"),
        (file_text(body="a\x00b"), "body"),
        (file_text(body="a\x07b"), "body"),
        (file_text(body="a\x85b"), "body"),
        (file_text(MINIMAL + 'model: "loc\\0al"\n'), "model"),
        (file_text(MINIMAL + 'metadata: {team: "a\\x01"}\n'), "metadata.team"),
        (file_text(MINIMAL + 'skills: ["a\\0"]\n'), "skills[0]"),
        (file_text(MINIMAL + "# a comment with \x00\n"), "front matter"),
    ],
)
def test_control_characters_are_refused(text: str, field: str) -> None:
    message = refused(text)[field]
    assert "which cannot be saved. Delete it." in message


@pytest.mark.parametrize(
    ("char", "words"),
    [("\x00", "a null character"), ("\x0b", "a vertical tab"), ("\x0c", "a form feed")],
)
def test_common_control_characters_are_named_in_words(char: str, words: str) -> None:
    assert words in refused(file_text(body=f"a{char}b"))["body"]


def test_tab_and_newline_stay_legal_in_the_body() -> None:
    agent = accepted(file_text(body="Step\tone.\nStep two.\n")).agent
    assert agent is not None
    assert "\t" in agent.instructions


# Characters that hide or reorder text are refused everywhere, the body
# included, so the file shows every instruction the model reads (review 2,
# findings 1 and 3). Joiners and marks that real scripts need stay legal.
HIDING = [
    ("\u202a", "a text-direction override"),
    ("\u202e", "a text-direction override"),
    ("\u2066", "a text-direction isolate"),
    ("\u2069", "a text-direction isolate"),
    ("\u200b", "a zero-width space"),
    ("\ufeff", "a zero-width no-break space"),
    ("\u2060", "a word joiner"),
    ("\u2062", "an invisible maths operator"),
    ("\U000e0000", "an invisible tag character"),
    ("\U000e0041", "an invisible tag character"),
    ("\U000e007f", "an invisible tag character"),
]


@pytest.mark.parametrize(("char", "words"), HIDING)
def test_hiding_characters_are_refused_in_front_matter_values(char: str, words: str) -> None:
    escaped = f"\\U{ord(char):08x}"
    message = refused(with_line(f'title: "a{escaped}b"'))["title"]
    assert f"{words} (U+{ord(char):04X})" in message
    assert "Remove it" not in message


@pytest.mark.parametrize(("char", "words"), HIDING)
def test_hiding_characters_are_refused_in_raw_front_matter_and_comments(
    char: str, words: str
) -> None:
    assert words in refused(with_line(f"title: a{char}b"))["front matter"]
    assert words in refused(with_line(f"# a{char}b"))["front matter"]


@pytest.mark.parametrize(("char", "words"), HIDING)
def test_hiding_characters_are_refused_in_the_body(char: str, words: str) -> None:
    message = refused(file_text(body=f"Do this.{char}\n"))["body"]
    assert message.startswith(f"Line 7 contains {words}")


def test_direction_controls_say_the_screen_does_not_match() -> None:
    message = refused(file_text(body="a\u202eb\n"))["body"]
    assert "changes the order in which text is shown" in message


LEGAL_SCRIPT_TEXT = [
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",  # Persian, zero-width non-joiner
    "\u0915\u094d\u200d\u0937",  # Devanagari, zero-width joiner
    "Judge \U0001f468\u200d\u2696\ufe0f",  # emoji built with a joiner
    "con\u00adfidential",  # soft hyphen, as Word pastes it
    "\u0639\u0642\u062f\u200f",  # Arabic with a right-to-left mark
    "abc\u200e",  # left-to-right mark
    "Cafe\u0301",  # combining accent
]


@pytest.mark.parametrize("value", LEGAL_SCRIPT_TEXT)
def test_joiners_and_marks_real_scripts_need_stay_legal(value: str) -> None:
    agent = accepted(with_line(f'title: "{value}"')).agent
    assert agent is not None
    assert agent.title == value
    assert accepted(with_line(f"# {value}")).agent is not None
    body = accepted(file_text(body=f"{value}\n")).agent
    assert body is not None
    assert body.instructions == f"{value}\n"


def test_title_must_be_one_line() -> None:
    assert refused(with_line('title: "a\\nb"'))["title"] == "`title` must be one line."
    assert refused(with_line('title: "a\\u2028b"'))["title"] == "`title` must be one line."
    accepted(with_line("title: >-\n  one line"))


def test_model_must_be_printable_ascii() -> None:
    problems = refused(with_line("version: 1\nmodel: \uff4c\uff4f\uff43\uff41\uff4c"), mode="repo")
    assert set(problems) == {"model"}
    message = problems["model"]
    assert "plain letters, digits and punctuation" in message


# --- numbers in plain digits (review 1, finding 10) --------------------------


@pytest.mark.parametrize("value", ["0x1", "01", "+1", "1_0", "0b1", "1.0"])
def test_schema_must_be_plain_digits(value: str) -> None:
    message = refused(file_text(MINIMAL.replace("schema: 1", f"schema: {value}")))["schema"]
    assert f"it is written `{value}`" in message
    assert "`schema: 1`" in message


def test_rounds_limit_has_no_upper_bound_at_save() -> None:
    # Annex A3 point 11: clamped at send. The slice that stores the number must
    # not assume it fits an integer column.
    agent = accepted(with_line(f"limits: {{{ROUNDS_LIMIT_FIELD}: 99999999999999999999999}}")).agent
    assert agent is not None
    assert agent.limits.max_rounds == 99999999999999999999999


# --- messages a person can act on (review 1, findings 6 and 7) ---------------


def repo_version(mode: AgentFileMode) -> str:
    """A repository file must carry `version`, so the corpus adds it in that
    mode: each entry is refused for its own fault, not for a missing version."""
    return "version: 1\n" if mode == "repo" else ""


REFUSE_CORPUS: list[tuple[str, AgentFileMode]] = (
    [
        (file_text(MINIMAL.replace(old, new) + repo_version(mode)), mode)
        for old, new in [
            ("my-agent", "no"),
            ("my-agent", "123"),
            ("my-agent", "2026-11-13"),
            ("my-agent", "Bad Name"),
            ("schema: 1", "schema: '1'"),
            ("schema: 1", "schema: true"),
            ("schema: 1", "schema: 0x1"),
            ("schema: 1", "schema: [1]"),
            ("schema: 1", "schema:"),
            ("tools: chat", "tools: yes"),
            ("tools: chat", "tools:"),
            ("tools: chat", "tools: {name: chat, optional: true}"),
            ("tools: chat", "tools: none"),
            ("tools: chat", "tools: [research]"),
            ("tools: chat", "tools: [chat]"),
            ("tools: chat", "tools: 3"),
            ("Use it for tests.", "Use for: NDAs"),
            ("Use it for tests.", "2026-11-13"),
            ("Use it for tests.", "on"),
            ("Use it for tests.", "null"),
        ]
        for mode in ("store", "repo")
    ]
    + [
        (file_text(MINIMAL + repo_version(mode) + line + "\n"), mode)
        for line in [
            "knowledge:",
            "knowledge: true",
            "knowledge: {name: matter}",
            "knowledge: [nda-positions]",
            "knowledge: [3]",
            "knowledge: [true]",
            "knowledge: [{name: x, optional: true}]",
            "metadata: {count: 3}",
            "metadata: {1: a}",
            "metadata: {flag: yes}",
            "metadata: [a]",
            "metadata: true",
            "model: null",
            "model: 3",
            "model: true",
            "model: [a]",
            "model: two words",
            "skills: true",
            "skills: [3]",
            "skills: [true]",
            "skills: [{name: a, optional: maybe}]",
            "skills: [{name: a, optional: 1}]",
            "skills: [{name: a, 1: b}]",
            "skills: [{name: a, always: true}]",
            "skills: [{name: 3}]",
            "limits: true",
            "limits: {max_tool_calls: true}",
            "limits: {max_tool_calls: null}",
            "limits: {max_tool_calls: '6'}",
            "limits: {max_tool_calls: 010}",
            "limits: {1: 2}",
            "limits: {max_subagents: 2}",
            "title: true",
            "title: 12",
            "title: [a]",
            "permissions: all",
            "workspace: own",
            "memory: true",
            "history: chat",
            "author: Jane",
            "1: x",
            "true: x",
            "null: x",
            "\tteam: legal",
            "metadata:\n\tteam: legal",
            "description2: a: b: c",
            "skills: [a",
            "title: !!python/object:os.system x",
            "title: !custom x",
            "? [a]\n: x",
            "metadata: {? [a] : b}",
            "descripton: x",
            "colour: red",
            "~: x",
            "metadata: &m {a: b}",
            "limits: {<<: {max_tool_calls: 2}}",
            "name: again",
            'title: "a\\0b"',
            'title: "\\u202e"',
        ]
        for mode in ("store", "repo")
    ]
    + [
        (file_text(), "repo"),
        (with_line("version: true"), "repo"),
        (with_line("version: '1'"), "repo"),
        (with_line("version: 01"), "repo"),
        ("---\n- a\n---\n", "store"),
        ("---\nfoo\n---\n", "store"),
        ("---\n42\n---\n", "store"),
        ("---\ntrue\n---\n", "store"),
        ("---\n---\n", "store"),
        ("nothing", "store"),
        ("\ufeff" + file_text(), "store"),
        (file_text("{schema: 1, name: a, description: d, tools: chat, version: 2}\n"), "store"),
    ]
)

_LEAKS = (
    "True",
    "False",
    "None",
    "{'",
    "['",
    "datetime",
    "mapping values are not allowed",
    "cannot start any token",
    "while parsing",
    "while scanning",
    "while constructing",
    "could not determine a constructor",
    "found character",
    "expected",
    "Stage ",
    "planned",
    "\\x",
)


@pytest.mark.parametrize(("text", "mode"), REFUSE_CORPUS)
def test_no_refusal_message_leaks_python_or_yaml_wording(text: str, mode: AgentFileMode) -> None:
    result = check(text, mode)
    assert result.agent is None
    for problem in result.problems:
        assert isinstance(problem.field, str)
        for leak in _LEAKS:
            assert leak not in problem.message, (leak, problem.message)


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("my-agent", "no", "name"),
        ("my-agent", "123", "name"),
        ("my-agent", "2026-11-13", "name"),
        ("Use it for tests.", "on", "description"),
    ],
)
def test_values_yaml_reads_as_other_types_get_a_quote_hint(old: str, new: str, field: str) -> None:
    message = refused(file_text(MINIMAL.replace(old, new)))[field]
    assert "Put the value in quotes" in message


def test_a_colon_inside_a_value_gets_a_quote_hint() -> None:
    message = refused(file_text(MINIMAL.replace("Use it for tests.", "Use for: NDAs")))
    assert "Put the whole value in quotes" in message["front matter"]
    assert "Line 4" in message["front matter"]


def test_a_tab_in_the_indentation_is_named() -> None:
    message = refused(with_line("metadata:\n\tteam: legal"))["front matter"]
    assert "uses a tab" in message


def test_a_quoted_schema_says_to_drop_the_quotes() -> None:
    message = refused(file_text(MINIMAL.replace("schema: 1", "schema: '1'")))["schema"]
    assert "in quotes; write the number without quotes" in message
