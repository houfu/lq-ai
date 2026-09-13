"""Unit tests for scripts/issue-triage/triage.py.

Run from the repo root:

    uv run --with pytest pytest scripts/issue-triage/tests

`run_gh` is the only seam that touches the network; every test replaces it
with an in-memory fake, so nothing here needs `gh` or credentials.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import triage

GOOD_LABELS = [
    "enhancement",
    "area:api",
    "effort:S",
    "priority:P2",
    "good first issue",
    "help wanted",
]


def good(**overrides: Any) -> dict[str, Any]:
    proposal: dict[str, Any] = {
        "number": 12,
        "title": "Return 204 from DELETE /things",
        "labels": list(GOOD_LABELS),
        "confidence": "high",
        "rationale": "Recipe is in CLAUDE.md; single handler.",
    }
    proposal.update(overrides)
    return proposal


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def test_in_scope_rules() -> None:
    assert triage.in_scope([]) == (True, "no labels")
    assert triage.in_scope(["bug", "needs-triage"])[0] is True
    assert triage.in_scope(["bug", "area:api"]) == (False, "already triaged")


def test_validate_accepts_a_well_formed_proposal() -> None:
    assert triage.validate_proposal(good()) == []


@pytest.mark.parametrize(
    ("labels", "needle"),
    [
        (["enhancement", "bug", "area:api", "effort:S", "priority:P2"], "exactly one type"),
        (["enhancement", "area:api", "effort:S", "priority:P2", "made-up"], "unknown label"),
        (["enhancement", "area:api", "priority:P2"], "exactly one effort"),
        (["enhancement", "area:api", "effort:S"], "exactly one priority"),
        (
            ["enhancement", "area:api", "effort:M", "priority:P2", "good first issue"],
            "requires `effort:S`",
        ),
        (
            [
                "enhancement",
                "area:gateway",
                "effort:S",
                "priority:P2",
                "good first issue",
                "security",
            ],
            "cannot combine",
        ),
        (
            ["enhancement", "area:api", "effort:S", "priority:P2", "help wanted", "needs-design"],
            "cannot combine",
        ),
        (
            ["enhancement", "area:api", "effort:L", "priority:P2", "help wanted"],
            "effort:S or effort:M",
        ),
        (["enhancement", "enhancement", "area:api", "effort:S", "priority:P2"], "duplicate labels"),
    ],
)
def test_validate_rejects_rule_violations(labels: list[str], needle: str) -> None:
    problems = triage.validate_proposal(good(labels=labels))
    assert any(needle in msg for msg in problems), problems


def test_validate_rejects_non_list_labels() -> None:
    assert triage.validate_proposal(good(labels="bug")) == ["`labels` must be a list of strings"]


def test_warnings_are_soft() -> None:
    p = good(labels=["bug", "effort:S", "priority:P2"], confidence="low")
    assert triage.proposal_warnings(p) == ["no area label", "low confidence"]
    assert "no area label" not in triage.proposal_warnings(
        good(labels=["question", "effort:S", "priority:P3"])
    )


def test_plan_changes_adds_missing_and_drops_intake() -> None:
    p = {"labels": ["bug", "area:api", "effort:S", "priority:P1"]}
    add, remove = triage.plan_changes(p, ["bug", "needs-triage"])
    assert add == ["area:api", "effort:S", "priority:P1"]
    assert remove == ["needs-triage"]


def test_plan_changes_can_keep_intake_label() -> None:
    p = {"labels": ["bug", "effort:S", "priority:P1"]}
    assert triage.plan_changes(p, ["needs-triage"], keep_intake=True) == (
        ["bug", "effort:S", "priority:P1"],
        [],
    )


def test_plan_changes_never_removes_a_proposed_label() -> None:
    assert triage.plan_changes({"labels": ["bug"], "remove": ["bug"]}, ["bug"]) == ([], [])


def test_parse_numbers() -> None:
    assert triage.parse_numbers("1, 2,3") == {1, 2, 3}
    assert triage.parse_numbers(None) == set()
    with pytest.raises(triage.TriageError):
        triage.parse_numbers("1,x")


def test_select_only_and_skip() -> None:
    rows = [good(number=n) for n in (5, 3, 9)]
    assert [p["number"] for p in triage.select_proposals(rows, set(), set())] == [3, 5, 9]
    assert [p["number"] for p in triage.select_proposals(rows, {9, 3}, {3})] == [9]


def test_load_proposals_accepts_bare_list(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(json.dumps([good()]))
    _doc, proposals = triage.load_proposals(path)
    assert proposals[0]["number"] == 12


# ---------------------------------------------------------------------------
# gh-backed commands, with the gh seam faked
# ---------------------------------------------------------------------------


class FakeGh:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.live: dict[int, dict[str, Any]] = {}
        self.labels: set[str] = set(triage.LABEL_DEFS)

    def __call__(self, args: list[str]) -> str:
        args = list(args)
        self.calls.append(args)
        if args[:2] == ["label", "list"]:
            return json.dumps([{"name": n} for n in sorted(self.labels)])
        if args[:2] == ["label", "create"]:
            self.labels.add(args[2])
            return ""
        if args[:2] == ["issue", "view"]:
            rec = self.live[int(args[2])]
            return json.dumps(
                {
                    "labels": [{"name": n} for n in rec["labels"]],
                    "state": rec.get("state", "OPEN"),
                    "title": "t",
                }
            )
        if args[:2] == ["issue", "edit"]:
            return ""
        raise AssertionError(f"unexpected gh call: {args}")

    def edits(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["issue", "edit"]]


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    fake = FakeGh()
    monkeypatch.setattr(triage, "run_gh", fake)
    monkeypatch.setattr(triage, "ensure_gh", lambda: None)
    return fake


def write_proposals(tmp_path: Path, proposals: list[dict[str, Any]]) -> Path:
    path = tmp_path / "proposals.json"
    path.write_text(json.dumps({"repo": "o/r", "proposals": proposals}))
    return path


def test_apply_dry_run_edits_nothing(
    fake_gh: FakeGh, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_gh.live[12] = {"labels": ["needs-triage"]}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path)]) == 0
    assert fake_gh.edits() == []
    out = capsys.readouterr().out
    assert "would +[enhancement, area:api" in out
    assert "-[needs-triage]" in out
    assert "re-run with --yes" in out


def test_apply_yes_edits_with_add_and_remove(fake_gh: FakeGh, tmp_path: Path) -> None:
    fake_gh.live[12] = {"labels": ["needs-triage"]}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes"]) == 0
    (edit,) = fake_gh.edits()
    assert edit[2] == "12"
    assert edit[edit.index("--add-label") + 1] == ",".join(GOOD_LABELS)
    assert edit[edit.index("--remove-label") + 1] == "needs-triage"


def test_apply_skips_issue_triaged_since_dump_unless_forced(
    fake_gh: FakeGh, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_gh.live[12] = {"labels": ["bug", "area:api"]}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes"]) == 0
    assert fake_gh.edits() == []
    assert "labelled since dump" in capsys.readouterr().out
    assert (
        triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes", "--force"]) == 0
    )
    (edit,) = fake_gh.edits()
    assert "bug" not in edit[edit.index("--add-label") + 1]


def test_apply_skips_closed_issues(fake_gh: FakeGh, tmp_path: Path) -> None:
    fake_gh.live[12] = {"labels": [], "state": "CLOSED"}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes"]) == 0
    assert fake_gh.edits() == []


def test_apply_refuses_invalid_proposals(fake_gh: FakeGh, tmp_path: Path) -> None:
    bad = good(labels=["bug", "enhancement", "effort:S", "priority:P2"])
    fake_gh.live[12] = {"labels": []}
    path = write_proposals(tmp_path, [bad])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes"]) == 1
    assert fake_gh.edits() == []


def test_apply_requires_labels_to_exist_unless_told_to_create(
    fake_gh: FakeGh, tmp_path: Path
) -> None:
    fake_gh.labels.discard("area:api")
    fake_gh.live[12] = {"labels": []}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes"]) == 1
    assert fake_gh.edits() == []
    argv = ["apply", "--repo", "o/r", "--proposals", str(path), "--yes", "--create-missing-labels"]
    assert triage.main(argv) == 0
    created = next(c[:3] for c in fake_gh.calls if c[:2] == ["label", "create"])
    assert created == ["label", "create", "area:api"]
    assert len(fake_gh.edits()) == 1


def test_apply_only_and_skip_select_rows(fake_gh: FakeGh, tmp_path: Path) -> None:
    fake_gh.live.update({1: {"labels": []}, 2: {"labels": []}, 3: {"labels": []}})
    path = write_proposals(tmp_path, [good(number=n) for n in (1, 2, 3)])
    argv = [
        "apply",
        "--repo",
        "o/r",
        "--proposals",
        str(path),
        "--yes",
        "--only",
        "1,3",
        "--skip",
        "3",
    ]
    assert triage.main(argv) == 0
    assert [e[2] for e in fake_gh.edits()] == ["1"]


def test_labels_reports_and_creates_missing(
    fake_gh: FakeGh, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_gh.labels -= {"effort:S", "needs-design"}
    assert triage.main(["labels", "--repo", "o/r"]) == 0
    out = capsys.readouterr().out
    assert "2 taxonomy label(s) missing" in out
    assert "re-run with --create" in out
    assert triage.main(["labels", "--repo", "o/r", "--create"]) == 0
    assert {c[2] for c in fake_gh.calls if c[:2] == ["label", "create"]} == {
        "effort:S",
        "needs-design",
    }


def test_review_flags_violations_and_writes_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = good(number=13, labels=["bug", "enhancement", "effort:S", "priority:P2"])
    path = write_proposals(tmp_path, [good(), bad])
    md = tmp_path / "proposals.md"
    assert triage.main(["review", "--proposals", str(path), "--md", str(md), "-v"]) == 1
    out = capsys.readouterr().out
    assert "1 proposal(s) violate LABELS.md" in out
    assert "#13: exactly one type" in out
    assert "rationale: Recipe is in CLAUDE.md" in out
    assert md.read_text().count("\n| #") == 2


def test_review_contributors_filter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plain = good(number=20, labels=["bug", "area:api", "effort:M", "priority:P2"])
    path = write_proposals(tmp_path, [good(), plain])
    assert triage.main(["review", "--proposals", str(path), "--contributors"]) == 0
    out = capsys.readouterr().out
    assert "   12  " in out
    assert "   20  " not in out


def test_fetch_marks_scope_and_writes_both_files(
    fake_gh: FakeGh, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues = [
        {"number": 1, "title": "a", "labels": []},
        {"number": 2, "title": "b", "labels": [{"name": "bug"}, {"name": "needs-triage"}]},
        {"number": 3, "title": "c", "labels": [{"name": "bug"}, {"name": "area:api"}]},
    ]

    def fake_run(args: list[str]) -> str:
        fake_gh.calls.append(list(args))
        if args[:2] == ["issue", "list"]:
            return json.dumps(issues)
        if args[:2] == ["label", "list"]:
            return json.dumps([{"name": "bug", "color": "d73a4a", "description": ""}])
        raise AssertionError(args)

    monkeypatch.setattr(triage, "run_gh", fake_run)
    monkeypatch.setattr(triage, "OUT_DIR", tmp_path)
    issues_path, labels_path = tmp_path / "issues.json", tmp_path / "labels.json"
    argv = ["fetch", "--repo", "o/r", "--issues", str(issues_path), "--labels", str(labels_path)]
    assert triage.main(argv) == 0
    dump = json.loads(issues_path.read_text())
    assert dump["counts"] == {"open": 3, "untriaged": 2}
    assert [i["in_scope"] for i in dump["issues"]] == [True, True, False]
    assert json.loads(labels_path.read_text())[0]["name"] == "bug"


def test_apply_dry_run_reports_missing_labels_but_still_plans(
    fake_gh: FakeGh, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_gh.labels.discard("effort:S")
    fake_gh.live[12] = {"labels": []}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path)]) == 0
    out = capsys.readouterr().out
    assert "MISSING" in out and "effort:S" in out
    assert "would +[" in out
    assert fake_gh.edits() == []


def test_apply_reports_already_applied_before_since_dump(
    fake_gh: FakeGh, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_gh.live[12] = {"labels": list(GOOD_LABELS)}
    path = write_proposals(tmp_path, [good()])
    assert triage.main(["apply", "--repo", "o/r", "--proposals", str(path), "--yes"]) == 0
    assert "already has the proposed labels" in capsys.readouterr().out
    assert fake_gh.edits() == []
