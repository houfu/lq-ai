# Issue label taxonomy

> **Purpose:** The single reference for how LQ.AI issues are labelled — read by maintainers, by contributors picking work, and by the Sonnet screening agents in [`workflow.js`](workflow.js). If a rule here changes, the agents' behaviour changes with it; nothing is hard-coded in the prompts.
>
> **Scope:** Labels describe *state and shape* of an issue. They do not replace the PRD (which decides what gets built) or the mini-PRDs (which scope contributor work).

---

## Groups and cardinality

| Group | Labels | Cardinality |
|---|---|---|
| Type | `bug` · `enhancement` · `documentation` · `question` · `skill-proposal` · `chore` | exactly one |
| Area | `area:api` · `area:gateway` · `area:web` · `area:word-addin` · `area:desktop` · `area:skills` · `area:docs` · `area:deploy` · `area:ci` · `area:integrations` | one or more (zero only for a pure `question` or a `needs-info` issue) |
| Effort | `effort:S` · `effort:M` · `effort:L` | exactly one |
| Priority | `priority:P0` · `priority:P1` · `priority:P2` · `priority:P3` | exactly one |
| Contributor flags | `good first issue` · `help wanted` | zero or more, each gated by its checklist below |
| State flags | `security` · `needs-info` · `needs-design` · `needs-attorney` · `duplicate` | zero or more |
| Intake | `needs-triage` (set by the issue templates) | removed once the groups above are applied |

The intake labels `needs-redirect` (security-vulnerability template) and `skill-proposal` (skill template) are left as they are; `skill-proposal` doubles as the type label for that template.

---

## Type

- **`bug`** — something that exists does not behave as the PRD, OpenAPI sketch, or its own docstring says. A reproduction or a concrete symptom is present.
- **`enhancement`** — new capability, or a behaviour change to an existing one. Most `DE-XXX` items from PRD §9 land here.
- **`documentation`** — the deliverable is a doc, guide, ADR, mini-PRD, or comment change. If code changes too, prefer the code's type.
- **`question`** — the reporter is asking, not requesting. Usually resolves by an answer, a doc fix (then re-type), or a redirect to Discussions.
- **`skill-proposal`** — a new or changed skill with legal substance (see [`skills/CONTRIBUTING.md`](../../skills/CONTRIBUTING.md)). Always pair with `area:skills`; usually pair with `needs-attorney`.
- **`chore`** — dependency bumps, CI plumbing, refactors with no behaviour change, tooling, repo hygiene.

## Area

Areas mirror the top-level directories. Pick every area whose files a fix would touch.

| Label | Paths |
|---|---|
| `area:api` | `api/**` — FastAPI backend, Alembic migrations, arq/ingest workers |
| `area:gateway` | `gateway/**` — Inference Gateway (the security boundary) |
| `area:web` | `web/**` — the OpenWebUI (SvelteKit) fork |
| `area:word-addin` | `word-addin/**` — Office.js add-in |
| `area:desktop` | `desktop/**` |
| `area:skills` | `skills/**` — skill content and skill tooling |
| `area:docs` | `docs/**`, `README.md`, `CONTRIBUTING.md`, top-level policy docs |
| `area:deploy` | `deploy/**`, `docker-compose*.yml`, `Dockerfile*`, `proxy/**` |
| `area:ci` | `.github/**`, `Makefile`, `ruff.toml`, lint/test plumbing |
| `area:integrations` | `slack-bridge/**`, `teams-bridge/**`, other outbound bridges |

## Effort

Same key as [`docs/contribute/EASIEST-CONTRIBUTIONS.md`](../../docs/contribute/EASIEST-CONTRIBUTIONS.md). Judge from the code, not from the issue's own estimate.

- **`effort:S`** — under a day. One subsystem, the fix location is nameable, tests are straightforward, no migration, no schema or contract change.
- **`effort:M`** — a few days. Touches more than one file cluster or crosses a service boundary (api ↔ gateway ↔ web), needs a migration or an OpenAPI change, or needs a new test fixture.
- **`effort:L`** — more than a week. New subsystem, new data model, multi-PR delivery, or blocked on an undecided design.

## Priority

The maintainer owns priority; the agents propose it so the list is sortable on day one.

- **`priority:P0`** — users are blocked or data/security is at risk: crash-loops, data loss, auth or gateway boundary defects, broken install or upgrade path.
- **`priority:P1`** — next up: user-visible breakage with a workaround, anything gating a roadmap milestone or a mini-PRD, CI red on `main`.
- **`priority:P2`** — normal: enhancements and bugs with no urgency; the default when nothing argues up or down.
- **`priority:P3`** — someday: polish, nice-to-have, speculative ideas, items that depend on work not yet planned.

## Contributor flags

These are the consequential labels. Wrongly inviting an outside contributor onto an issue costs more than a missing label, so both are checklists, not vibes. When one item fails, leave the flag off and say which item in the rationale.

### `good first issue` — all of the following must hold

1. `effort:S`.
2. The scope is clear from the issue itself or from a document it cites (PRD section, DE-XXX entry, mini-PRD). No product or architectural decision is needed.
3. The fix location is nameable: a file, a directory, or a doc section a newcomer can open first.
4. None of the files are security-sensitive per [`.github/CODEOWNERS`](../../.github/CODEOWNERS): not `gateway/**`, not `.github/workflows/**`, not `docs/security/**`, and nothing touching authentication, authorization, audit logging, or cryptography.
5. No legal substance: not a skill's substantive content (that needs a practicing attorney, see `needs-attorney`).
6. Verification is obvious: an existing test pattern to copy, or a documented verification step.
7. Not blocked on another issue or on a decision.

### `help wanted` — all of the following must hold

1. `effort:S` or `effort:M`.
2. Well scoped: a contributor could open a PR without a maintainer conversation first. Every item in `docs/contribute/mini-prds/` qualifies by construction.
3. Does not need deep maintainer context (running acceptance data, provider keys, deployment history).
4. Not flagged `needs-design` or `needs-info`.
5. If the work is legal substance (`area:skills` content), it is still `help wanted` — for a practicing attorney. Record that in `contributor_profile` and pair with `needs-attorney`.

A `good first issue` is normally also `help wanted`. A `help wanted` is often not a `good first issue`.

## State flags

- **`security`** — touches a CODEOWNERS security path or auth/audit/crypto. Routes to security review. Never `good first issue`. A *vulnerability report* filed as an issue is not labelled; it is redirected per [`SECURITY.md`](../../SECURITY.md).
- **`needs-info`** — cannot be acted on as written: no reproduction, no version, unclear ask. Rationale says what is missing. Never `help wanted`.
- **`needs-design`** — a product, architectural, or authorization decision must be made first (CLAUDE.md: "stop on architectural questions"). Rationale names the decision. Never `help wanted` until the decision is recorded (PRD §9 or an ADR).
- **`needs-attorney`** — legal substance that requires practicing-attorney authorship or review before merge (skill content, rubric changes, jurisdictional claims).
- **`duplicate`** — same ask as an earlier open issue. `duplicate_of` in the proposal names the canonical (older) issue. Labelling does not close anything; the maintainer decides.

---

## Reading the board once labels are applied

What should the maintainer work on next:

```bash
gh issue list -R LegalQuants/lq-ai -l priority:P0
gh issue list -R LegalQuants/lq-ai -l priority:P1 -l effort:S
gh issue list -R LegalQuants/lq-ai -l needs-design        # decisions only you can make
```

What to hand to outside contributors:

```bash
gh issue list -R LegalQuants/lq-ai -l "good first issue"
gh issue list -R LegalQuants/lq-ai -l "help wanted" -l area:skills   # attorney contributors
gh issue list -R LegalQuants/lq-ai -l "help wanted" -l effort:M      # engineers with a weekend
```

What is waiting on someone else:

```bash
gh issue list -R LegalQuants/lq-ai -l needs-info
gh issue list -R LegalQuants/lq-ai -l needs-attorney
```

---

*Changing a rule here is a maintainer decision. Update this file, then re-run the workflow on the affected issues; do not edit the prompts in `workflow.js` to special-case a label.*
