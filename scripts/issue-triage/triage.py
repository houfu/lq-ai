#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Screen-and-label helper for the LQ.AI issue tracker.

Four subcommands, run from the repo root in this order:

    uv run scripts/issue-triage/triage.py fetch  --repo LegalQuants/lq-ai
    # ... run the Sonnet screening workflow (scripts/issue-triage/README.md) ...
    uv run scripts/issue-triage/triage.py review
    uv run scripts/issue-triage/triage.py labels --repo LegalQuants/lq-ai [--create]
    uv run scripts/issue-triage/triage.py apply  --repo LegalQuants/lq-ai [--yes]

`fetch` dumps the open issues and the repo's labels through the `gh` CLI and
marks which issues are still untriaged. `review` prints the agents' proposals
as a table (and validates them against LABELS.md) before anything touches
GitHub. `labels` shows which taxonomy labels the repo lacks and creates them on
request. `apply` is a dry run unless `--yes` is passed; it re-reads each
issue's live labels first and skips anything a human labelled since the dump.

Only the standard library is used. All GitHub traffic goes through `gh`, so the
caller's own `gh auth` scope is the only credential involved.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
ISSUES_PATH = OUT_DIR / "issues.json"
LABELS_PATH = OUT_DIR / "labels.json"
PROPOSALS_PATH = OUT_DIR / "proposals.json"

DEFAULT_REPO = "LegalQuants/lq-ai"
INTAKE_LABEL = "needs-triage"
ISSUE_FIELDS = (
    "number,title,body,state,url,labels,author,assignees,milestone,createdAt,updatedAt,comments"
)

# ---------------------------------------------------------------------------
# Taxonomy (mirror of LABELS.md — keep the two in step)
# ---------------------------------------------------------------------------

TYPE_LABELS = {
    "bug": ("d73a4a", "Existing behaviour diverges from the PRD, API sketch, or docstring"),
    "enhancement": ("a2eeef", "New capability or behaviour change; most PRD §9 DE-XXX items"),
    "documentation": ("0075ca", "Deliverable is a doc, guide, ADR, or mini-PRD"),
    "question": ("d876e3", "Asking, not requesting; resolves by answer, doc fix, or redirect"),
    "skill-proposal": ("5319e7", "New or changed skill with legal substance"),
    "chore": ("cfd3d7", "Deps, CI plumbing, refactors with no behaviour change, tooling"),
}
AREA_LABELS = {
    "area:api": ("1d76db", "api/** — FastAPI backend, migrations, workers"),
    "area:gateway": ("1d76db", "gateway/** — Inference Gateway (security boundary)"),
    "area:web": ("1d76db", "web/** — OpenWebUI (SvelteKit) fork"),
    "area:word-addin": ("1d76db", "word-addin/** — Office.js add-in"),
    "area:desktop": ("1d76db", "desktop/**"),
    "area:skills": ("1d76db", "skills/** — skill content and skill tooling"),
    "area:docs": ("1d76db", "docs/**, README, CONTRIBUTING, policy docs"),
    "area:deploy": ("1d76db", "deploy/**, compose files, Dockerfiles, proxy/**"),
    "area:ci": ("1d76db", ".github/**, Makefile, lint/test plumbing"),
    "area:integrations": ("1d76db", "slack-bridge/**, teams-bridge/**, other bridges"),
}
EFFORT_LABELS = {
    "effort:S": ("fbca04", "Under a day; one subsystem; fix location nameable"),
    "effort:M": ("fbca04", "A few days; crosses a boundary or needs a migration/contract change"),
    "effort:L": ("fbca04", "More than a week; new subsystem or blocked on design"),
}
PRIORITY_LABELS = {
    "priority:P0": ("b60205", "Users blocked or data/security at risk"),
    "priority:P1": ("e99695", "Next up: visible breakage with workaround, gates a milestone"),
    "priority:P2": ("f9d0c4", "Normal; the default"),
    "priority:P3": ("fef2c0", "Someday: polish, speculative, depends on unplanned work"),
}
CONTRIBUTOR_LABELS = {
    "good first issue": (
        "7057ff",
        "effort:S, clear scope, nameable fix location, no security/legal",
    ),
    "help wanted": ("008672", "Well scoped; a contributor can open a PR without a design chat"),
}
STATE_LABELS = {
    "security": ("ee0701", "Touches a CODEOWNERS security path or auth/audit/crypto"),
    "needs-info": ("d4c5f9", "Cannot be acted on as written; rationale says what is missing"),
    "needs-design": ("c5def5", "Product/architecture/authz decision needed first"),
    "needs-attorney": ("bfdadc", "Legal substance; practicing-attorney authorship or review"),
    "duplicate": ("cfd3d7", "Same ask as an earlier open issue"),
}
LABEL_DEFS: dict[str, tuple[str, str]] = {
    **TYPE_LABELS,
    **AREA_LABELS,
    **EFFORT_LABELS,
    **PRIORITY_LABELS,
    **CONTRIBUTOR_LABELS,
    **STATE_LABELS,
}
GFI = "good first issue"
HELP_WANTED = "help wanted"
GFI_BLOCKERS = {"security", "needs-design", "needs-attorney", "needs-info"}
HELP_WANTED_BLOCKERS = {"needs-design", "needs-info"}


class TriageError(RuntimeError):
    """A user-facing failure: printed without a traceback, exit code 1."""


# ---------------------------------------------------------------------------
# gh plumbing
# ---------------------------------------------------------------------------


def ensure_gh() -> None:
    if shutil.which("gh") is None:
        raise TriageError("`gh` (GitHub CLI) is not on PATH. Install it and run `gh auth login`.")


def run_gh(args: Sequence[str]) -> str:
    """Run `gh` and return stdout. Tests monkeypatch this single seam."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise TriageError(f"gh {' '.join(args)}\n{proc.stderr.strip()}")
    return proc.stdout


def gh_json(args: Sequence[str]) -> Any:
    return json.loads(run_gh(args) or "null")


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def label_names(issue: dict[str, Any]) -> list[str]:
    return [lbl["name"] if isinstance(lbl, dict) else str(lbl) for lbl in issue.get("labels", [])]


def in_scope(labels: Iterable[str]) -> tuple[bool, str]:
    """Is this issue still untriaged?

    No labels at all, or still carrying the templates' intake label, means
    nobody has looked at it yet. Anything else was triaged by a human and is
    left alone (``apply --force`` overrides).
    """
    names = list(labels)
    if not names:
        return True, "no labels"
    if INTAKE_LABEL in names:
        return True, f"carries {INTAKE_LABEL}"
    return False, "already triaged"


def validate_proposal(proposal: dict[str, Any]) -> list[str]:
    """Return the rule violations that must block `apply` (empty = OK)."""
    problems: list[str] = []
    labels = proposal.get("labels")
    if not isinstance(proposal.get("number"), int):
        problems.append("`number` must be an integer")
    if not isinstance(labels, list) or not all(isinstance(lbl, str) for lbl in labels):
        return [*problems, "`labels` must be a list of strings"]
    unknown = [lbl for lbl in labels if lbl not in LABEL_DEFS]
    if unknown:
        problems.append(f"unknown label(s): {', '.join(unknown)} — see LABELS.md")
    if len(set(labels)) != len(labels):
        problems.append("duplicate labels")
    for group, name in (
        (TYPE_LABELS, "type"),
        (EFFORT_LABELS, "effort"),
        (PRIORITY_LABELS, "priority"),
    ):
        picked = [lbl for lbl in labels if lbl in group]
        if len(picked) != 1:
            problems.append(f"exactly one {name} label required, got {picked or 'none'}")
    if GFI in labels:
        if "effort:S" not in labels:
            problems.append(f"`{GFI}` requires `effort:S`")
        blocked = GFI_BLOCKERS.intersection(labels)
        if blocked:
            problems.append(f"`{GFI}` cannot combine with {sorted(blocked)}")
    if HELP_WANTED in labels:
        blocked = HELP_WANTED_BLOCKERS.intersection(labels)
        if blocked:
            problems.append(f"`{HELP_WANTED}` cannot combine with {sorted(blocked)}")
        if "effort:L" in labels:
            problems.append(f"`{HELP_WANTED}` requires effort:S or effort:M")
    return problems


def proposal_warnings(proposal: dict[str, Any]) -> list[str]:
    """Soft advice shown by `review`; never blocks."""
    labels = proposal.get("labels", [])
    warnings: list[str] = []
    is_question_or_info = "question" in labels or "needs-info" in labels
    if not any(lbl in AREA_LABELS for lbl in labels) and not is_question_or_info:
        warnings.append("no area label")
    if proposal.get("confidence") == "low":
        warnings.append("low confidence")
    if "duplicate" in labels and not proposal.get("duplicate_of"):
        warnings.append("`duplicate` without duplicate_of")
    return warnings


def plan_changes(
    proposal: dict[str, Any], live_labels: Iterable[str], *, keep_intake: bool = False
) -> tuple[list[str], list[str]]:
    """Return (labels to add, labels to remove) for one issue."""
    live = set(live_labels)
    add = [lbl for lbl in proposal["labels"] if lbl not in live]
    wanted_removals = list(proposal.get("remove") or [])
    if not keep_intake and INTAKE_LABEL not in wanted_removals:
        wanted_removals.append(INTAKE_LABEL)
    remove = [lbl for lbl in wanted_removals if lbl in live and lbl not in proposal["labels"]]
    return add, remove


def parse_numbers(raw: str | None) -> set[int]:
    if not raw:
        return set()
    try:
        return {int(part) for part in raw.replace(" ", "").split(",") if part}
    except ValueError as exc:
        raise TriageError(f"expected comma-separated issue numbers, got {raw!r}") from exc


def select_proposals(
    proposals: list[dict[str, Any]], only: set[int], skip: set[int]
) -> list[dict[str, Any]]:
    chosen = [p for p in proposals if (not only or p["number"] in only) and p["number"] not in skip]
    return sorted(chosen, key=lambda p: p["number"])


def load_proposals(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.exists():
        raise TriageError(f"{path} not found — run the screening workflow first (see README.md)")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        doc = {"proposals": doc}
    proposals = doc.get("proposals")
    if not isinstance(proposals, list):
        raise TriageError(f"{path} must be a list or an object with a `proposals` list")
    return doc, proposals


def load_issue_dump(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TriageError(f"{path} not found — run `triage.py fetch` first")
    return json.loads(path.read_text(encoding="utf-8"))


def format_table(rows: list[dict[str, Any]], *, verbose: bool) -> str:
    lines = [f"{'#':>5}  {'conf':<6}  {'labels':<52}  title", "-" * 100]
    for p in rows:
        labels = ", ".join(p["labels"])
        lines.append(f"{p['number']:>5}  {p.get('confidence', '?'):<6}  {labels:<52}  {p['title']}")
        if verbose:
            for key in ("rationale", "contributor_profile", "notes_for_maintainer"):
                if p.get(key):
                    lines.append(textwrap.indent(textwrap.fill(f"{key}: {p[key]}", 96), " " * 7))
            if p.get("pointers"):
                lines.append(" " * 7 + "pointers: " + "; ".join(p["pointers"]))
            if p.get("duplicate_of"):
                lines.append(" " * 7 + f"duplicate_of: #{p['duplicate_of']}")
            lines.append("")
    return "\n".join(lines)


def format_markdown(rows: list[dict[str, Any]]) -> str:
    out = ["| # | Title | Labels | Conf | Rationale |", "|---|---|---|---|---|"]
    for p in rows:
        labels = " ".join(f"`{lbl}`" for lbl in p["labels"])
        rationale = str(p.get("rationale", "")).replace("|", "\\|").replace("\n", " ")
        title = str(p["title"]).replace("|", "\\|")
        out.append(
            f"| #{p['number']} | {title} | {labels} | {p.get('confidence', '')} | {rationale} |"
        )
    return "\n".join(out) + "\n"


def summarise(rows: list[dict[str, Any]]) -> str:
    def count(pred: Any) -> int:
        return sum(1 for p in rows if pred(p["labels"]))

    parts = [f"{len(rows)} proposals"]
    for name in TYPE_LABELS:
        n = count(lambda ls, name=name: name in ls)
        if n:
            parts.append(f"{name}={n}")
    parts.append(f"{GFI}={count(lambda ls: GFI in ls)}")
    parts.append(f"{HELP_WANTED}={count(lambda ls: HELP_WANTED in ls)}")
    for name in ("needs-design", "needs-info", "needs-attorney", "duplicate", "security"):
        n = count(lambda ls, name=name: name in ls)
        if n:
            parts.append(f"{name}={n}")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    ensure_gh()
    issues = gh_json(
        [
            "issue",
            "list",
            "-R",
            args.repo,
            "--state",
            "open",
            "--limit",
            str(args.limit),
            "--json",
            ISSUE_FIELDS,
        ]
    )
    labels = gh_json(
        ["label", "list", "-R", args.repo, "--limit", "300", "--json", "name,color,description"]
    )
    for issue in issues:
        names = label_names(issue)
        ok, why = in_scope(names)
        issue["label_names"] = names
        issue["in_scope"] = ok
        issue["scope_reason"] = why
    untriaged = [i for i in issues if i["in_scope"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    args.issues.write_text(
        json.dumps(
            {
                "repo": args.repo,
                "fetched_with": f"gh issue list --state open --limit {args.limit}",
                "counts": {"open": len(issues), "untriaged": len(untriaged)},
                "issues": issues,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    args.labels.write_text(
        json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.issues}  ({len(issues)} open issues, {len(untriaged)} untriaged)")
    print(f"wrote {args.labels}  ({len(labels)} labels in {args.repo})")
    if len(issues) >= args.limit:
        print(f"WARNING: hit --limit {args.limit}; re-run with a higher limit", file=sys.stderr)
    for issue in untriaged:
        print(f"  #{issue['number']:<5} {issue['scope_reason']:<20} {issue['title']}")
    print("\nnext: run the screening workflow (scripts/issue-triage/README.md, step 2)")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    _doc, proposals = load_proposals(args.proposals)
    rows = select_proposals(proposals, parse_numbers(args.only), parse_numbers(args.skip))
    if args.contributors:
        rows = [p for p in rows if GFI in p["labels"] or HELP_WANTED in p["labels"]]
    print(format_table(rows, verbose=args.verbose))
    print()
    print(summarise(rows))
    bad = {p["number"]: validate_proposal(p) for p in rows}
    bad = {n: probs for n, probs in bad.items() if probs}
    soft = {p["number"]: proposal_warnings(p) for p in rows}
    soft = {n: w for n, w in soft.items() if w}
    if soft:
        print(f"\n{len(soft)} proposal(s) with warnings (apply still allowed):")
        for n, warnings in soft.items():
            print(f"  #{n}: {'; '.join(warnings)}")
    if bad:
        print(f"\n{len(bad)} proposal(s) violate LABELS.md and will block `apply`:")
        for n, problems in bad.items():
            print(f"  #{n}: {'; '.join(problems)}")
    if args.md:
        args.md.write_text(format_markdown(rows), encoding="utf-8")
        print(f"\nwrote {args.md}")
    return 1 if bad else 0


def cmd_labels(args: argparse.Namespace) -> int:
    ensure_gh()
    existing = {
        lbl["name"]
        for lbl in gh_json(["label", "list", "-R", args.repo, "--limit", "300", "--json", "name"])
    }
    missing = [name for name in LABEL_DEFS if name not in existing]
    if not missing:
        print(f"all {len(LABEL_DEFS)} taxonomy labels exist in {args.repo}")
        return 0
    print(f"{len(missing)} taxonomy label(s) missing in {args.repo}:")
    for name in missing:
        print(f"  {name:<20} #{LABEL_DEFS[name][0]}  {LABEL_DEFS[name][1]}")
    if not args.create:
        print("\nre-run with --create to add them")
        return 0
    for name in missing:
        create_label(args.repo, name)
    return 0


def create_label(repo: str, name: str) -> None:
    color, description = LABEL_DEFS[name]
    run_gh(["label", "create", name, "-R", repo, "--color", color, "--description", description])
    print(f"  created {name}")


def cmd_apply(args: argparse.Namespace) -> int:
    ensure_gh()
    _doc, proposals = load_proposals(args.proposals)
    rows = select_proposals(proposals, parse_numbers(args.only), parse_numbers(args.skip))
    if not rows:
        raise TriageError("no proposals selected")
    invalid = {p["number"]: validate_proposal(p) for p in rows}
    invalid = {n: probs for n, probs in invalid.items() if probs}
    if invalid:
        for n, problems in invalid.items():
            print(f"  #{n}: {'; '.join(problems)}", file=sys.stderr)
        raise TriageError(
            f"{len(invalid)} proposal(s) violate LABELS.md — fix {args.proposals} or use --skip"
        )

    existing = {
        lbl["name"]
        for lbl in gh_json(["label", "list", "-R", args.repo, "--limit", "300", "--json", "name"])
    }
    needed = sorted({lbl for p in rows for lbl in p["labels"]})
    missing = [lbl for lbl in needed if lbl not in existing]
    if missing and args.yes and not args.create_missing_labels:
        raise TriageError(
            "labels not present in the repo: "
            + ", ".join(missing)
            + "\nrun `triage.py labels --create` or pass --create-missing-labels"
        )
    if missing and args.yes:
        print(f"creating {len(missing)} missing label(s)")
        for name in missing:
            create_label(args.repo, name)
    elif missing:
        how = "would create" if args.create_missing_labels else "MISSING (run `labels --create`)"
        print(f"[dry-run] {how} {len(missing)} label(s): {', '.join(missing)}")
    mode = "APPLY" if args.yes else "dry-run"
    print(f"[{mode}] {len(rows)} proposal(s) against {args.repo}\n")
    applied = skipped = failed = 0
    for p in rows:
        n = p["number"]
        try:
            live = gh_json(
                ["issue", "view", str(n), "-R", args.repo, "--json", "labels,state,title"]
            )
        except TriageError as exc:
            failed += 1
            print(f"  #{n:<5} FAILED to read issue: {exc}")
            continue
        live_names = label_names(live)
        if str(live.get("state", "")).upper() != "OPEN":
            skipped += 1
            print(f"  #{n:<5} skip  (issue is {live.get('state')})")
            continue
        add, remove = plan_changes(p, live_names, keep_intake=args.keep_needs_triage)
        if not add and not remove:
            skipped += 1
            print(f"  #{n:<5} skip  (already has the proposed labels)")
            continue
        still_untriaged, _why = in_scope(live_names)
        if not still_untriaged and not args.force:
            skipped += 1
            print(
                f"  #{n:<5} skip  (labelled since dump: {', '.join(live_names)}; "
                "--force to override)"
            )
            continue
        plan = f"+[{', '.join(add)}]" + (f" -[{', '.join(remove)}]" if remove else "")
        if not args.yes:
            print(f"  #{n:<5} would {plan}  | {p['title']}")
            continue
        edit = ["issue", "edit", str(n), "-R", args.repo]
        if add:
            edit += ["--add-label", ",".join(add)]
        if remove:
            edit += ["--remove-label", ",".join(remove)]
        try:
            run_gh(edit)
        except TriageError as exc:
            failed += 1
            print(f"  #{n:<5} FAILED {plan}: {exc}")
            continue
        applied += 1
        print(f"  #{n:<5} done  {plan}  | {p['title']}")

    print(f"\n{mode}: applied={applied} skipped={skipped} failed={failed}")
    if not args.yes:
        print("re-run with --yes to apply")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="triage.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/name (default {DEFAULT_REPO})")

    def add_proposals(p: argparse.ArgumentParser) -> None:
        p.add_argument("--proposals", type=Path, default=PROPOSALS_PATH)
        p.add_argument("--only", help="comma-separated issue numbers to include")
        p.add_argument("--skip", help="comma-separated issue numbers to exclude")

    fetch = sub.add_parser("fetch", help="dump open issues + repo labels via gh")
    add_repo(fetch)
    fetch.add_argument("--limit", type=int, default=500)
    fetch.add_argument("--issues", type=Path, default=ISSUES_PATH)
    fetch.add_argument("--labels", type=Path, default=LABELS_PATH)
    fetch.set_defaults(func=cmd_fetch)

    review = sub.add_parser("review", help="print and validate the proposals")
    add_proposals(review)
    review.add_argument("-v", "--verbose", action="store_true", help="show rationale per issue")
    review.add_argument(
        "--contributors", action="store_true", help="only good-first-issue / help-wanted rows"
    )
    review.add_argument("--md", type=Path, help="also write a markdown table to this path")
    review.set_defaults(func=cmd_review)

    labels = sub.add_parser("labels", help="show/create taxonomy labels missing in the repo")
    add_repo(labels)
    labels.add_argument("--create", action="store_true")
    labels.set_defaults(func=cmd_labels)

    apply = sub.add_parser("apply", help="apply proposals with gh issue edit (dry-run by default)")
    add_repo(apply)
    add_proposals(apply)
    apply.add_argument("--yes", action="store_true", help="actually edit issues")
    apply.add_argument(
        "--force", action="store_true", help="also relabel issues labelled since the dump"
    )
    apply.add_argument(
        "--keep-needs-triage", action="store_true", help=f"do not remove `{INTAKE_LABEL}`"
    )
    apply.add_argument(
        "--create-missing-labels", action="store_true", help="create taxonomy labels on the fly"
    )
    apply.set_defaults(func=cmd_apply)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except TriageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
