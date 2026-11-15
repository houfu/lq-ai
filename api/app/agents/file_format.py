"""Agent file format, version 1: parse, validate and fingerprint.

An agent file is Markdown with YAML front matter, like a ``SKILL.md``. The
front matter holds the fields below; the body is the agent's instructions.
This module reads the file alone. It does not look anything up: whether a
named skill exists, whether the operator allows a model, or whether a matter
permits a tool is the check's job, not this one.

The two modes differ only in ``version`` (annex A3 point 17):

* ``store`` is for a file a person pastes or uploads. ``version`` is ignored
  with a notice and its lines are left out of the saved text, because the
  store numbers versions itself.
* ``repo`` is for files kept in the repository, which have no store. Such a
  file must carry ``version``, as a whole number of 1 or more. It is kept in
  the saved text.

Every problem names a field and says what is wrong in plain words. Problems
in the fields are all collected. A file that cannot be read as YAML gets one
problem, since nothing after the error can be read.

The fingerprint is the SHA-256 of the saved text with line endings
normalised to ``\\n``. Keys are not reordered and comments are kept, so a
changed comment is a changed fingerprint.

YAML is read with PyYAML's safe loader, as the skill loader does. Things the
safe loader allows that are refused here: duplicate keys (it keeps the last
one silently), anchors and aliases, merge keys, and numbers written other
than as plain digits where a number is asked for.

Some characters are refused anywhere in the file, the body included:
control characters other than tab and newline, and a named list of
characters that hide or reorder text (see ``_hiding_character_name``). The
raw line and paragraph separators U+2028 and U+2029 are refused in the front
matter only. Other characters that are not shown on screen, such as
variation selectors, are not refused.
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.errors import ValidationError

# --- Constants ---------------------------------------------------------------

NAME_MAX_LENGTH: Final = 64
_NAME_PATTERN: Final = re.compile(r"^[a-z][a-z0-9-]*$")

# Skill slugs as the user-skill store accepts them (``app/api/user_skills.py``).
_SKILL_SLUG_PATTERN: Final = re.compile(r"^[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?$")

# Listed, hand-attached and kept skills together are at most 16 on a turn,
# so a file that lists more could never run.
MAX_SKILLS: Final = 16

# The key under ``limits`` that holds the rounds limit. The name is not
# ruled yet. Every place that reads or names the key uses this constant; the
# parsed value is ``AgentLimits.max_rounds``, which does not depend on it.
ROUNDS_LIMIT_FIELD: Final = "max_tool_calls"

MAX_BODY_BYTES: Final = 32 * 1024
MAX_FRONT_MATTER_BYTES: Final = 16 * 1024
# Checked before anything else, so no larger text is split or parsed.
MAX_FILE_BYTES: Final = MAX_BODY_BYTES + MAX_FRONT_MATTER_BYTES + 1024

MODEL_MAX_LENGTH: Final = 200
# Printable ASCII other than the space.
_MODEL_PATTERN: Final = re.compile(r"^[!-~]+$")

# Plain decimal digits: no sign, no leading zero, no `0x`, `_` or `:`.
_PLAIN_WHOLE_NUMBER: Final = re.compile(r"^[1-9][0-9]*$")

_MATTER: Final = "matter"
_NONE: Final = "none"
_CHAT: Final = "chat"

AgentFileMode = Literal["store", "repo"]

_DELIMITER: Final = "---"
_BOM: Final = "\ufeff"
_INT_TAG: Final = "tag:yaml.org,2002:int"
_MERGE_TAG: Final = "tag:yaml.org,2002:merge"

_KNOWN_FIELDS: Final = frozenset(
    {
        "schema",
        "name",
        "title",
        "description",
        "metadata",
        "model",
        "skills",
        "knowledge",
        "tools",
        "limits",
        "version",
    }
)

_NOT_SUPPORTED: Final = "is not supported in this version of LQ.AI"

# Names refused with the word "reserved", with any extra pointer.
_RESERVED_FIELDS: Final[dict[str, str]] = {
    "history": "",
    "workspace": "",
    "subagents": "",
    "use_as": "",
    "memory": (
        " For notes the agent keeps, see `workspace`; for earlier messages of "
        "this chat, see `history`."
    ),
    "permissions": "",
}
_RESERVED_LIMITS: Final = frozenset(
    {"max_subagents", "max_subagent_tool_calls", "max_result_chars"}
)

_QUOTE_HINT: Final = (
    " YAML reads words such as yes, no, on and off, numbers and dates as other "
    'values. Put the value in quotes, for example `{key}: "{example}"`.'
)


# --- Results -----------------------------------------------------------------


@dataclass(frozen=True)
class AgentFileNote:
    """A problem that refuses the file, or a notice about a file that saves:
    the field it concerns and what to know about it, in plain words."""

    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


class ListedItem(BaseModel):
    """One entry of ``skills`` or ``knowledge``: a name, and whether the turn
    may run without it."""

    model_config = ConfigDict(frozen=True)

    name: str
    optional: bool = False


class AgentLimits(BaseModel):
    """``limits``. The rounds limit may only lower the operator's number,
    which happens at send, not here."""

    model_config = ConfigDict(frozen=True)

    max_rounds: int | None = None


class AgentFile(BaseModel):
    """A parsed, valid agent file."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: Literal[1] = Field(alias="schema")
    name: str
    title: str
    description: str
    model: str | None = None
    skills: tuple[ListedItem, ...] = ()
    knowledge: Literal["none"] | tuple[ListedItem, ...]
    tools: Literal["chat"]
    limits: AgentLimits = AgentLimits()
    metadata: dict[str, str] = Field(default_factory=dict)
    version: int | None = None
    """Set only in ``repo`` mode; the store assigns versions itself."""
    instructions: str
    """The body, exactly as written. May be empty."""
    text: str
    """The saved text: line endings normalised, and in ``store`` mode
    without the ``version`` field."""
    fingerprint: str
    """SHA-256 of :attr:`text`, as 64 lowercase hex characters."""

    @property
    def has_instructions(self) -> bool:
        """False when the body is empty or only white space: the system
        prompt then has no agent section."""
        return bool(self.instructions.strip())


@dataclass(frozen=True)
class AgentFileCheck:
    """The outcome of :func:`validate_agent_file`."""

    agent: AgentFile | None
    problems: tuple[AgentFileNote, ...] = ()
    notices: tuple[AgentFileNote, ...] = ()

    @property
    def ok(self) -> bool:
        return self.agent is not None


class AgentFileInvalid(ValidationError):
    """An agent file was refused. ``details["problems"]`` lists each one."""

    def __init__(self, problems: tuple[AgentFileNote, ...]) -> None:
        count = len(problems)
        noun = "problem" if count == 1 else "problems"
        super().__init__(
            f"The agent file has {count} {noun}.",
            details={"problems": [p.as_dict() for p in problems]},
        )
        self.problems = problems


class _YamlRefused(ValidationError):
    """Front matter that cannot be read. Caught inside this module."""


# --- Public functions --------------------------------------------------------


def normalise_line_endings(text: str) -> str:
    """Turn ``\\r\\n`` and lone ``\\r`` into ``\\n``."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def fingerprint_agent_text(text: str) -> str:
    """SHA-256 of ``text`` with line endings normalised, as lowercase hex.

    The same text gives the same fingerprint on every platform, whether it
    was checked out with ``\\n`` or ``\\r\\n`` line endings.
    """
    return hashlib.sha256(normalise_line_endings(text).encode("utf-8")).hexdigest()


def validate_agent_file(text: str, *, mode: AgentFileMode) -> AgentFileCheck:
    """Read an agent file and return the parsed file, or every problem found.

    Never raises for a bad file; the problems are in the result.
    """
    return _Validator(text, mode).run()


def parse_agent_file(text: str, *, mode: AgentFileMode) -> AgentFile:
    """Read an agent file; raise :class:`AgentFileInvalid` if it is refused."""
    check = validate_agent_file(text, mode=mode)
    if check.agent is None:
        raise AgentFileInvalid(check.problems)
    return check.agent


# --- Describing values -------------------------------------------------------


def _shown(text: str) -> str:
    """A value from the file, short, between backticks."""
    if len(text) > 60:
        text = text[:57] + "..."
    return f"`{text}`"


def _read_as(value: object) -> str:
    """What YAML made of a value, in words: "YAML read it as a number"."""
    if value is None:
        return "it is empty"
    if isinstance(value, bool):
        return "YAML read it as true or false"
    if isinstance(value, (int, float)):
        return "YAML read it as a number"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return "YAML read it as a date"
    if isinstance(value, str):
        return f"it is {_shown(value)}"
    if isinstance(value, list):
        return "it is a list"
    if isinstance(value, dict):
        return "it is a set of fields"
    return "it is a value that is not text"


def _written(node: yaml.Node | None, value: object) -> str:
    """How a number was written in the file, for a message."""
    if isinstance(node, yaml.ScalarNode):
        if node.style in ("'", '"'):
            return "it is in quotes; write the number without quotes"
        if node.tag != _INT_TAG and _PLAIN_WHOLE_NUMBER.fullmatch(node.value):
            return "it is marked as text with a tag such as `!!str`; remove the tag"
        if node.value:
            return f"it is written {_shown(node.value)}"
    return _read_as(value)


def _quote_hint(value: object, key: str, example: str) -> str:
    if isinstance(value, (bool, int, float, datetime.date)):
        return _QUOTE_HINT.format(key=key, example=example)
    return ""


def _key_words(key: object) -> str:
    """A field name from the file, for a message. Never a Python repr."""
    if isinstance(key, str):
        return _shown(key)
    if isinstance(key, bool):
        return "a field name that YAML read as true or false"
    if isinstance(key, (int, float)):
        return f"a field name that YAML read as the number {key}"
    if key is None:
        return "a field name that YAML read as empty (`null`, `~` or nothing before the colon)"
    return "a field name that is not text"


def _unknown_field_message(key: str) -> str:
    """Refuse an unknown field, suggesting the nearest real one."""
    near = difflib.get_close_matches(key, sorted(_KNOWN_FIELDS), n=1, cutoff=0.75)
    if near:
        return f"`{key}` is not a field of an agent file. Did you mean `{near[0]}`?"
    fields = ", ".join(f"`{name}`" for name in sorted(_KNOWN_FIELDS))
    return f"`{key}` is not a field of an agent file. The fields are {fields}."


def _hiding_character_name(code: int) -> str | None:
    """Name a character that hides or reorders text on screen, or None.

    Only these are refused. Joiners and marks that real scripts need (the
    zero-width joiner and non-joiner, the left-to-right and right-to-left
    marks, the soft hyphen) stay legal.
    """
    if 0x202A <= code <= 0x202E:
        return "a text-direction override"
    if 0x2066 <= code <= 0x2069:
        return "a text-direction isolate"
    if code == 0x200B:
        return "a zero-width space"
    if code == 0xFEFF:
        return "a zero-width no-break space"
    if code == 0x2060:
        return "a word joiner"
    if 0x2061 <= code <= 0x2064:
        return "an invisible maths operator"
    if 0xE0000 <= code <= 0xE007F:
        return "an invisible tag character"
    return None


_RAW_LINE_BREAKS: Final[dict[str, str]] = {
    "\u2028": "a line separator",
    "\u2029": "a paragraph separator",
}


def _raw_line_break(line: str) -> str | None:
    """Describe a Unicode line break written raw in the front matter, or None.

    YAML reads U+2028 and U+2029 as line breaks, but the file is split into
    lines on ``\\n`` only. Written raw, they would put YAML's line numbers
    out of step with the file's, and the ``version`` field would be cut from
    the wrong lines. Inside a double-quoted value the escapes ``\\u2028``
    and ``\\u2029`` still work.
    """
    for char in line:
        name = _RAW_LINE_BREAKS.get(char)
        if name:
            return (
                f"{name} (U+{ord(char):04X}), which YAML reads as a line break. "
                "Replace it with an ordinary line break or a space"
            )
    return None


_CONTROL_NAMES: Final[dict[int, str]] = {
    0x00: "a null character",
    0x0B: "a vertical tab",
    0x0C: "a form feed (page break)",
}


def _bad_character(text: str, *, allow_newline: bool) -> str | None:
    """Describe the first character not allowed in ``text``, or None.

    Control characters are refused except tab and, where allowed, newline.
    Characters that hide or reorder text are refused everywhere, the body
    included, so the file shows every instruction the model reads.
    """
    for char in text:
        if char == "\t" or (char == "\n" and allow_newline):
            continue
        code = ord(char)
        hiding = _hiding_character_name(code)
        if hiding and "direction" in hiding:
            return (
                f"{hiding} (U+{code:04X}). It changes the order in which text is shown, "
                "so the screen does not match what the model reads. Delete it"
            )
        if hiding:
            return (
                f"{hiding} (U+{code:04X}). It is not shown on screen, but the model "
                "reads it. Delete it"
            )
        if unicodedata.category(char) == "Cc":
            name = _CONTROL_NAMES.get(code, "a control character")
            return f"{name} (U+{code:04X}), which cannot be saved. Delete it"
    return None


# --- Front matter YAML -------------------------------------------------------


class _Loader(yaml.SafeLoader):
    """The safe loader, refusing anchors and aliases as it composes."""

    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        event = self.peek_event()
        if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
            raise _YamlRefused(
                "Anchors and aliases (`&` and `*`) are not allowed in an agent file. "
                "Write each value out."
            )
        return super().compose_node(parent, index)


def _yaml_problem(exc: yaml.YAMLError) -> str:
    """Turn a PyYAML error into a sentence a person can act on."""
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or ""
    # Front matter line n is line n + 2 of the file.
    where = f"Line {mark.line + 2}" if mark else "The front matter"
    if "mapping values are not allowed" in problem:
        return (
            f"{where} has a colon (`:`) inside a value, which YAML reads as the start "
            "of a new field. Put the whole value in quotes, for example "
            '`description: "Use for: NDAs"`.'
        )
    if "'\\t'" in problem:
        return f"{where} uses a tab. Indent the front matter with spaces, not tabs."
    if "unhashable key" in problem:
        return (
            f"{where} has a field name written as a list or a set of fields, with "
            "`?` or brackets. A field name is one word: write it as `name: value`, "
            "for example `title: NDA Comparer`."
        )
    if "constructor for the tag" in problem:
        return (
            f"{where} uses a YAML tag (a word starting with `!`). Remove it, or put "
            "the value in quotes."
        )
    return (
        f"{where} cannot be read as YAML. Check the indentation and that every "
        "bracket and quote is closed. Put any value that contains `:`, `#`, `[`, `{` "
        "or a quote mark inside quotes."
    )


def _load_front_matter(front: str) -> tuple[yaml.MappingNode | None, object]:
    """Parse the front matter once, refusing what the format does not allow.

    Returns the composed root node (for line positions and raw scalars) and
    the constructed data.
    """
    loader = _Loader(front)
    try:
        root = loader.get_single_node()
        if root is None:
            return None, None
        _check_mappings(root)
        data = loader.construct_document(root)
    except _YamlRefused:
        raise
    except yaml.YAMLError as exc:
        raise _YamlRefused(_yaml_problem(exc)) from None
    except (RecursionError, ValueError, TypeError):
        raise _YamlRefused(
            "The front matter cannot be read as YAML. Check the indentation and the values."
        ) from None
    finally:
        loader.dispose()
    return (root if isinstance(root, yaml.MappingNode) else None), data


def _check_mappings(node: yaml.Node) -> None:
    """Refuse duplicate keys and merge keys anywhere in the tree."""
    stack: list[yaml.Node] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, yaml.MappingNode):
            seen: set[str] = set()
            for key_node, value_node in current.value:
                if isinstance(key_node, yaml.ScalarNode):
                    if key_node.tag == _MERGE_TAG:
                        raise _YamlRefused("Merge keys (`<<`) are not allowed in an agent file.")
                    if key_node.value in seen:
                        line = key_node.start_mark.line + 2
                        raise _YamlRefused(
                            f"`{key_node.value}` appears twice (again at line {line}). Keep one."
                        )
                    seen.add(key_node.value)
                stack.append(value_node)
        elif isinstance(current, yaml.SequenceNode):
            stack.extend(current.value)


def _value_node(mapping: yaml.Node | None, key: str) -> yaml.Node | None:
    if not isinstance(mapping, yaml.MappingNode):
        return None
    for key_node, value_node in mapping.value:
        if isinstance(key_node, yaml.ScalarNode) and key_node.value == key:
            return value_node
    return None


def _is_plain_whole_number(node: yaml.Node | None) -> bool:
    """True when YAML read an integer from plain decimal digits."""
    return (
        isinstance(node, yaml.ScalarNode)
        and node.tag == _INT_TAG
        and bool(_PLAIN_WHOLE_NUMBER.fullmatch(node.value))
    )


# --- The validator -----------------------------------------------------------


class _Validator:
    def __init__(self, text: str, mode: AgentFileMode) -> None:
        self.raw = text
        self.mode = mode
        self.problems: list[AgentFileNote] = []
        self.notices: list[AgentFileNote] = []
        self.root: yaml.MappingNode | None = None

    def problem(self, field_name: str, message: str) -> None:
        self.problems.append(AgentFileNote(field_name, message))

    def fail(self) -> AgentFileCheck:
        return AgentFileCheck(agent=None, problems=tuple(self.problems))

    # The steps run in order; a step that cannot go on returns a refusal.
    def run(self) -> AgentFileCheck:
        if not isinstance(self.raw, str):
            self.problem("file", "The file must be text.")
            return self.fail()
        size = len(self.raw.encode("utf-8", errors="surrogatepass"))
        if size > MAX_FILE_BYTES:
            self.problem(
                "file",
                f"The file is {size} bytes; an agent file may be at most {MAX_FILE_BYTES} bytes.",
            )
            return self.fail()
        try:
            self.raw.encode("utf-8")
        except UnicodeEncodeError:
            self.problem("file", "The file contains characters that are not valid text.")
            return self.fail()
        if self.raw.startswith(_BOM):
            self.problem(
                "file",
                "The file starts with an invisible byte-order mark, which some editors "
                "add. Remove it: the first line must be `---`.",
            )
            return self.fail()

        text = normalise_line_endings(self.raw)
        lines = text.split("\n")
        if lines[0].rstrip(" \t") != _DELIMITER:
            self.problem(
                "file",
                "The first line must be `---`, to open the front matter. "
                "An agent file is YAML front matter between two `---` lines, then the "
                "instructions.",
            )
            return self.fail()
        close = next(
            (i for i in range(1, len(lines)) if lines[i].rstrip(" \t") == _DELIMITER),
            None,
        )
        if close is None:
            self.problem(
                "file", "The front matter is not closed: add a line `---` after the last field."
            )
            return self.fail()

        front = "\n".join(lines[1:close])
        body = "\n".join(lines[close + 1 :])
        self._check_sizes_and_characters(lines, close, front, body)
        if self.problems:
            return self.fail()

        try:
            root, data = _load_front_matter(front)
        except _YamlRefused as exc:
            self.problem("front matter", exc.message)
            return self.fail()
        self.root = root

        if data is None:
            data = {}
        if not isinstance(data, dict):
            self.problem(
                "front matter",
                "The front matter must be a set of fields such as `name: my-agent`, "
                f"but {_read_as(data)}.",
            )
            return self.fail()

        self._check_parsed_text(data, "")
        if self.problems:
            return self.fail()

        saved_text = text
        version: int | None = None
        if "version" in data:
            if self.mode == "store":
                saved_text = self._without_version(lines, text)
            else:
                version = self._repo_version(data["version"])
        elif self.mode == "repo":
            self.problem(
                "version",
                "`version` is missing. A file kept in the repository states its version "
                "as a whole number, for example `version: 1`.",
            )

        agent_fields = self._check_fields(data)
        if self.problems:
            return self.fail()

        agent = AgentFile.model_validate(
            {
                **agent_fields,
                "version": version,
                "instructions": body,
                "text": saved_text,
                "fingerprint": fingerprint_agent_text(saved_text),
            }
        )
        return AgentFileCheck(agent=agent, notices=tuple(self.notices))

    # --- sizes and characters --------------------------------------------

    def _check_sizes_and_characters(
        self, lines: list[str], close: int, front: str, body: str
    ) -> None:
        front_size = len(front.encode("utf-8"))
        if front_size > MAX_FRONT_MATTER_BYTES:
            self.problem(
                "front matter",
                f"The front matter is {front_size} bytes; it may be at most "
                f"{MAX_FRONT_MATTER_BYTES} bytes.",
            )
        body_size = len(body.encode("utf-8"))
        if body_size > MAX_BODY_BYTES:
            self.problem(
                "body",
                f"The instructions are {body_size} bytes; they may be at most "
                f"{MAX_BODY_BYTES} bytes (32 KB).",
            )
        # Raw text: comments and the body included, so nothing unsaveable is
        # kept in the saved text.
        for number, line in enumerate(lines, start=1):
            in_front = number - 1 < close
            bad = _bad_character(line, allow_newline=False)
            if in_front and not bad:
                bad = _raw_line_break(line)
            if bad:
                where = "front matter" if in_front else "body"
                self.problem(where, f"Line {number} contains {bad}.")

    def _check_parsed_text(self, value: object, where: str) -> None:
        """Values can carry characters through YAML escapes such as ``\\0``."""
        if isinstance(value, str):
            bad = _bad_character(value, allow_newline=True)
            if bad:
                self.problem(where or "front matter", f"The value contains {bad}.")
        elif isinstance(value, dict):
            for key, item in value.items():
                name = key if isinstance(key, str) else "front matter"
                if isinstance(key, str):
                    self._check_parsed_text(key, where or "front matter")
                self._check_parsed_text(item, f"{where}.{name}" if where else name)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                self._check_parsed_text(item, f"{where}[{i}]")

    # --- version ---------------------------------------------------------

    def _without_version(self, lines: list[str], text: str) -> str:
        """The saved text without the ``version`` field (annex A3 point 17)."""
        root = self.root
        if root is None or root.flow_style:
            self.problem(
                "version",
                "This file writes its fields on one line, between `{` and `}`, so "
                "`version` cannot be left out of it here. The store numbers versions "
                "itself: delete `version`, or write each field on its own line.",
            )
            return text
        # In a block mapping each key starts on a line of its own, so the
        # field's lines run from its key to the end of its value. Front
        # matter line n is text line n + 1 (line 0 is `---`).
        for key_node, value_node in root.value:
            if isinstance(key_node, yaml.ScalarNode) and key_node.value == "version":
                start = key_node.start_mark.line + 1
                end_mark = value_node.end_mark
                end = max(start, end_mark.line + 1 if end_mark.column > 0 else end_mark.line)
                self.notices.append(
                    AgentFileNote(
                        "version",
                        "`version` is ignored: the store numbers each saved version. "
                        "It is left out of the saved text.",
                    )
                )
                return "\n".join(lines[:start] + lines[end + 1 :])
        return text

    def _repo_version(self, value: object) -> int | None:
        node = _value_node(self.root, "version")
        if not _is_plain_whole_number(node) or not isinstance(value, int):
            self.problem(
                "version",
                f"`version` must be a whole number, 1 or more, in plain digits, such as "
                f"`version: 1`, but {_written(node, value)}.",
            )
            return None
        return value

    # --- fields ----------------------------------------------------------

    def _check_fields(self, data: dict[Any, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in data:
            if not isinstance(key, str):
                self.problem(
                    "front matter",
                    f"Each field name must be text, but the file has {_key_words(key)}.",
                )
            elif key in _RESERVED_FIELDS:
                self.problem(
                    key, f"`{key}` is reserved: it {_NOT_SUPPORTED}.{_RESERVED_FIELDS[key]}"
                )
            elif key == "author":
                self.problem(
                    "author",
                    "`author` is not a field of an agent file. To say who wrote it, put it "
                    "under `metadata`, for example `metadata: {author: Jane Tan}`.",
                )
            elif key not in _KNOWN_FIELDS:
                self.problem(key, _unknown_field_message(key))

        self._schema(data, out)
        self._name(data, out)
        self._text_field(data, out, "description", required=True)
        self._text_field(data, out, "title", required=False)
        if "title" not in out and "name" in out:
            out["title"] = out["name"]
        self._metadata(data, out)
        self._model(data, out)
        self._skills(data, out)
        self._knowledge(data, out)
        self._tools(data, out)
        self._limits(data, out)
        return out

    def _schema(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "schema" not in data:
            self.problem("schema", "`schema` is required. Add the line `schema: 1`.")
            return
        node = _value_node(self.root, "schema")
        if not _is_plain_whole_number(node) or data["schema"] != 1:
            self.problem(
                "schema",
                "`schema` must be the number 1, written `schema: 1`, "
                f"but {_written(node, data['schema'])}. This version of LQ.AI reads "
                "schema 1 only.",
            )
            return
        out["schema"] = 1

    def _name(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "name" not in data:
            self.problem("name", "`name` is required, for example `name: nda-comparer`.")
            return
        value = data["name"]
        if not isinstance(value, str):
            self.problem(
                "name",
                f"`name` must be text, but {_read_as(value)}."
                + _quote_hint(value, "name", "my-agent"),
            )
            return
        if len(value) > NAME_MAX_LENGTH:
            self.problem(
                "name",
                f"`name` is {len(value)} characters; it may be at most {NAME_MAX_LENGTH}.",
            )
            return
        if not _NAME_PATTERN.fullmatch(value):
            self.problem(
                "name",
                f"`name` is {_shown(value)}. Use lowercase letters, digits and hyphens, "
                "starting with a letter, for example `nda-comparer`.",
            )
            return
        out["name"] = value

    def _text_field(
        self, data: dict[Any, Any], out: dict[str, Any], key: str, *, required: bool
    ) -> None:
        if key not in data:
            if required:
                self.problem(key, f"`{key}` is required. Say when to use this agent.")
            return
        value = data[key]
        if not isinstance(value, str):
            self.problem(
                key,
                f"`{key}` must be text, but {_read_as(value)}." + _quote_hint(value, key, "..."),
            )
            return
        if not value.strip():
            self.problem(key, f"`{key}` is empty.")
            return
        if key == "title" and any(c in value.strip() for c in "\n\u2028\u2029"):
            self.problem("title", "`title` must be one line.")
            return
        out[key] = value

    def _metadata(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "metadata" not in data:
            return
        value = data["metadata"]
        if not isinstance(value, dict):
            self.problem(
                "metadata",
                f"`metadata` must be a set of fields, each one text, but {_read_as(value)}.",
            )
            return
        result: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                self.problem(
                    "metadata",
                    f"Each field name under `metadata` must be text, but the file has "
                    f"{_key_words(key)}.",
                )
                continue
            if not isinstance(item, str):
                self.problem(
                    f"metadata.{key}",
                    f"`metadata.{key}` must be text, but {_read_as(item)}."
                    + _quote_hint(item, key, "..."),
                )
                continue
            result[key] = item
        out["metadata"] = result

    def _model(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "model" not in data:
            return
        value = data["model"]
        if value is None:
            self.problem(
                "model",
                "`model` is empty. Name a model, or delete the line to use the chat's model.",
            )
            return
        if not isinstance(value, str):
            self.problem(
                "model",
                f"`model` must be text, but {_read_as(value)}."
                + _quote_hint(value, "model", "local"),
            )
            return
        if (
            len(value) > MODEL_MAX_LENGTH
            or not _MODEL_PATTERN.fullmatch(value)
            or value.startswith("/")
            or value.endswith("/")
            or "//" in value
        ):
            self.problem(
                "model",
                f"`model` is {_shown(value)}. Use a model alias such as `local`, or "
                f"`provider/model`: plain letters, digits and punctuation, no spaces, at "
                f"most {MODEL_MAX_LENGTH} characters.",
            )
            return
        # Annex A1: contributed agent files name aliases only. That rule belongs
        # to the check for contributed agents when it is built; it is not
        # applied in either mode here.
        out["model"] = value

    def _skills(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "skills" not in data:
            return
        value = data["skills"]
        if not isinstance(value, list):
            self.problem(
                "skills",
                f"`skills` must be a list, for example `skills: [nda-snapshot]`, "
                f"but {_read_as(value)}.",
            )
            return
        if len(value) > MAX_SKILLS:
            self.problem(
                "skills",
                f"`skills` lists {len(value)} skills; at most {MAX_SKILLS} can be used on a turn.",
            )
            return
        refs: list[ListedItem] = []
        seen: set[str] = set()
        ok = True
        for i, item in enumerate(value):
            where = f"skills[{i}]"
            ref = self._skill_item(where, item)
            if ref is None:
                ok = False
            elif ref.name in seen:
                self.problem(where, f"`{ref.name}` is listed twice.")
                ok = False
            else:
                seen.add(ref.name)
                refs.append(ref)
        if ok:
            out["skills"] = tuple(refs)

    def _skill_item(self, where: str, item: object) -> ListedItem | None:
        optional = False
        if isinstance(item, dict):
            if "always" in item:
                self.problem(
                    f"{where}.always",
                    f"`always` is reserved: it {_NOT_SUPPORTED}. The instructions can say "
                    "which skill to load first.",
                )
                return None
            for key in item:
                if key not in ("name", "optional"):
                    self.problem(
                        where,
                        f"A skill entry has {_key_words(key)}, which is not one of its "
                        "fields. Use `name` and, if you want, `optional`.",
                    )
                    return None
            if "name" not in item:
                self.problem(where, "A skill entry needs a `name`.")
                return None
            optional_value = item.get("optional", False)
            if not isinstance(optional_value, bool):
                self.problem(
                    f"{where}.optional",
                    f"`optional` must be `true` or `false`, but {_read_as(optional_value)}.",
                )
                return None
            optional = optional_value
            item = item["name"]
        if not isinstance(item, str):
            self.problem(
                where,
                "Each skill is a skill's name, or `{name: ..., optional: true}`, "
                f"but {_read_as(item)}." + _quote_hint(item, "name", "..."),
            )
            return None
        if not _SKILL_SLUG_PATTERN.fullmatch(item):
            self.problem(
                where,
                f"{_shown(item)} is not a skill name. Skill names use lowercase letters, "
                "digits and hyphens, for example `nda-snapshot`.",
            )
            return None
        return ListedItem(name=item, optional=optional)

    def _knowledge(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "knowledge" not in data:
            out["knowledge"] = (ListedItem(name=_MATTER),)
            return
        value = data["knowledge"]
        if value == _NONE:
            out["knowledge"] = _NONE
            return
        if value is None or value == []:
            self.problem(
                "knowledge",
                "`knowledge` is empty. Write `knowledge: none` to search nothing, or "
                "`knowledge: [matter]` to search the matter's knowledge.",
            )
            return
        if not isinstance(value, list):
            self.problem(
                "knowledge",
                f"`knowledge` must be `none` or a list such as `[matter]`, but {_read_as(value)}.",
            )
            return
        refs: list[ListedItem] = []
        ok = True
        for i, item in enumerate(value):
            where = f"knowledge[{i}]"
            if item == _NONE:
                self.problem(where, "`none` stands alone: write `knowledge: none`, not a list.")
                ok = False
            elif item == _MATTER:
                if refs:
                    self.problem(where, "`matter` is listed twice.")
                    ok = False
                else:
                    refs.append(ListedItem(name=_MATTER))
            elif isinstance(item, dict) and item.get("name") == _MATTER:
                self.problem(
                    where,
                    "`matter` cannot be optional, and needs no fields: write `matter`.",
                )
                ok = False
            elif isinstance(item, (str, dict)):
                # Marking the item `optional` does not let it save (annex A5(a),
                # refused until ruled otherwise).
                self.problem(
                    where,
                    f"Naming a knowledge base {_NOT_SUPPORTED}. Use `matter`, or `none`.",
                )
                ok = False
            else:
                self.problem(
                    where,
                    f"Each `knowledge` item is `matter`, but {_read_as(item)}.",
                )
                ok = False
        if ok:
            out["knowledge"] = tuple(refs)

    def _tools(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "tools" not in data:
            self.problem(
                "tools",
                "`tools` is required. Write `tools: chat` for the tools ordinary chat offers here.",
            )
            return
        value = data["tools"]
        if value == _CHAT:
            out["tools"] = _CHAT
        elif value == _NONE:
            self.problem("tools", f"`tools: none` {_NOT_SUPPORTED}. Use `tools: chat`.")
        elif isinstance(value, list) and any(item in (_CHAT, _NONE) for item in value):
            self.problem(
                "tools",
                "`chat` and `none` stand alone and cannot be part of a list. Write `tools: chat`.",
            )
        elif isinstance(value, list):
            self.problem("tools", f"A list of tools {_NOT_SUPPORTED}. Use `tools: chat`.")
        else:
            self.problem(
                "tools",
                f"`tools` must be `chat`, but {_read_as(value)}. Write `tools: chat`.",
            )

    def _limits(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "limits" not in data:
            return
        value = data["limits"]
        if not isinstance(value, dict):
            self.problem(
                "limits",
                f"`limits` must be a set of fields, for example "
                f"`limits: {{{ROUNDS_LIMIT_FIELD}: 6}}`, but {_read_as(value)}.",
            )
            return
        ok = True
        for key in value:
            if not isinstance(key, str):
                self.problem(
                    "limits",
                    f"`limits` has {_key_words(key)}. The one limit is `{ROUNDS_LIMIT_FIELD}`.",
                )
                ok = False
            elif key in _RESERVED_LIMITS:
                self.problem(f"limits.{key}", f"`limits.{key}` is reserved: it {_NOT_SUPPORTED}.")
                ok = False
            elif key != ROUNDS_LIMIT_FIELD:
                self.problem(
                    f"limits.{key}",
                    f"`{key}` is not a limit. The one limit is `{ROUNDS_LIMIT_FIELD}`.",
                )
                ok = False
        rounds: int | None = None
        if ROUNDS_LIMIT_FIELD in value:
            limit = value[ROUNDS_LIMIT_FIELD]
            node = _value_node(_value_node(self.root, "limits"), ROUNDS_LIMIT_FIELD)
            if not _is_plain_whole_number(node) or not isinstance(limit, int):
                self.problem(
                    f"limits.{ROUNDS_LIMIT_FIELD}",
                    f"`{ROUNDS_LIMIT_FIELD}` is the most rounds a turn may take: a whole "
                    f"number, 1 or more, in plain digits, such as `{ROUNDS_LIMIT_FIELD}: 6`, "
                    f"but {_written(node, limit)}.",
                )
                ok = False
            else:
                # No upper bound at save (annex A3 point 11: clamped at send).
                rounds = limit
        if ok:
            out["limits"] = AgentLimits(max_rounds=rounds)
