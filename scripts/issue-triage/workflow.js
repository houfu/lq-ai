// Sonnet screening workflow for the LQ.AI issue tracker.
//
// Runs inside Claude Code's Workflow tool. From the repo root, after
// `uv run scripts/issue-triage/triage.py fetch` has written out/issues.json:
//
//     Workflow({ scriptPath: "scripts/issue-triage/workflow.js",
//                args: { repo: "LegalQuants/lq-ai" } })
//
// (In chat: "run the workflow at scripts/issue-triage/workflow.js".)
//
// Shape — small on purpose:
//   Scope      1 agent    reads the dump, lists the untriaged issues
//   Screen     1/batch    a Sonnet screener proposes labels for ~10 issues
//   Challenge  ≤1/batch   a Sonnet skeptic re-checks any good-first-issue /
//                         help-wanted call in that batch (skipped when none)
//   Reconcile  1 agent    normalises across batches, writes out/proposals.json
//
// Nothing here touches GitHub. `triage.py review` / `apply` do that, with a
// human in between. Every rule the agents follow lives in LABELS.md.

export const meta = {
  name: 'issue-triage',
  description: 'Screen untriaged LQ.AI issues with Sonnet agents and propose labels for maintainer review',
  whenToUse: 'After `triage.py fetch` has written scripts/issue-triage/out/issues.json; writes out/proposals.json for `triage.py review` and `triage.py apply`.',
  phases: [
    { title: 'Scope', detail: 'read the issue dump; list untriaged issues', model: 'sonnet' },
    { title: 'Screen', detail: 'one Sonnet screener per batch proposes labels', model: 'sonnet' },
    { title: 'Challenge', detail: 'a skeptic re-checks good-first-issue / help-wanted calls', model: 'sonnet' },
    { title: 'Reconcile', detail: 'normalise across batches; write proposals.json', model: 'sonnet' },
  ],
}

const cfg = Object.assign(
  {
    repo: 'LegalQuants/lq-ai',
    issuesPath: 'scripts/issue-triage/out/issues.json',
    labelsPath: 'scripts/issue-triage/out/labels.json',
    outPath: 'scripts/issue-triage/out/proposals.json',
    labelsDoc: 'scripts/issue-triage/LABELS.md',
    batchSize: 10,
    model: 'sonnet',
  },
  args || {},
)

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const SCOPE_SCHEMA = {
  type: 'object',
  properties: {
    total_open: { type: 'integer' },
    in_scope: {
      type: 'array',
      items: {
        type: 'object',
        properties: { number: { type: 'integer' }, title: { type: 'string' } },
        required: ['number', 'title'],
      },
    },
    existing_labels: { type: 'array', items: { type: 'string' } },
  },
  required: ['total_open', 'in_scope', 'existing_labels'],
}

const PROPOSAL_SCHEMA = {
  type: 'object',
  properties: {
    number: { type: 'integer' },
    title: { type: 'string' },
    labels: { type: 'array', items: { type: 'string' } },
    remove: { type: 'array', items: { type: 'string' } },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    rationale: { type: 'string' },
    contributor_profile: { type: 'string' },
    pointers: { type: 'array', items: { type: 'string' } },
    duplicate_of: { type: 'integer' },
    notes_for_maintainer: { type: 'string' },
  },
  required: ['number', 'title', 'labels', 'confidence', 'rationale'],
}

const BATCH_SCHEMA = {
  type: 'object',
  properties: { proposals: { type: 'array', items: PROPOSAL_SCHEMA } },
  required: ['proposals'],
}

const RECONCILE_SCHEMA = {
  type: 'object',
  properties: {
    written_to: { type: 'string' },
    counts: {
      type: 'object',
      properties: {
        proposals: { type: 'integer' },
        good_first_issue: { type: 'integer' },
        help_wanted: { type: 'integer' },
        needs_design: { type: 'integer' },
        needs_info: { type: 'integer' },
        low_confidence: { type: 'integer' },
      },
      required: ['proposals', 'good_first_issue', 'help_wanted'],
    },
    new_labels: { type: 'array', items: { type: 'string' } },
    changes_made: { type: 'array', items: { type: 'string' } },
    maintainer_attention: { type: 'array', items: { type: 'string' } },
  },
  required: ['written_to', 'counts', 'new_labels', 'changes_made', 'maintainer_attention'],
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

const GUARDRAILS = `Ground rules: do not modify any file except where this prompt says so; do not call gh or fetch anything from the network; everything you need is in the repo checkout and the dump. Work from the repo root.`

const scopePrompt = () => `You are the scoping step of the LQ.AI issue-triage workflow. ${GUARDRAILS}

1. Read ${cfg.issuesPath}. It is JSON of the form {"repo", "counts", "issues": [...]} written by scripts/issue-triage/triage.py. Each issue carries "in_scope" (bool) and "scope_reason".
2. Read ${cfg.labelsPath} if it exists: a JSON list of the repo's current labels ({"name", ...}).

Use a short python3 one-liner for both files rather than paging the whole dump into your context.

Return: total_open = number of issues in the dump; in_scope = every issue whose in_scope is true, as {number, title}, sorted by number ascending; existing_labels = the label names from the labels file (empty list if it is missing).`

const screenPrompt = (batch) => `You are a triage screener for the LQ.AI issue tracker (${cfg.repo}). You PROPOSE labels; a maintainer reviews and applies them later with a script. ${GUARDRAILS}

Your batch: issues ${batch.map((i) => `#${i.number}`).join(', ')}.

Step 1 — Read the taxonomy and decision rules in ${cfg.labelsDoc} in full. They are the contract: exactly one type label, one or more area labels, exactly one effort label, exactly one priority label, and a flag only when its checklist holds. Use the exact label names from that file.

Step 2 — For each issue in your batch, pull the full record out of ${cfg.issuesPath} with a python3 snippet (the file is {"issues": [...]}; match on "number"). Read the whole body and every comment; comments often narrow, supersede, or answer the original ask. Note the issue's current labels ("label_names").

Step 3 — Ground every call in the repo before deciding:
- Locate the code or docs the issue is about: grep the directory the area label points at, read the relevant file heads. If the issue cites a PRD section, a DE-XXX entry, or a mini-PRD, read that entry (docs/PRD.md, docs/contribute/mini-prds/, docs/contribute/EASIEST-CONTRIBUTIONS.md).
- Judge effort from what the code shows, not from the reporter's estimate. Judge priority by the rules in the doc.
- \`good first issue\` and \`help wanted\` are the consequential calls. Walk their checklists item by item. If any item fails, leave the flag off and name the failing item in the rationale.
- Security-sensitive paths (.github/CODEOWNERS: gateway/**, .github/workflows/**, docs/security/**, anything auth/audit/crypto) get the \`security\` flag and never \`good first issue\`.
- Fill \`pointers\` with the files or doc sections a contributor would open first (1–4 entries).

Step 4 — Return one proposal per issue in your batch: all ${batch.length} of them, including low-confidence ones. Set \`remove\` to ["needs-triage"] when the issue currently carries it. Keep \`rationale\` to 1–3 sentences a maintainer can check in ten seconds. Set \`duplicate_of\` only when the same ask exists in another issue in the dump (you may grep titles across the dump); point at the older issue and add the \`duplicate\` flag. Use \`notes_for_maintainer\` for open questions, missing information, or a decision only the maintainer can make.`

const challengePrompt = (flagged) => `You are the skeptic in the LQ.AI issue-triage workflow. A screener proposed \`good first issue\` and/or \`help wanted\` for the issues below. Try to REFUTE each flag against the checklists in ${cfg.labelsDoc}; inviting an outside contributor onto the wrong issue costs more than a missing label. ${GUARDRAILS}

For each proposal: re-read the issue record from ${cfg.issuesPath} (python3 snippet, match on "number"), open the files or doc sections named in \`pointers\`, and check every checklist item for each flag. Sanity-check the type, area, and effort labels while you are there.

Return ALL the proposals you were given, in the same schema, with your corrections applied:
- Keep a flag only if every checklist item holds. Otherwise drop it and prepend one sentence to \`notes_for_maintainer\` starting with "Challenger:" naming the failing item.
- If effort or area is wrong, fix it and note that the same way.
- Leave proposals you agree with byte-for-byte unchanged.

Proposals to challenge:
${JSON.stringify(flagged, null, 2)}`

const reconcilePrompt = (all, existing) => `You are the reconcile step of the LQ.AI issue-triage workflow. You receive every proposal from the screening batches (already challenged) and produce the final file a maintainer will review. ${GUARDRAILS.replace('do not modify any file except where this prompt says so', 'the only file you may write is ' + cfg.outPath)}

1. Read ${cfg.labelsDoc}. Normalise every label to the exact names there; drop anything outside the taxonomy and record it in changes_made.
2. Enforce cardinality: exactly one type, one effort, one priority per issue; at least one area unless the issue is a pure \`question\` or carries \`needs-info\`. Fix inconsistencies across batches (two near-identical asks with different effort or priority, for example) and record each change.
3. Cross-issue checks: overlapping asks → set duplicate_of on the newer issue pointing at the older one and add the \`duplicate\` flag. Do not propose closing anything.
4. Keep \`good first issue\` only where effort:S holds and none of security / needs-design / needs-attorney / needs-info is present. Keep \`help wanted\` off anything flagged needs-design or needs-info and off effort:L.
5. Write ${cfg.outPath} as a JSON object:
   {"repo": "${cfg.repo}", "generated_from": "${cfg.issuesPath}", "workflow": "scripts/issue-triage/workflow.js", "proposals": [...]}
   with proposals sorted by number ascending, 2-space indentation, trailing newline. Then run
   python3 -c "import json; d=json.load(open('${cfg.outPath}')); print(len(d['proposals']))"
   to confirm it parses.
6. Return: counts; new_labels = taxonomy labels you used that are NOT already in the repo (existing labels: ${JSON.stringify(existing)}); changes_made; and up to 15 short maintainer_attention lines — needs-design and needs-info items, duplicates, and any P0/P1 call with confidence below high.

Proposals:
${JSON.stringify(all)}`

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

const isContributorFlag = (l) => l === 'good first issue' || l === 'help wanted'

phase('Scope')
const scope = await agent(scopePrompt(), {
  label: 'scope',
  phase: 'Scope',
  schema: SCOPE_SCHEMA,
  model: cfg.model,
  effort: 'low',
})
if (!scope) throw new Error(`scope agent failed — does ${cfg.issuesPath} exist? run triage.py fetch first`)

const items = scope.in_scope
log(`${items.length} of ${scope.total_open} open issues are untriaged`)
if (!items.length) return { untriaged: 0, message: 'nothing to triage' }

const batches = []
for (let i = 0; i < items.length; i += cfg.batchSize) batches.push(items.slice(i, i + cfg.batchSize))
log(`${batches.length} batch(es) of up to ${cfg.batchSize}; model ${cfg.model}`)

const screened = await pipeline(
  batches,
  (batch, _item, idx) =>
    agent(screenPrompt(batch), {
      label: `screen:${idx + 1}`,
      phase: 'Screen',
      schema: BATCH_SCHEMA,
      model: cfg.model,
    }),
  async (result, batch, idx) => {
    if (!result) {
      log(`batch ${idx + 1}: screener failed; ${batch.length} issue(s) will have no proposal`)
      return []
    }
    const proposals = result.proposals
    const flagged = proposals.filter((p) => p.labels.some(isContributorFlag))
    if (!flagged.length) return proposals
    const verdict = await agent(challengePrompt(flagged), {
      label: `challenge:${idx + 1}`,
      phase: 'Challenge',
      schema: BATCH_SCHEMA,
      model: cfg.model,
    })
    if (!verdict) {
      log(`batch ${idx + 1}: challenger failed; keeping ${flagged.length} contributor flag(s) unverified`)
      return proposals
    }
    const corrected = new Map(verdict.proposals.map((p) => [p.number, p]))
    return proposals.map((p) => corrected.get(p.number) || p)
  },
)

const all = screened.filter(Boolean).flat()
const covered = new Set(all.map((p) => p.number))
const missing = items.filter((i) => !covered.has(i.number)).map((i) => i.number)
if (missing.length) log(`WARNING: no proposal for ${missing.length} issue(s): ${missing.join(', ')} — re-run to fill them`)

phase('Reconcile')
const final = await agent(reconcilePrompt(all, scope.existing_labels), {
  label: 'reconcile',
  phase: 'Reconcile',
  schema: RECONCILE_SCHEMA,
  model: cfg.model,
})
if (!final) throw new Error('reconcile agent failed; proposals were not written')

log(`wrote ${final.written_to}: ${final.counts.proposals} proposals, ${final.counts.good_first_issue} good first issue, ${final.counts.help_wanted} help wanted`)
return {
  untriaged: items.length,
  batches: batches.length,
  missing,
  ...final,
  next: `uv run scripts/issue-triage/triage.py review`,
}
