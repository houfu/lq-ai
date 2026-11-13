"""Agent file format, version 1: parse, validate and fingerprint.

An agent file is Markdown with YAML front matter, the same shape as a
``SKILL.md``. The front matter holds the fields below; the body is the
agent's instructions. This module reads the file alone. It does not look
anything up: whether a named skill exists, whether the operator allows a
model, or whether a matter permits a tool is the check's job, not this one.

Two modes:

* ``store`` is for a file a person pastes or uploads. A ``version`` line is
  ignored with a notice and removed from the saved text, because the store
  numbers versions itself.
* ``repo`` is for files shipped in the repository, which have no store.
  They may carry ``version``, and their ``model`` must be an alias.

Every problem names a field and says what is wrong in plain words. All
problems are collected, not only the first.

The fingerprint is the SHA-256 of the saved text with line endings
normalised to ``\\n``. Keys are not reordered and comments are kept, so a
changed comment is a changed fingerprint.

YAML is read with PyYAML's safe loader, as the skill loader does. Three
things the safe loader allows are refused here: duplicate keys (the safe
loader keeps the last one silently), anchors and aliases, and merge keys.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.errors import ValidationError

# --- Constants ---------------------------------------------------------------

SCHEMA_VERSION: Final = 1

NAME_MAX_LENGTH: Final = 64
NAME_PATTERN: Final = re.compile(r"^[a-z][a-z0-9-]*$")

# Skill slugs as the user-skill store accepts them (``app/api/user_skills.py``).
SKILL_SLUG_PATTERN: Final = re.compile(r"^[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?$")

# Listed, hand-attached and kept skills together are at most 16 on a turn,
# so a file that lists more could never run.
MAX_SKILLS: Final = 16

# The file's name for its rounds limit. The name is not ruled yet; every
# use reads it from here.
ROUNDS_LIMIT_FIELD: Final = "max_tool_calls"

MAX_BODY_BYTES: Final = 32 * 1024
MAX_FRONT_MATTER_BYTES: Final = 16 * 1024
# Checked before anything else, so no larger text is split or parsed.
MAX_FILE_BYTES: Final = MAX_BODY_BYTES + MAX_FRONT_MATTER_BYTES + 1024

MODEL_MAX_LENGTH: Final = 200

KNOWLEDGE_MATTER: Final = "matter"
KNOWLEDGE_NONE: Final = "none"
TOOLS_CHAT: Final = "chat"
TOOLS_NONE: Final = "none"

AgentFileMode = Literal["store", "repo"]

_DELIMITER: Final = "---"
_BOM: Final = "﻿"

# Fields a version 1 file may carry.
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

_SUBAGENTS_WAIT = "It waits for the decision on sub-agents."

# Names refused with the word "reserved" until their own decisions.
_RESERVED_FIELDS: Final[dict[str, str]] = {
    "history": "It waits for the history tool.",
    "workspace": "It waits for the agent's own workspace (Stage 4).",
    "subagents": _SUBAGENTS_WAIT,
    "use_as": _SUBAGENTS_WAIT,
    "memory": (
        "For notes the agent keeps, see `workspace`; for earlier messages of "
        "this chat, see `history`."
    ),
    "permissions": "There is no plan for it.",
}

_RESERVED_LIMITS: Final[dict[str, str]] = {
    "max_subagents": _SUBAGENTS_WAIT,
    "max_subagent_tool_calls": _SUBAGENTS_WAIT,
    "max_result_chars": _SUBAGENTS_WAIT,
}

_NOT_YET = "is not supported yet in this version of LQ.AI. It is planned for"


# --- Results -----------------------------------------------------------------


@dataclass(frozen=True)
class AgentFileProblem:
    """One reason a file is refused: the field, and what is wrong with it."""

    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass(frozen=True)
class AgentFileNotice:
    """Something the validator changed or ignored. The file is still saved."""

    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


class SkillRef(BaseModel):
    """One entry of ``skills``: a skill the model may load."""

    model_config = ConfigDict(frozen=True)

    name: str
    optional: bool = False


class KnowledgeRef(BaseModel):
    """One entry of ``knowledge``. Only ``matter`` is valid in version 1 today."""

    model_config = ConfigDict(frozen=True)

    name: str
    optional: bool = False


class AgentLimits(BaseModel):
    """``limits``. ``max_tool_calls`` is a limit on rounds; it may only lower
    the operator's number, which happens at send, not here."""

    model_config = ConfigDict(frozen=True)

    max_tool_calls: int | None = None


class AgentFile(BaseModel):
    """A parsed, valid agent file."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: Literal[1] = Field(alias="schema")
    name: str
    title: str
    description: str
    model: str | None = None
    skills: tuple[SkillRef, ...] = ()
    knowledge: Literal["none"] | tuple[KnowledgeRef, ...]
    tools: Literal["chat"]
    limits: AgentLimits = AgentLimits()
    metadata: dict[str, str] = Field(default_factory=dict)
    version: int | None = None
    """Set only in ``repo`` mode; the store assigns versions itself."""
    instructions: str
    """The body, exactly as written. May be empty."""
    text: str
    """The saved text: line endings normalised, and in ``store`` mode
    without the ``version`` line."""
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
    problems: tuple[AgentFileProblem, ...] = ()
    notices: tuple[AgentFileNotice, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return self.agent is not None


class AgentFileInvalid(ValidationError):
    """An agent file was refused. ``details["problems"]`` lists each one."""

    def __init__(self, problems: tuple[AgentFileProblem, ...]) -> None:
        count = len(problems)
        noun = "problem" if count == 1 else "problems"
        super().__init__(
            f"The agent file has {count} {noun}.",
            details={"problems": [p.as_dict() for p in problems]},
        )
        self.problems = problems


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


def validate_agent_file(text: str, *, mode: AgentFileMode = "store") -> AgentFileCheck:
    """Read an agent file and return the parsed file, or every problem found.

    Never raises for a bad file; the problems are in the result.
    """
    return _Validator(text, mode).run()


def parse_agent_file(text: str, *, mode: AgentFileMode = "store") -> AgentFile:
    """Read an agent file; raise :class:`AgentFileInvalid` if it is refused."""
    check = validate_agent_file(text, mode=mode)
    if check.agent is None:
        raise AgentFileInvalid(check.problems)
    return check.agent


# --- Implementation ----------------------------------------------------------


def _code(value: object) -> str:
    """Show a value from the file in a message, short."""
    shown = repr(value) if not isinstance(value, str) else value
    if len(shown) > 60:
        shown = shown[:57] + "..."
    return f"`{shown}`"


def _type_word(value: object) -> str:
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a set of fields"
    return "a date or other value"


class _YamlRefused(Exception):
    """Front matter YAML that the format refuses before it is constructed."""


class _Validator:
    def __init__(self, text: str, mode: AgentFileMode) -> None:
        self.raw = text
        self.mode = mode
        self.problems: list[AgentFileProblem] = []
        self.notices: list[AgentFileNotice] = []

    def problem(self, field_name: str, message: str) -> None:
        self.problems.append(AgentFileProblem(field_name, message))

    def fail(self) -> AgentFileCheck:
        return AgentFileCheck(agent=None, problems=tuple(self.problems), notices=())

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
                "The file starts with an invisible byte-order mark. Remove it: "
                "the first line must be `---`.",
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

        front_lines = lines[1:close]
        front = "\n".join(front_lines)
        body = "\n".join(lines[close + 1 :])

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
        if self.problems:
            return self.fail()

        try:
            root, data = _load_front_matter(front)
        except _YamlRefused as exc:
            self.problem("front matter", str(exc))
            return self.fail()

        if data is None:
            data = {}
        if not isinstance(data, dict):
            self.problem(
                "front matter",
                f"The front matter must be a set of fields such as `name: my-agent`; "
                f"it is {_type_word(data)}.",
            )
            return self.fail()

        saved_text = text
        version: int | None = None
        if "version" in data:
            if self.mode == "store":
                saved_text = self._strip_version(lines, root)
            else:
                version = self._repo_version(data["version"])

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
        return AgentFileCheck(agent=agent, problems=(), notices=tuple(self.notices))

    # --- version ---------------------------------------------------------

    def _strip_version(self, lines: list[str], root: yaml.MappingNode | None) -> str:
        """Remove the ``version`` field's lines from the saved text."""
        assert root is not None
        if root.flow_style:
            self.problem(
                "version",
                "`version` is set by the store, so it is removed from a pasted file. "
                "Write each field on its own line, or delete `version` yourself.",
            )
            return "\n".join(lines)
        # In a block mapping each key starts on a line of its own, so the
        # field's lines run from its key to the end of its value. Front
        # matter line n is text line n + 1 (line 0 is `---`).
        key_node, value_node = next(
            (k, v) for k, v in root.value if getattr(k, "value", None) == "version"
        )
        v_start = key_node.start_mark.line + 1
        end_mark = value_node.end_mark
        v_end = max(v_start, end_mark.line + 1 if end_mark.column > 0 else end_mark.line)
        self.notices.append(
            AgentFileNotice(
                "version",
                "`version` is ignored: the store numbers each saved version. "
                "The line was removed from the saved text.",
            )
        )
        return "\n".join(lines[:v_start] + lines[v_end + 1 :])

    def _repo_version(self, value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            self.problem(
                "version", f"`version` must be a whole number, 1 or more; it is {_code(value)}."
            )
            return None
        return value

    # --- fields ----------------------------------------------------------

    def _check_fields(self, data: dict[Any, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in data:
            if not isinstance(key, str):
                self.problem(
                    "front matter", f"Field names must be text; {_code(key)} is {_type_word(key)}."
                )
            elif key in _RESERVED_FIELDS:
                self.problem(
                    key, f"`{key}` is reserved and cannot be saved yet. {_RESERVED_FIELDS[key]}"
                )
            elif key == "author":
                self.problem(
                    "author",
                    "`author` is not a field of an agent file. To say who wrote it, put it "
                    "under `metadata`, for example `metadata: {author: Jane Tan}`.",
                )
            elif key not in _KNOWN_FIELDS:
                self.problem(key, f"`{key}` is not a field of an agent file (schema 1).")

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
        value = data["schema"]
        if isinstance(value, bool) or value != SCHEMA_VERSION or not isinstance(value, int):
            self.problem(
                "schema",
                f"`schema` must be the number 1; it is {_code(value)}. "
                "This version of LQ.AI reads schema 1 only.",
            )
            return
        out["schema"] = SCHEMA_VERSION

    def _name(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "name" not in data:
            self.problem("name", "`name` is required, for example `name: nda-comparer`.")
            return
        value = data["name"]
        if not isinstance(value, str):
            self.problem("name", f"`name` must be text; it is {_type_word(value)}.")
            return
        if len(value) > NAME_MAX_LENGTH:
            self.problem(
                "name",
                f"`name` is {len(value)} characters; it may be at most {NAME_MAX_LENGTH}.",
            )
            return
        if not NAME_PATTERN.fullmatch(value):
            self.problem(
                "name",
                f"`name` is {_code(value)}. Use lowercase letters, digits and hyphens, "
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
                f"`{key}` must be text; it is {_type_word(value)}. Put it in quotes if it "
                "looks like a number or a date.",
            )
            return
        if not value.strip():
            self.problem(key, f"`{key}` is empty.")
            return
        out[key] = value

    def _metadata(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "metadata" not in data:
            return
        value = data["metadata"]
        if not isinstance(value, dict):
            self.problem(
                "metadata",
                f"`metadata` must be a set of fields, each one text; it is {_type_word(value)}.",
            )
            return
        result: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                self.problem(
                    "metadata", f"Field names under `metadata` must be text; {_code(key)} is not."
                )
                continue
            if not isinstance(item, str):
                self.problem(
                    f"metadata.{key}",
                    f"`metadata.{key}` must be text; it is {_type_word(item)}. Put it in quotes.",
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
            self.problem("model", f"`model` must be text; it is {_type_word(value)}.")
            return
        if (
            not value
            or len(value) > MODEL_MAX_LENGTH
            or any(c.isspace() for c in value)
            or value.startswith("/")
            or value.endswith("/")
            or "//" in value
        ):
            self.problem(
                "model",
                f"`model` is {_code(value)}. Use a model alias such as `local`, or "
                "`provider/model`, with no spaces.",
            )
            return
        if self.mode == "repo" and "/" in value:
            self.problem(
                "model",
                f"`model` is {_code(value)}. A file shipped in the repository names a "
                "model alias, such as `local`, not `provider/model`.",
            )
            return
        out["model"] = value

    def _skills(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "skills" not in data:
            return
        value = data["skills"]
        if not isinstance(value, list):
            self.problem(
                "skills",
                f"`skills` must be a list, for example `skills: [nda-snapshot]`; "
                f"it is {_type_word(value)}.",
            )
            return
        if len(value) > MAX_SKILLS:
            self.problem(
                "skills",
                f"`skills` lists {len(value)} skills; at most {MAX_SKILLS} can be used on a turn.",
            )
            return
        refs: list[SkillRef] = []
        seen: set[str] = set()
        ok = True
        for i, item in enumerate(value):
            where = f"skills[{i}]"
            ref = self._skill_item(where, item)
            if ref is None:
                ok = False
                continue
            if ref.name in seen:
                self.problem(where, f"`{ref.name}` is listed twice.")
                ok = False
                continue
            seen.add(ref.name)
            refs.append(ref)
        if ok:
            out["skills"] = tuple(refs)

    def _skill_item(self, where: str, item: object) -> SkillRef | None:
        optional = False
        if isinstance(item, dict):
            mapping = item
            if "always" in mapping:
                self.problem(
                    f"{where}.always",
                    "`always` is reserved and cannot be saved yet. No skill is always loaded "
                    "in schema 1; the instructions can say which skill to load first.",
                )
                return None
            for key in mapping:
                if key not in ("name", "optional"):
                    self.problem(
                        f"{where}",
                        f"{_code(key)} is not a field of a skill entry. Use `name` and, "
                        "if you want, `optional`.",
                    )
                    return None
            if "name" not in mapping:
                self.problem(where, "A skill entry needs a `name`.")
                return None
            optional_value = mapping.get("optional", False)
            if not isinstance(optional_value, bool):
                self.problem(
                    f"{where}.optional",
                    f"`optional` must be `true` or `false`; it is {_code(optional_value)}.",
                )
                return None
            optional = optional_value
            item = mapping["name"]
        if not isinstance(item, str):
            self.problem(
                where,
                f"Each skill is a skill's name, or `{{name: ..., optional: true}}`; "
                f"this one is {_type_word(item)}.",
            )
            return None
        if not SKILL_SLUG_PATTERN.fullmatch(item):
            self.problem(
                where,
                f"{_code(item)} is not a skill name. Skill names use lowercase letters, "
                "digits and hyphens, for example `nda-snapshot`.",
            )
            return None
        return SkillRef(name=item, optional=optional)

    def _knowledge(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "knowledge" not in data:
            out["knowledge"] = (KnowledgeRef(name=KNOWLEDGE_MATTER),)
            return
        value = data["knowledge"]
        if value == KNOWLEDGE_NONE:
            out["knowledge"] = KNOWLEDGE_NONE
            return
        if not isinstance(value, list):
            self.problem(
                "knowledge",
                f"`knowledge` must be `none` or a list such as `[matter]`; it is {_code(value)}.",
            )
            return
        if not value:
            self.problem(
                "knowledge",
                "`knowledge` is an empty list. To search nothing, write `knowledge: none`.",
            )
            return
        refs: list[KnowledgeRef] = []
        ok = True
        for i, item in enumerate(value):
            where = f"knowledge[{i}]"
            if item == KNOWLEDGE_NONE:
                self.problem(where, "`none` stands alone: write `knowledge: none`, not a list.")
                ok = False
            elif item == KNOWLEDGE_MATTER:
                if any(r.name == KNOWLEDGE_MATTER for r in refs):
                    self.problem(where, "`matter` is listed twice.")
                    ok = False
                else:
                    refs.append(KnowledgeRef(name=KNOWLEDGE_MATTER))
            elif isinstance(item, dict) and item.get("name") == KNOWLEDGE_MATTER:
                self.problem(
                    where,
                    "`matter` cannot be optional, and needs no fields: write `matter`.",
                )
                ok = False
            elif isinstance(item, (str, dict)):
                self.problem(
                    where,
                    f"Naming a knowledge base {_NOT_YET} Stage 2 of the agent builder. "
                    "Use `matter`, or `none`.",
                )
                ok = False
            else:
                self.problem(
                    where,
                    f"Each `knowledge` item is `matter`; this one is {_type_word(item)}.",
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
        if value == TOOLS_CHAT:
            out["tools"] = TOOLS_CHAT
            return
        if value == TOOLS_NONE:
            self.problem(
                "tools",
                f"`tools: none` {_NOT_YET} Stage 3 of the agent builder. Use `tools: chat`.",
            )
            return
        if isinstance(value, list):
            if any(item in (TOOLS_CHAT, TOOLS_NONE) for item in value):
                self.problem(
                    "tools",
                    "`chat` and `none` stand alone and cannot be part of a list. "
                    "Write `tools: chat`.",
                )
                return
            self.problem(
                "tools",
                f"A list of tools {_NOT_YET} Stage 3 of the agent builder. Use `tools: chat`.",
            )
            return
        self.problem("tools", f"`tools` must be `chat`; it is {_code(value)}.")

    def _limits(self, data: dict[Any, Any], out: dict[str, Any]) -> None:
        if "limits" not in data:
            return
        value = data["limits"]
        if not isinstance(value, dict):
            self.problem(
                "limits",
                f"`limits` must be a set of fields, for example "
                f"`limits: {{{ROUNDS_LIMIT_FIELD}: 6}}`; it is {_type_word(value)}.",
            )
            return
        ok = True
        for key in value:
            where = f"limits.{key}"
            if key in _RESERVED_LIMITS:
                self.problem(
                    where, f"`{where}` is reserved and cannot be saved yet. {_RESERVED_LIMITS[key]}"
                )
                ok = False
            elif key != ROUNDS_LIMIT_FIELD:
                self.problem(
                    where,
                    f"{_code(key)} is not a limit. The one limit is `{ROUNDS_LIMIT_FIELD}`.",
                )
                ok = False
        rounds: int | None = None
        if ROUNDS_LIMIT_FIELD in value:
            limit = value[ROUNDS_LIMIT_FIELD]
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                self.problem(
                    f"limits.{ROUNDS_LIMIT_FIELD}",
                    f"`{ROUNDS_LIMIT_FIELD}` is the most rounds a turn may take: a whole "
                    f"number, 1 or more. It is {_code(limit)}.",
                )
                ok = False
            else:
                rounds = limit
        if ok:
            out["limits"] = AgentLimits(max_tool_calls=rounds)


def _load_front_matter(front: str) -> tuple[yaml.MappingNode | None, object]:
    """Parse the front matter, refusing what the format does not allow.

    Returns the composed root node (for line positions) and the loaded data.
    """
    try:
        for event in yaml.parse(front, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise _YamlRefused(
                    "Anchors and aliases (`&` and `*`) are not allowed in an agent file. "
                    "Write each value out."
                )
        root = yaml.compose(front, Loader=yaml.SafeLoader)
        if root is not None:
            _check_mappings(root)
        data = yaml.safe_load(front)
    except _YamlRefused:
        raise
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        # Front matter line n is line n + 2 of the file.
        where = f" at line {mark.line + 2}, column {mark.column + 1}" if mark else ""
        reason = exc.problem or "it cannot be read"
        raise _YamlRefused(f"The front matter is not valid YAML{where}: {reason}.") from None
    except yaml.YAMLError:
        raise _YamlRefused("The front matter is not valid YAML.") from None
    except (RecursionError, ValueError, TypeError):
        raise _YamlRefused("The front matter is not valid YAML.") from None
    if root is not None and not isinstance(root, yaml.MappingNode):
        return None, data
    return root, data


def _check_mappings(node: yaml.Node) -> None:
    """Refuse duplicate keys and merge keys anywhere in the tree."""
    stack: list[yaml.Node] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, yaml.MappingNode):
            seen: set[str] = set()
            for key_node, value_node in current.value:
                if isinstance(key_node, yaml.ScalarNode):
                    if key_node.tag == "tag:yaml.org,2002:merge":
                        raise _YamlRefused("Merge keys (`<<`) are not allowed in an agent file.")
                    key = key_node.value
                    if key in seen:
                        line = key_node.start_mark.line + 2
                        raise _YamlRefused(f"`{key}` appears twice (again at line {line}).")
                    seen.add(key)
                stack.append(value_node)
        elif isinstance(current, yaml.SequenceNode):
            stack.extend(current.value)


__all__ = [
    "MAX_BODY_BYTES",
    "MAX_FILE_BYTES",
    "MAX_FRONT_MATTER_BYTES",
    "MAX_SKILLS",
    "NAME_MAX_LENGTH",
    "ROUNDS_LIMIT_FIELD",
    "SCHEMA_VERSION",
    "AgentFile",
    "AgentFileCheck",
    "AgentFileInvalid",
    "AgentFileMode",
    "AgentFileNotice",
    "AgentFileProblem",
    "AgentLimits",
    "KnowledgeRef",
    "SkillRef",
    "fingerprint_agent_text",
    "normalise_line_endings",
    "parse_agent_file",
    "validate_agent_file",
]
