"""The agent files shipped in the repository's ``agents/`` folder.

Every shipped file must parse and validate in ``repo`` mode, and the
fingerprints are pinned so a change to a shipped file is a visible change
to this test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents import ListedItem, parse_agent_file, validate_agent_file

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"
DEFAULT_AGENT = AGENTS_DIR / "lq-ai.md"
EXAMPLES_DIR = AGENTS_DIR / "examples"

PINNED_FINGERPRINTS = {
    "lq-ai.md": "b1d1aa5b561f0fe0f0e2da632cd9827317f0948a559a16e7e3de28516b6f6ee6",
    "examples/nda-comparer.md": "745f4d4b48f0eacdcf55220641992eb6a46435c3b0ef891ec4fece368b4b41a6",
    "examples/contract-first-read.md": (
        "18b170328272024893920ad084b78f96fab7a058224739d92eeebc264d978d31"
    ),
}


def shipped_files() -> list[Path]:
    return sorted(p for p in AGENTS_DIR.rglob("*.md") if p.name != "README.md")


def read(path: Path) -> str:
    # Bytes, decoded here, so the platform's newline translation plays no part.
    return path.read_bytes().decode("utf-8")


def test_the_shipped_files_are_the_pinned_ones() -> None:
    found = {p.relative_to(AGENTS_DIR).as_posix() for p in shipped_files()}
    assert found == set(PINNED_FINGERPRINTS)


@pytest.mark.parametrize("path", shipped_files(), ids=lambda p: p.name)
def test_every_shipped_file_validates_in_repo_mode(path: Path) -> None:
    result = validate_agent_file(read(path), mode="repo")
    assert result.problems == ()
    assert result.notices == ()
    assert result.agent is not None
    assert path.stem == result.agent.name


@pytest.mark.parametrize("path", shipped_files(), ids=lambda p: p.name)
def test_every_shipped_file_has_the_same_saved_text_in_both_modes(path: Path) -> None:
    store = validate_agent_file(read(path), mode="store")
    repo = validate_agent_file(read(path), mode="repo")
    assert store.agent is not None and repo.agent is not None
    assert store.notices == ()
    assert store.agent.text == repo.agent.text
    assert store.agent.fingerprint == repo.agent.fingerprint


@pytest.mark.parametrize(("relative", "expected"), sorted(PINNED_FINGERPRINTS.items()))
def test_shipped_fingerprints_are_pinned(relative: str, expected: str) -> None:
    text = read(AGENTS_DIR / relative)
    assert parse_agent_file(text, mode="repo").fingerprint == expected
    # The same file checked out with Windows line endings gives the same value.
    crlf = text.replace("\r\n", "\n").replace("\n", "\r\n")
    assert parse_agent_file(crlf, mode="repo").fingerprint == expected


def test_default_agent_matches_the_rulings() -> None:
    agent = parse_agent_file(read(DEFAULT_AGENT), mode="repo")
    assert agent.name == "lq-ai"
    assert agent.title == "LQ.AI"
    assert agent.description == "The main agent."
    assert agent.model is None
    assert agent.skills == ()
    assert agent.tools == "chat"
    assert agent.knowledge == "none"
    assert agent.version is None
    assert agent.instructions == ""
    assert "model:" not in agent.text
    assert "version:" not in agent.text


def test_nda_comparer_is_the_plans_example() -> None:
    agent = parse_agent_file(read(EXAMPLES_DIR / "nda-comparer.md"), mode="store")
    assert agent.name == "nda-comparer"
    assert agent.title == "NDA Comparer"
    assert agent.model == "local"
    assert agent.skills == (ListedItem(name="nda-snapshot"),)
    assert agent.knowledge == (ListedItem(name="matter"),)
    assert agent.tools == "chat"
    assert agent.has_instructions


def test_second_example_exercises_other_fields() -> None:
    agent = parse_agent_file(read(EXAMPLES_DIR / "contract-first-read.md"), mode="repo")
    assert agent.version is None
    assert agent.title == agent.name
    # The listed skills need tier 2 or stronger; `local` is tier 1 on the
    # stock configuration, so the example runs as shipped.
    assert agent.model == "local"
    assert agent.skills == (
        ListedItem(name="contract-snapshot"),
        ListedItem(name="msa-snapshot", optional=True),
    )
    assert agent.knowledge == "none"
    # `limits` is left out of shipped files while its key's name is not ruled.
    assert agent.limits.max_rounds is None
    assert "limits" not in agent.text
    assert agent.metadata == {"author": "LegalQuants", "jurisdiction": "agnostic"}


def test_skills_named_by_shipped_files_exist_as_built_in_skills() -> None:
    skills_dir = AGENTS_DIR.parent / "skills"
    for path in shipped_files():
        agent = parse_agent_file(read(path), mode="repo")
        for ref in agent.skills:
            assert (skills_dir / ref.name / "SKILL.md").is_file(), (path.name, ref.name)
