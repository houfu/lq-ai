# Issue triage: screen with Sonnet agents, label with a script

> **Purpose:** Get every untriaged issue in `LegalQuants/lq-ai` labelled by type, area, effort and priority, and flag the ones an outside contributor could pick up — without an agent ever writing to GitHub unreviewed.
>
> **Shape:** `gh` dumps the issues → a small Claude Code workflow of Sonnet agents proposes labels → you read the proposals → `gh` applies the ones you keep. Three files matter:
>
> | File | Role |
> |---|---|
> | [`LABELS.md`](LABELS.md) | The taxonomy and the checklists. Agents and humans read the same rules. |
> | [`workflow.js`](workflow.js) | The screening workflow (Claude Code `Workflow` script). Reads `out/issues.json`, writes `out/proposals.json`. |
> | [`triage.py`](triage.py) | `fetch` / `review` / `labels` / `apply`. Standard library only; every GitHub call goes through your own `gh`. |
>
> `out/` is git-ignored (the repo ignores every `out/`), so dumps and proposals never land in a commit by accident.

---

## Prerequisites

- `gh` installed and logged in as an account with **triage** rights on the repo: `gh auth status`.
- `uv` installed (the script declares its own interpreter requirement; no venv to manage).
- Claude Code with the `Workflow` tool (any recent build). The agents run on **Sonnet**; the orchestrating session can be any model.
- Run everything from the **repo root**. The workflow's agents grep the codebase to judge area and effort, so a full checkout matters.

## Step 1 — Dump the open issues

```bash
uv run scripts/issue-triage/triage.py fetch --repo LegalQuants/lq-ai
```

Writes `scripts/issue-triage/out/issues.json` (every open issue with body, comments, labels) and `out/labels.json` (the repo's current labels), then prints the untriaged ones. An issue counts as untriaged when it has **no labels** or still carries the templates' `needs-triage` intake label. Anything else was touched by a human and is left alone.

If the output warns that `--limit` was hit, re-run with `--limit 1000`.

## Step 2 — Run the screening workflow

In a Claude Code session opened at the repo root:

> Run the workflow at `scripts/issue-triage/workflow.js` with args `{"repo": "LegalQuants/lq-ai"}`.

That is a `Workflow({scriptPath: "scripts/issue-triage/workflow.js", args: {...}})` call. Watch progress with `/workflows`. What runs:

| Phase | Agents | What happens |
|---|---|---|
| Scope | 1 | Reads the dump, returns the untriaged list and the repo's existing labels. |
| Screen | 1 per batch of 10 | A Sonnet screener reads each issue's body and comments, greps the code or docs it points at, and proposes labels per `LABELS.md`. Returns a rationale and file pointers per issue. |
| Challenge | at most 1 per batch | Only if that batch proposed `good first issue` or `help wanted`: a Sonnet skeptic tries to refute each flag against the checklist and drops the ones that fail. Runs as soon as its batch is screened; no waiting on other batches. |
| Reconcile | 1 | Sees every proposal together: normalises label names, enforces one-type/one-effort/one-priority, spots duplicates across issues, writes `out/proposals.json`, and returns a short list of items needing your attention. |

For 70 issues that is roughly 1 + 7 + (up to 7) + 1 agents, about 15 minutes of wall clock. Optional args:

| Arg | Default | Use |
|---|---|---|
| `repo` | `LegalQuants/lq-ai` | Recorded in the output file. |
| `batchSize` | `10` | Smaller batches = more, shallower agents. |
| `model` | `sonnet` | Set to another alias for a one-off comparison. |
| `issuesPath` / `outPath` | `scripts/issue-triage/out/...` | Point at a different dump or output. |

The workflow never calls `gh` and never edits an issue. If a screener batch fails, the run continues and the final log names the issue numbers with no proposal; re-run to fill them (completed agents are cached on resume).

**No `Workflow` tool?** Ask the session to do the same by hand: spawn one Sonnet subagent per ten issues with the screener prompt from `workflow.js`, then one with the reconcile prompt. The prompts are plain strings in that file.

## Step 3 — Read the proposals

```bash
uv run scripts/issue-triage/triage.py review              # one line per issue
uv run scripts/issue-triage/triage.py review -v           # plus rationale, pointers, notes
uv run scripts/issue-triage/triage.py review --contributors   # only good-first-issue / help-wanted rows
uv run scripts/issue-triage/triage.py review --md out/proposals.md   # a table you can paste anywhere
```

`review` also validates every proposal against `LABELS.md` and lists violations that would block `apply`. Warnings (no area label, low confidence) are shown but do not block.

To change a call, edit `out/proposals.json` directly: change the `labels` list, or delete the whole entry. Re-run `review` to re-validate. To leave an issue out at apply time without editing, use `--skip`.

## Step 4 — Make sure the labels exist

```bash
uv run scripts/issue-triage/triage.py labels --repo LegalQuants/lq-ai            # report
uv run scripts/issue-triage/triage.py labels --repo LegalQuants/lq-ai --create   # create the missing ones
```

Colours and descriptions come from the taxonomy table in `triage.py` (a mirror of `LABELS.md`). Existing labels are never modified.

## Step 5 — Apply

```bash
uv run scripts/issue-triage/triage.py apply --repo LegalQuants/lq-ai          # dry run: prints the exact plan
uv run scripts/issue-triage/triage.py apply --repo LegalQuants/lq-ai --yes    # edits the issues
```

For each proposal, `apply` re-reads the issue's **live** labels first and then:

- skips it if it is closed;
- skips it if someone labelled it since the dump (pass `--force` to relabel anyway);
- adds only the labels not already present, and removes `needs-triage` (keep it with `--keep-needs-triage`);
- runs one `gh issue edit` per issue and prints `done` / `skip` / `FAILED` per line, then a summary. Exit code is 1 if anything failed.

Useful flags: `--only 12,15,40` to apply a subset, `--skip 33` to hold one back, `--create-missing-labels` to fold Step 4 into this step.

## Step 6 — Use the board

The queries that answer "what next" and "what can I hand out" are at the bottom of [`LABELS.md`](LABELS.md).

## Re-running later

Repeat from Step 1. Because `fetch` only marks unlabelled / `needs-triage` issues as in scope and `apply` re-checks live labels, re-running is safe: previously triaged issues are ignored and new ones are picked up.

## Changing the rules

Edit `LABELS.md` (the rule) and the matching table in `triage.py` (the validator and label colours). The prompts in `workflow.js` refer to the doc rather than restating it, so they rarely need touching. Tests for the script:

```bash
uv run --with pytest pytest scripts/issue-triage/tests
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `gh: ... HTTP 403` on `apply` | Your `gh` account lacks triage rights on the repo. |
| `labels not present in the repo: ...` | Run Step 4, or pass `--create-missing-labels`. |
| `skip (labelled since dump ...)` | Someone triaged the issue after `fetch`. Re-run `fetch`, or `--force`. |
| Workflow log says `no proposal for N issue(s)` | A screener batch failed. Re-run the workflow; cached batches are not re-screened. |
| `review` exits 1 | At least one proposal violates `LABELS.md`; the last lines say which and why. |
