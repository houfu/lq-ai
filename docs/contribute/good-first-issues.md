# Good First Issues

> The shortest on-ramp into LQ.AI. Every item here is **first-PR-sized**: small scope, a clear rubric, and a named place in source to start. Pick one, claim it, ship it.

## Who this is for

You are new to the project (or to open source) and want a contribution you can finish without first absorbing the whole codebase. The items below are deliberately small — a one-line fix, a single function, one doc page, one worked example.

This page exists because [`docs/ROADMAP.md`](../ROADMAP.md) — while complete — is a ~120-row maintainer punch list that interleaves first-PR work with multi-week senior work. It is the wrong front door for a newcomer. This page is the right one: it pre-filters the roadmap down to what a first-time contributor can actually pick up, and tags each item by the skill it needs.

### How this relates to the other lists

| List | Tier | When to use it |
|---|---|---|
| **This page** | First PR — hours, not days | Your first contribution. Small, bounded, clear rubric. |
| [`EASIEST-CONTRIBUTIONS.md`](EASIEST-CONTRIBUTIONS.md) | Bounded weekend project (mini-PRDs) | Your *second* contribution, or if you want a meatier, still-well-defined piece (e.g. OWASP mapping, a procurement pack, a skill acceptance suite). |
| [`docs/ROADMAP.md`](../ROADMAP.md) | The full backlog | Browsing everything that's open, including senior / multi-week work. |

If an item here grows under you, or you hit an architectural fork, **stop and ask on the issue** — that is the project's expected behavior, not a failure (see [`coding-agent-onboarding.md`](coding-agent-onboarding.md)).

## How to claim one

1. Open a GitHub issue using the **Good First Issue** template, with the item's **slug** as the title (e.g. `cypress-response-timeout`). Several items below are pre-written and ready to file as-is.
2. Comment **"I'd like to take this."** A maintainer assigns you within ~7 days.
3. Read the linked source anchor (the `DE-###` entry in [PRD §9](../PRD.md#9-deferred-enhancements-and-identified-future-work) or the ROADMAP row) and the **Where to start** pointer.
4. Submit a PR per [`CONTRIBUTING.md`](../../CONTRIBUTING.md): DCO sign-off (`git commit -s`), imperative-mood commits, the PR template. Reference the issue and DE entry in the body (`Closes #NN`, `Refs DE-255`).
5. For **skill / legal-domain** items (Track D), also follow [`skills/CONTRIBUTING.md`](../../skills/CONTRIBUTING.md) — the practicing-attorney attestation step applies.

Before you start: [`docs/HONEST-STATE.md`](../HONEST-STATE.md) is the truth map of what is shipped vs. deferred. A handful of items below say "verify status before claiming" because a later milestone may already have closed them.

**Anything touching `gateway/`, authentication, authorization, audit logging, or cryptography is _not_ a good first issue** — those paths are security-reviewed per [`.github/CODEOWNERS`](../../.github/CODEOWNERS) and go through a maintainer. They are excluded here on purpose.

---

## Track A — Self-hosting & operator documentation

The headline gap. The stack self-hosts cleanly (`docker compose up`), but a newcomer-to-hosting can't get from "I want to run this on my server" to "I have a secured, production-ready instance" from the docs as they stand: the material is fragmented across `quickstart.md`, the two compose files, an **undocumented** Helm chart, `.env.example`, and `gateway.yaml.example`. These items consolidate it into an operator-facing path.

> **A1 — Epic: Self-hosting & operator documentation** · `area:hosting-docs` · meta
>
> Umbrella tracking issue for A2–A10. Proposes a [Diátaxis](https://diataxis.fr/)-shaped taxonomy for operator docs — **tutorial** (first deploy) → **how-to** (TLS, backups, scaling) → **reference** (env vars, gateway config) → **explanation** (architecture, deployment topologies) — and links the child issues below. No code; this is the coordination home for the track.
> **Acceptance:** the taxonomy is agreed in the thread; A2–A10 are filed and linked as children.

> **A2 — Decision (ADR): adopt a docs-site generator** · `area:hosting-docs`, `documentation` · Docs/DevOps · S–M
>
> Today docs are raw markdown read in GitHub — there is no searchable, polished site (the bar the maintainer wants is OpenWebUI's clean look with docassemble-grade thoroughness). This issue **decides the tool** and records it as `docs/adr/00xx-docs-site-generator.md`; it does **not** stand up the site (that's a follow-on).
> **Options (researched):**
> - **MkDocs + Material** *(recommended)* — markdown-only, one `mkdocs.yml`, built-in client-side search, Python-ecosystem-aligned with the FastAPI backend, polished out of the box. Lowest friction for markdown-native and legal-practitioner contributors. Used by FastAPI, Kubernetes, Pydantic.
> - **Docusaurus** — what OpenWebUI itself uses; React/MDX, heavier build, Algolia (paid) for search parity. Most features, most overhead.
> - **Sphinx** — the "serious docs" default, but reStructuredText friction and a dated default theme; better for Python API autogen than operator guides.
> **Acceptance:** ADR written with the decision + rationale + alternatives; a follow-up "stand up the site" issue is filed referencing the chosen tool. **Architectural fork — do not implement a site before this is decided.**

> **A3 — Operator "Deploy in 20 minutes" tutorial** · `area:hosting-docs`, `documentation` · DevOps/Docs · S
>
> The first genuinely operator-facing tutorial (the existing `quickstart.md` is developer-oriented). Walk someone new to hosting from clone → required secrets in `.env` → `docker compose up` → first admin login → first skill run, framed for an operator, not a developer. Refs **DE-306**.
> **Where to start:** `docs/quickstart.md`, `.env.example` (the 4 required secrets), `docker-compose.yml`.
> **Acceptance:** a reader with Docker but no prior LQ.AI context reaches a working login and one completed skill run by following only this page.

> **A4 — Reverse-proxy + TLS recipes (Caddy / Traefik / nginx)** · `area:hosting-docs`, `good-first-issue` · Junior–mid DevOps · S
>
> Production needs TLS on a public FQDN; today there's only the Tailscale recipe. The mini-PRD is already written — this promotes it to a tracked first issue.
> **Where to start:** [`mini-prds/reverse-proxy-tls-deployment-recipes.md`](mini-prds/reverse-proxy-tls-deployment-recipes.md); **DE-031**; model the structure on `deploy/caddy-tailscale/`.
> **Acceptance:** three drop-in recipes (auto-TLS) under `deploy/reverse-proxy/`, each with a README and OIDC-pass-through notes, verified against the release compose file.

> **A5 — Document the existing Helm chart** · `area:hosting-docs`, `documentation` · DevOps/Docs · S–M
>
> `deploy/helm/lq-ai/` ships a working chart with **zero documentation** — no README, no values walkthrough. Write the operator guide: values, secrets, ingress, persistence, first-install steps. (Production-ready hardening of the chart itself stays a separate, larger DE-030 item.)
> **Where to start:** `deploy/helm/lq-ai/` (`Chart.yaml`, `values-example.yaml`, templates).
> **Acceptance:** `deploy/helm/lq-ai/README.md` takes an operator from a fresh cluster to a running instance; every value in `values-example.yaml` is explained.

> **A6 — Backup & restore runbook** · `area:hosting-docs`, `documentation` · DevOps/Docs · S–M
>
> No documented backup/restore path today. Write a runbook covering `pg_dump`, MinIO snapshot, and a restore drill, in a new `docs/runbooks/`. Refs **DE-033 / DE-249**.
> **Acceptance:** an operator can take a full backup and restore it into a clean stack by following the runbook; restore is verified end-to-end (a restored instance logs in and reads prior data).

> **A7 — Configuration reference page** · `area:hosting-docs`, `documentation` · Docs · S
>
> Consolidate the two annotated examples (`.env.example`, `gateway.yaml.example`) into one searchable reference: every env var, secret, tier, and anonymization setting, with defaults and "required vs optional."
> **Acceptance:** one reference page covers every variable in both example files; nothing is invented beyond what the examples document.

> **A8 — Air-gap (Mode 2) install verification** · `area:hosting-docs`, `good-first-issue` · Mid DevOps · S–M
>
> Mode 2 (Ollama, fully offline) claims "no outbound calls" but nothing proves it. The mini-PRD is scoped — promote it.
> **Where to start:** [`mini-prds/air-gap-install-verification.md`](mini-prds/air-gap-install-verification.md); **DE-032**.
> **Acceptance:** a sealed-network CI test proves the stack stands up with no internet egress.

> **A9 — Quickstart host-port collision callout** · `area:hosting-docs`, `good-first-issue` · Docs · S
>
> Fresh installs hit host-port collisions with no guidance. Add a prominent callout to the quickstart. A genuine first issue. Refs **DE-306**.
> **Where to start:** `docs/quickstart.md`; port bindings in `docker-compose.yml`.
> **Acceptance:** the quickstart names the colliding ports and how to remap them.

> **A10 — Compose env-var `${VAR:?}` fix** · `area:hosting-docs`, `good-first-issue` · DevOps · S
>
> Bridge env vars use `${VAR:?}`, which breaks *all* Compose commands when those vars are unset — even for operators not using the bridges. One-line fix from M3 acceptance. Refs **DE-305**.
> **Where to start:** the `slack-bridge` / `teams-bridge` service definitions in `docker-compose.yml`.
> **Acceptance:** `docker compose` commands succeed with bridge vars unset; bridges still fail loudly only when actually enabled.

---

## Track B — Junior code first-PRs

Small, single-surface code changes pulled from the 🟢-Low / Junior rows of the roadmap. Each issue body must carry the relevant **test-suite collision guards** from [`CLAUDE.md`](../../CLAUDE.md) (e.g. a new route → add to `IMPLEMENTED_ROUTES` *and* bump the path count + `EXPECTED_PATHS` in `api/tests/test_openapi.py`; a `204` endpoint → use the `response_class=Response` recipe). Run `ruff format` **and** `ruff check`, and the relevant `pytest` paths, before opening the PR.

### Frontend (SvelteKit)

| Slug | Item | Source | Notes |
|---|---|---|---|
| `cypress-response-timeout` | Add `responseTimeout: 90000` to `cypress.config.ts` | DE-255 | Single-line config change. The canonical "your very first PR." |
| `errorfor-string-detail` | `api/client.ts` `errorFor` swallows string-shaped FastAPI `detail` bodies | DE-261 | Single-function fix; add a unit test for the string-detail path. |
| `aliasform-model-autocomplete` | Admin AliasForm model-dropdown autocomplete population | DE-272 | One-prop wiring fix called out in HONEST-STATE §1. |
| `cypress-support-helpers` | Extract Cypress shared helpers to `support/` | DE-254 | Mechanical refactor finding from M1 wave-D2. |
| `kb-attach-interceptor` | Add KB-attach interceptor to `wave-m1-final-surfaces.cy.ts` Test 2 | DE-256 | Test-reliability patch. |
| `tabular-builtins-browser-polish` | Tabular built-ins browser polish on `/skills` | DE-298 | UI polish so table skills are discoverable. |
| `enhance-prompt-reasoning-toggle` | Reasoning-visibility toggle for Enhance Prompt | DE-011 | Toggle + small UI surface. |

### Backend (FastAPI / Python)

| Slug | Item | Source | Notes |
|---|---|---|---|
| `log-trace-correlation` | Inject `trace_id` / `span_id` into structured log records | DE-300 | Adds the IDs to every log record; high-leverage, low-risk. |
| `skill-author-wire-shape` | Promote skill `author` to the `Skill` / `SkillSummary` wire shape | DE-316 | Wire-shape addition. |
| `tabular-skill-id-span` | Tabular `skill_id` span-attribute linkage | DE-314 | Span-attribute fix. |
| `playbook-position-spans` | `playbook.position` child spans on the redline node | DE-318 | Adds a missing child span. |
| `tabular-results-openapi-schema` | Formalize the Tabular `results` OpenAPI schema (typed cell/citation components) | DE-330 | Type the `source_file_id` / `source_page` / `source_text` fields from #125. |
| `api-tests-mypy` | Bring `api/tests/` into mypy | DE-284 | Typecheck-coverage tightening. |
| `audit-health-endpoint` | `/api/v1/audit-health` endpoint for the AmbientFooter signal | DE-257 | Endpoint + footer wiring. *Mind the route collision guards.* |
| `kb-embedding-progress` | KB embedding-progress percentage aggregation | DE-258 | Aggregation endpoint. |
| `kb-attached-matters-lookup` | KB attached-matters reverse-lookup | DE-259 | Reverse-lookup endpoint. |
| `receipts-skill-event-dedup` | Receipts assistant-side skill-event deduplication | DE-260 | Dedup pass. |
| `audit-log-actor-enrichment` | Audit-log API server-side actor enrichment | DE-273 | Server-side enrichment fix. |
| `file-count-fields` | `File` API `page_count` / `character_count` (populate or remove) | DE-307 | Either populate the fields or drop them from the schema. |
| `dedup-storage-failure-findings` | Dedupe correlated artifact storage-failure warn findings | DE-333 | Collapse correlated findings so one MinIO outage doesn't flood a session. |

> **Verify-before-claiming:** **DE-283** (fresh-install login UX: surface the bootstrap-password path on first 401) and **DE-265** (in-app "unverified citation" badging) are listed as 🟢/Junior on the roadmap but flagged "verify status" — a later milestone may have closed them. Check `docs/HONEST-STATE.md` and source before claiming.
>
> **Excluded (security-reviewed):** DE-315 and DE-317 are also small but live in `gateway/` — they go through a maintainer, not this list.

---

## Track C — Docs & quality

| Slug | Item | Source | Skill / Effort |
|---|---|---|---|
| `test-strategy-coverage-matrix` | Write `docs/test-strategy.md` (per-surface E2E coverage matrix) | ROADMAP §4.1 (M1 deliverable still open) | Docs/Mid · S |
| `coverage-gate-ci` | Add the coverage-threshold gate in CI (80% api / 90% gateway) | ROADMAP §4.3 | DevOps · S |
| `error-budget-policy` | Error-budget policy doc | DE-246 | Docs/DevOps · S |
| `public-postmortem-template` | Public-postmortem template + commitment | DE-247 | Docs · S |
| `dr-test-cadence` | Disaster-recovery test-cadence doc | DE-248 | Docs/DevOps · S |

---

## Track D — Legal-domain & skills

These follow the higher-bar skill path in [`skills/CONTRIBUTING.md`](../../skills/CONTRIBUTING.md): claim → draft → **practicing-attorney attestation** → review → merge. They are still newcomer-accessible for someone with the relevant legal background.

| Slug | Item | Source | Skill / Effort |
|---|---|---|---|
| `dpa-worked-examples` | Additional worked examples for DPA Checklist Review | DE-003 | Legal-domain · S |
| `easy-playbook-sample-nda-kb` | First-run sample-NDA knowledge base for the Easy Playbook wizard | DE-285 | Backend + Legal-domain · S |
| `dpa-regime-<code>` | Additional DPA regime (one per issue: PDPA, LGPD, PIPL, …) | DE-002 | Legal-domain · M |

For meatier legal/compliance work, see the existing mini-PRDs in [`EASIEST-CONTRIBUTIONS.md`](EASIEST-CONTRIBUTIONS.md): Procurement-Readiness Pack (§3.1), skill acceptance tests (§3.3), and NIST AI RMF mapping (§3.6). They are not duplicated here.

---

## Maintenance note

This list is curated. Items leave when they ship; items join when a roadmap row turns out to be genuinely first-PR-sized. If you think something on [`docs/ROADMAP.md`](../ROADMAP.md) belongs here, open an issue and say so.

*Maintained alongside the ROADMAP and the mini-PRD list. The source documents win on any disagreement.*
