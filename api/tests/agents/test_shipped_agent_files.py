"""The agent files shipped in the repository's ``agents/`` folder.

Every shipped file must parse and validate in ``repo`` mode, so each one
carries ``version``, and the fingerprints are pinned so a change to a shipped file is a visible change
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
    "lq-ai.md": "b5ad5acc2e18c6db7f56e76a7c649af5577a9887dd16435271e05ab63eb68bad",
    "examples/nda-comparer.md": "e665d5bdbbbfbe8bf56ba477d47a9c535263bdd5e4284973d8470f63ff9e4445",
    "examples/contract-first-read.md": (
        "5eada9e744cd4a5dfeab46c17561367a6ae145d23cf2b05d8852ce9c34d8a0bf"
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
def test_every_shipped_file_carries_a_version(path: Path) -> None:
    agent = parse_agent_file(read(path), mode="repo")
    assert isinstance(agent.version, int)
    assert agent.version >= 1
    assert f"\nversion: {agent.version}\n" in agent.text


@pytest.mark.parametrize("path", shipped_files(), ids=lambda p: p.name)
def test_every_shipped_file_pasted_differs_only_in_version(path: Path) -> None:
    # Pasted, a shipped file saves without its `version` line, with one notice.
    # Every other field reads the same in both modes.
    store = validate_agent_file(read(path), mode="store")
    repo = validate_agent_file(read(path), mode="repo")
    assert store.agent is not None and repo.agent is not None
    assert [n.field for n in store.notices] == ["version"]
    version_line = f"version: {repo.agent.version}\n"
    assert store.agent.text == repo.agent.text.replace(version_line, "", 1)
    assert store.agent.version is None
    assert store.agent.model_dump(exclude={"version", "text", "fingerprint"}) == (
        repo.agent.model_dump(exclude={"version", "text", "fingerprint"})
    )


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
    assert agent.version == 1
    assert agent.instructions == ""
    assert "model:" not in agent.text


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
    assert agent.version == 1
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
