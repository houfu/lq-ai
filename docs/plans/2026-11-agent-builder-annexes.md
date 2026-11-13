# Agent builder: annexes

**Status:** Draft 18. **Date:** 2026-11-13. Changes since draft 4 are listed in annex J. Nothing here is built. No ADR is adopted. Code facts are read, not run, except two probes named in annex H; a few are reported from private notes (annex H).
Reference detail for [the plan](2026-11-agent-builder.md). All sizes, days and dates are estimates.

- [A. File format v1](#a-file-format-v1)
- [B. How a turn is built, and what is recorded](#b-how-a-turn-is-built-and-what-is-recorded)
- [C. Slices for Stages 2 to 4, the history tool and contributed agents](#c-slices-for-stages-2-to-4-the-history-tool-and-contributed-agents)
- [D. Sub-agents trial specification](#d-sub-agents-trial-specification)
- [E. Governance path](#e-governance-path)
- [F. Engines and what stays frozen](#f-engines-and-what-stays-frozen)
- [G. Why earlier attempts stalled](#g-why-earlier-attempts-stalled)
- [H. Sources](#h-sources)
- [I. Slots, stages, dates and this week](#i-slots-stages-dates-and-this-week)
- [J. Changes since draft 4](#j-changes-since-draft-4)
- [K. Glossary](#k-glossary)
- [L. Decided in this draft](#l-decided-in-this-draft)
- [M. The main plan's fuller text](#m-the-main-plans-fuller-text)

## A. File format v1

Markdown with YAML frontmatter. The body is the instructions, as in `SKILL.md` and the Claude Code subagent file.

### A1. What the Stages 1–3 ADR ratifies

The ADR ratifies **only the fields in this table**. Nothing else.

| Field | Values | If absent | Live from | Claude Code |
|---|---|---|---|---|
| `schema` (required) | `1` | refused | Stage 1 | none; written on export under one namespaced key |
| `name` (required) | slug (A3, point 1) | refused | 1 | `name` |
| `description` (required) | when to use this agent | refused | 1 | `description` |
| body | instructions, at most 32 KB; may be empty. Sent as the agent's section of the system prompt (B) | no agent section | 1 | body |
| `title`, `metadata` | display name; string map | `title` = `name` | 1 | lossy; unmapped import fields land in `metadata` |
| `author` | Not a version 1 field (API R43). A file may say who wrote it under `metadata`. The server labels an agent from where it loaded it | an unknown field (A3, point 17) | never | not checked |
| `model` | a gateway alias, or `provider/model`; contributed files use aliases only. The sender may pick another model for one turn; the check then runs against that one | the model sent with the message. On an agent turn that is optional and has no default: absent means the file's model, or today's default if the file names none (API R33) | 1 | `model`; names differ, so import asks |
| `skills` | the list the model may load from: slugs, or `{name, optional}` | no list and no `load_skill` tool | 1 | `skills`; there they are preloaded, so the meaning differs and import says so |
| `knowledge` | what `search_knowledge` may search: `none`; or a list of `matter`, a name, or `{name, optional}` | `[matter]` | `matter`/`none` from 1; names from 2 | none; lossy |
| `tools` (required) | `chat`; `none`; or a list of selectors (A2) | refused | `chat` from 1; the rest from 3 | `tools`; `connector:x` ↔ `mcp__x__*`; other names do not map |
| `limits` | `max_tool_calls`. On an agent turn this is a limit on rounds, and may only lower the operator's number. The field's name is not ruled | operator's limit (20 rounds by default) | 1 in the build plan (slice 1p); the stage is not ruled | `maxTurns`, roughly |

**Reserved names.** Refused at save, with the reason, until their own decisions:

| Name | Waits for |
|---|---|
| `history` | Slice H1 and its cover rule (C) |
| `workspace` | The Stage 4 decision (an amendment to ADR 0035 D8b) |
| `subagents`, `use_as`, `limits.max_subagents`, `limits.max_subagent_tool_calls`, `limits.max_result_chars` | The sub-agents ADR |
| `always` on a `skills` item | No plan. See A4 |
| `memory`, `permissions` | No plan. The `memory` refusal points to `workspace` and `history` |

The plan uses `history: chat`, `workspace: own` and `subagents: [name@version]` as working spellings. The ADR does not ratify them.

Draft 3 reserved a separate field for skills the model chooses. It is gone: `skills` now means exactly that.

### A2. The `tools` selectors

| Selector | Means | Kind in code |
|---|---|---|
| `research` | The built-in case-law research tools | `research` |
| `authority` | The search-and-get pair over every authority source the operator has enabled (statutes, regulations, filings) | `authority` |
| `connector:<server>` | Every enabled tool of one connector the operator installed | `mcp` |
| `connector:<server>/<tool>` | One tool of one connector | `mcp` |

**Decision in this draft:** `authority` is one selector. Draft 2's `authority:<source>` is dropped. In code one pair of tools covers all enabled sources, and the model picks the source by argument (`api/app/chat/tool_schemas.py:266-300`). Narrowing to one source would need the schema rebuilt and a refusal at dispatch. That can be added later without a `schema` change.

- `chat` means "what ordinary chat offers here". It changes when the operator changes it. The turn's record shows what was offered. It is deployment-wide, not per user.
- `chat` and `none` stand alone. They cannot be combined with a list.
- A list is the exact set. `tools: [connector:docstore]` switches research and authority off.
- A list item may be `{name: connector:docstore, optional: true}`.
- **Some tools come with their own field, whatever `tools` says.** `load_skill` comes with a non-empty `skills` list. `search_knowledge` comes with `knowledge`, unless it is `none`. Later, `search_history` comes with `history` and the workspace tools with `workspace`. A skill's own tools arrive when the model loads that skill.
- So `tools: none` means "none beyond those". An agent offers no tool at all only with no `skills`, `knowledge: none`, and a `tools` line that resolves to nothing here. Only that agent's turns skip the loop and stream, as chat does today.

### A3. The seventeen points a first-time builder had to guess

1. **`name`.** Lowercase letters, digits and hyphens; starts with a letter; at most 64 characters. Saving a name the owner already has makes the next version of that agent. Identical text reuses its version. A chat using the agent stays on the version it was given; saving a newer one does not move it. The user moves the chat by editing it. `title` defaults to `name`.
2. **`model`: where the aliases are.** The chat's model picker lists them. From slice 1m-6 the agent page shows each one's tier. The stock example configuration has `smart`, `fast`, `budget` (tier 4) and `local`, `local-fast`, `local-thinking` (tier 1).
3. **`skills`: how a name resolves.** As in chat today: the user's own, then the team's, then built-in. The API resolves that order; the gateway asks it for each name, and renders the list the same way. Skills are not pinned to a version; the per-turn record carries each loaded skill's fingerprint. **Declare no inputs:** `contract-snapshot`, `msa-snapshot`, `nda-snapshot` (each needs tier 2 or stronger), `skill-creator`, and two demonstration skills, `saved-notes-demo` and `orchestration-chat-demo`; plus any of the user's own skills with no inputs. The other 11 built-in skills can be listed too, since 12 November: missing required inputs no longer refuse a skill, in any chat.
4. **`knowledge`: forms.** `none` is a bare word, never a list item. Otherwise a list. A named item may be a bare string or `{name, optional}`. `matter` cannot be optional and never fails. Today `matter` means the knowledge bases attached to the matter *and* owned by the chat's owner. In a chat outside a matter there is nothing to search: the tool is not offered, and a line says so.
5. **Which selector is case law.** `research`. See A2.
6. **Where a builder learns a connector's name before slice 3b.** From the operator. A sign-in status endpoint exists; no settings page lists connectors yet.
7. **`tools` details.** Resolved in A2. The one detail left, item (c) under "To settle", was settled on 12 November.
8. **Workspace tool names.** Reserved. The intent: three tools, list, read and write, modelled on today's skill workspace tools, which come with `workspace`, independent of `tools`. The Stage 4 slices fix the names and print them on the agent page.
9. **Workspace outside a matter, or for a matter member who is not the owner.** Reserved. The intent: "Not available: needs a matter", and today's owner-only rule kept. The Stage 4 decision settles both.
10. **Can `workspace` be optional?** Reserved. The intent is yes, so an agent runs where the operator has workspaces off.
11. **`limits` above the operator's limit.** Clamped at send, never refused: the file may lower the rounds limit, never raise it. The record and the agent page say so. Save cannot know another deployment's cap. Ruled 13 November (API R82): where the operator has set a spend limit, a turn whose model is on a paid route with no price configured is refused at the check, in a 409 item that names the model. With no limit set it runs, bounded by rounds, and the record says "unpriced". Local models count as priced at zero.
12. **Empty body.** Valid. Such an agent is a named set-up of model, skills and knowledge. The system prompt has no agent section.
13. **`memory`.** Refused, with "for notes the agent keeps, see `workspace`; for earlier messages of this chat, see `history`".
14. **Comments.** Allowed and kept. They are part of the text, so of the fingerprint. Changing a comment makes a new version.
15. **`schema: 1` on an older deployment.** A field that the deployment does not support yet is refused at save, with the field and the LQ.AI version that supports it. `optional` does not help there; see "To settle", item (a). The plan's example is now a Stage 1 file, so it saves on every deployment that has agents. A contributed agent's README states the minimum LQ.AI version.
16. **`name@version` across stores.** Reserved. Version numbers belong to each owner's store, so a pasted reference means nothing to the receiver. The sub-agents ADR must decide; a reference by name with a fingerprint is the likely form.
17. **Unknown fields against `version`.** One rule: an unknown field is refused. `version` is a known field that the store assigns. In a pasted file it is ignored with a notice. It is not in the stored text or the fingerprint. Files in the repo carry `version` because they have no store. The built-in default agent is one of them.

### A4. Other rules

- **`skills` is the list the model may load from.** The system prompt shows each one's name and description. The model calls `load_skill` with a name from the list; any other name is refused as a tool error it can read. A loaded skill contributes its written body. A table-mode skill's column definitions and per-cell citations belong to the tabular page and are not used in chat.
- **No skill is always loaded in v1.** `always` is reserved. If the model proves unreliable at loading (risk 2 in the plan), it is the first thing to add. Until then the instructions can say "load X first", as the example does.
- **A skill the user attaches by hand** still loads in full on every turn, as today, on an agent chat too: the `skills` field, `attached_skills` by slug, the sticky set and the leading slash all work beside the agent's list. Listed, hand-attached and kept skills together are at most 16. Inline skill text is refused on an agent chat: it is unsaved text with no fingerprint for the record.
- **`history`, as intended.** `chat` or `none`; absent means `none`. `chat` covers this chat's messages that no longer fit in the request. Reserved until H1.
- **`knowledge` is the exact set the tool may search.** Naming one attached to the matter narrows. The file holds a name, never an id. The name is matched exactly against the reader's own knowledge bases; the matched id goes in the record. No match, or more than one, is "not found": choose, or run without. No uniqueness rule on knowledge-base names was found. A real per-user binding needs a second table and is not in v1.
- **Fingerprint.** SHA-256 of the text as saved, line endings normalised. Keys are not reordered.
- **Versions and deletion.** A saved version is never edited. Deleting an agent is the owner's explicit act. Ruled 13 November: a version that ran in a matter cannot be deleted while the matter is open. Its owner can retire it: it leaves the lists and no new chat can use it. Deleting removes the text of every version from the store, and keeps the agent's name and the fact that it was deleted, so old replies still show who answered. A chat that points at a deleted agent returns to the default agent, and says so. Ruled 13 November (API R68): a paused turn resumes on the version it started with even if that version has since been retired or deleted. Its saved state carries the instructions it needs, and deletion of the text takes effect when the turn ends. Ruled 13 November (API R74, V24): a paused turn that runs out ends as a failed turn, with a reply saying the approval ran out and a record; deletion of the text takes effect then. Ruled 13 November (V27, API R78): a try in the builder does not count as running in a matter, so a version used only in "Try it" can be deleted while the matter is open. Deleting a version deletes the hidden try chats that ran it; their audit rows stay and keep the agent's name. Audit records keep the agent's id, version number, fingerprint and the list of what was used. "View file" from such a record then reads "deleted by its owner". Until deletion, every version that ran can be read.
- `schema` rises only on a breaking change.

### A5. To settle in slice 1d

(a) Whether a not-yet-supported field marked `optional` may save with a notice, so one file works on old and new deployments.
(b) The validator's two modes, store and repo (point 17). The ADR lists them.
(c) Settled 12 November: agent turns count rounds, so a load and a call to a skill's own tool are ordinary rounds.
(d) Settled 13 November: no. It can be retired (A4).
(e) Settled 12 November: a loaded skill lasts for the turn only.

## B. How a turn is built, and what is recorded

### B1. Today, and what changes

Read, not run; file and line are in H. Today chat has no LQ.AI system prompt. The server fetches knowledge before the model is asked and sends it, and any attached files, as system messages. With a skill attached, the gateway merges every attached skill in full and puts the joined system messages after them under one heading, "Operator system instructions"; with no skill it does not assemble at all. History is the most recent messages that fit 64,000 tokens and 20 messages; older ones are dropped, not summarised. The tool loop runs only when a tool is offered.

Since 12 November three things change for every chat, agent or not. The LQ.AI system prompt is added, so assembly runs even with no skill. Missing required inputs no longer refuse a skill. A tool-loop turn's tokens and cost are summed over its rounds on the message row; today that row gets a null cost and the last round's tokens only. The last two are PRs of their own, outside the agent slices. On an install with agents off, the rest stays as described above. On an install with agents on, every chat has an agent, and one with none chosen runs the default agent. Ruled 13 November (ADR R21, R25, R26): this split lasts until the release after Stage 1, which turns agents on for every install and removes the setting and the old chat path together (annex E, decisions 11 and 14).

### B2. The system prompt

The gateway builds one system message. Part 1 is for every chat. Parts 3 and 4 are for agent turns only. Part 5 is also where a skill attached by hand goes in ordinary chat. Each part has its own heading:

1. **The LQ.AI system prompt.** A file in the repo, with a version. Its words are the maintainer's. Its path, and how it reaches the gateway image, are settled in slice 1b.
2. **Operator instructions**, under today's heading. Left out when empty. This plan found no setting for an operator-written chat prompt in `api/app/config.py`; if one is added, it goes here, and users can read its text (ADR ruling R8). Ruled 12 November in the interface discussion: people can read the operator's instructions and the Organization Profile in the interface, and an admin setting to hide them may be filed as a deferred enhancement. That discussion describes operator instructions as an existing operator-side setting, which this annex did not find. Not reconciled.
3. **The agent's instructions**, with one fixed line saying a user wrote them and that they do not override the parts above. Ruled 12 November: the label comes from the server's own knowledge of where it loaded the agent. It says "built in to LQ.AI" for agents shipped in the repo and "written by a user of this deployment" for saved ones. Built-in instructions sit in the same section under the same limits. The exact label text is proposed in slice 1a-2 and approved in review (API R44).
4. **The skills list.** For each allowed skill: its name and description, and one line on how to load it.
5. **Loaded skills**, in full, rendered as skills are today. The Organization Profile keeps its place at the head of them, under today's rule.

On agent turns whose agent can search knowledge, the citing rule is a sixth part of its own, kind `citing_rule`, with a version and a fingerprint; an agent with `knowledge: none` has none (API R62, R76, R80; annex B4). One exception: while the default agent ships `knowledge: none` and keeps the server fetch (API R64), its citing rule stays where it is today, in the header of the server-fetched block. Its place among these parts was answered twice on 13 November: last, after loaded skills (API R76), and straight after the LQ.AI prompt, before operator instructions (ADR R29). Not reconciled (open question 39).

What slices 1a-1, 1a-2 and 1c have to add, since nothing today labels a message by who wrote it (the only per-message extension is `lq_ai_skip_anonymization`, `gateway/app/providers/openai_schema.py:85`):

- request fields for the agent's instructions and for the listed skill names, separate from the field that carries attached skills, so a listed skill is never merged in full by accident;
- assembly that runs when one of those fields is set, even with no skill loaded;
- the new headings added to the set that inputs cannot forge (`_MARKER_LINE_RE`, `assembler.py:112-116`), and the agent's text treated as input for that purpose;
- the order above: the LQ.AI part for every request, the agent and skills-list parts for requests that carry the new fields.

**Honest limits.** The label tells the model who wrote the text. Nothing enforces rank. Agent instructions are pseudonymized like other system text on a route that pseudonymizes. Attached-file text is document text. Ruled 13 November (API R70): it stays a system message in Stage 1, on agent turns too; only knowledge moves. Earlier drafts had decided "its own message"; that is reversed. Ruled 13 November (API R75): attached-file text and the carried passages are sent as a system message of their own, after the assembled one, word for word, never under the operator heading, on agent turns and ordinary chat alike. The limit: a provider that takes one system prompt receives them joined (the Anthropic adapter joins system messages), so "separate" holds only up to the gateway. From a chat's second turn, the passages the previous reply cited travel in a system message as well (API R72, annex B4). So on agent turns document text leaves the system messages only as `search_knowledge` results.

**Ordinary chat after slice 1a-1 (API R36, R32).** With agents off the LQ.AI part comes first. Knowledge passages and attached-file text stay separate messages, word for word, as today. The gateway adds the LQ.AI part only when the request carries a new field that only the chat send path sets. That field is separate from the purpose tag, and its name is not ruled. The request builders that must set it (send, loop rounds, resume, re-run) are still to be listed; the callers of the endpoint were not all traced.

**The default agent (API R35, R52, R34, R64).** Its file has no `model` line, no skills and `tools: chat`. It ships with `knowledge: none` and keeps today's server fetch until the citations slice merges; then the line changes to `knowledge: [matter]` (API R64, amending R52 and R61). So for that period `knowledge: none` means "fetched by the server, as chat does today" on the default agent and "no knowledge" on every other agent, in a file users read through View file. Ruled 13 November (review-rulings file, V13): accepted as it is, with no comment in the file and no other value. The period is inside Stage 1, before agents are announced. With no `model` line the picker decides, and an unset picker gives the install's default model (the request's default as today, which on `main` is the `smart` alias; whether the picker shows that alias is for slice 1m-1; an API note of 13 November, not a ruling); a model picked there lasts one turn, as on every agent chat (interface ruling, 13 November). It is named `lq-ai` and titled "LQ.AI". Its body is empty for now: the LQ.AI system prompt, which every chat gets, is its whole voice. A body can be added later as a new shipped version (API R61). A chat on it always runs the default file of the running release: the chat's pointer is "default", with no version and no "newer version" line. Each turn's record carries the file's fingerprint, and on upgrade the server keeps each shipped default's text in the store, so the text an old turn used can be read back. So an upgrade changes the default agent for every chat on it at once, and release notes say so. Inline skill text is allowed on the default agent, as in ordinary chat today, and the record carries its fingerprint. It is refused only on a chat whose agent the user chose.

### B3. The loop and `load_skill`

The chat tool loop is `run_chat_tool_loop` (`api/app/chat/tool_loop.py:787`). Each round is a complete, non-streaming request to the gateway that keeps the request's skill and tier fields (`tool_loop.py:1058-1082`). On every round the gateway assembles the prompt, checks the tier, pseudonymizes and writes its routing-log row again.

**Decision: `load_skill` attaches.** When the model calls `load_skill("nda-snapshot")`, the server adds that name to the request's skill set and returns a short "loaded" result. On the next round the gateway merges the skill as it merges any attached skill, with the same heading protection and input checks.

Declined: returning the skill's text as a tool result, which skips those checks.

What the loop slices must handle, from the code as read (`load_skill` is slice 1h; the hand-back after each round is 0b, progress events 1n, stop 1o, the limits 1p):

- The loop copies one base request each round (`tool_loop.py:1075-1082`; used at `:876, 880, 1010, 1015`). The tool executor cannot see it, so the loop handles a load itself and rebinds the base request with the new skill set. The load still writes one row in the tool-call log through the governed path, like any tool; The loop calls the same governed entry point as every tool, so the row, tier 0 and digest are written the same way, and it applies the effect of the load after that call returns (API R45).
- Dispatch needs its own branch: any tool kind that is not skill, research or authority falls through to connectors (`tool_loop.py:680-687`).
- A skill's own tools are added once, before the loop (`chats.py:1861`). Tool schemas are re-read each round (`tool_loop.py:882`), so adding the loaded skill's tools to the allowlist is enough.
- On agent turns the loop counts rounds, not tool calls: an operator setting, 20 by default, with an optional spend limit per turn beside it. A load is an ordinary round, so the earlier special case for load-only rounds is gone. At a limit the loop runs one last round with tools off (today's directive is at `tool_loop.py:1009-1011, 1022-1028`), and the reply and a progress event say the limit was reached. On an install with agents off, chat keeps its cap of 8 calls, until the old chat path is removed (ADR R26). The spend limit is a threshold checked after each round, and only the rounds limit applies to local models. There is no count of tool calls within a round (API R37).
- The loaded set must survive a pause and be there on the resumed turn.
- A second load of the same skill is a no-op with a result that says so.
- The loop does not check for a stop today. New: closing the stream, or an explicit stop call, ends the turn at the next round boundary. The round in flight finishes, no further tool runs, and the reply is saved as stopped with what was gathered. Ruled 13 November: both ship in one slice, which starts by verifying what a closed stream does to a running loop today (API R46). A stopped reply always has text: a fixed line saying it was stopped and after how many rounds, then anything already written (API R37). Stop applies to every tool turn, agents on or off (API R36).
- New: the loop reports progress in the chat stream, with names and counts only: an event when a round's model call starts, when each tool call starts, and when each ends with its outcome (`round_started`, `tool_started`, `tool_finished`, `skill_loaded`). This amends "after each round" (API R39). Progress events apply to every tool turn, agents on or off (API R36).

**The check comes first (slices 1g-1 and 1g-2).** Today the gateway checks required inputs and tier minimums for the skills attached to a request (`assembler.py:464-484`; `inference.py:661`). With loading, the set grows mid-turn. So the server checks every listed skill before round one, against the agent's model and the matter. A skill with required inputs is no longer refused: that check is removed everywhere (API ruling R11). The check also runs before the user's message is saved, and uses the model that will run.

### B4. Knowledge, history and pseudonymization

**`search_knowledge` (slice 1i)** is a chat tool backed by chat's own retrieval, `_retrieve_kb_context_for_chat` (`chats.py:1189`), which searches by meaning and by keyword. Today the send path writes a retrieval audit row only when passages come back (`chats.py:1666, 1687-1701`). New in 1i: the tool writes a row for every search, empty ones included. Ruled 13 November (audit 15, API R83): that row names the embedding's provider and tier, or "keyword only" when no embedding was made. The tool sends the turn's chat and message ids with the embeddings request, and the gateway writes them on its routing-log row. The tool-call row stays tier 0, which there means the tool, not the embedding. New harness has a tool of a similar name, but in another registry and with keyword matching only (`api/app/autonomous/orchestration/tools.py:376-505`); it is not ported.

**`search_history` (slice H1)** searches this chat's messages that fell out of the window.
**The pseudonymization problem, unsolved.** In ordinary chat, tool results are sent as they are and tool-call arguments come back as the model wrote them. One request-wide switch changes both at once: it covers tool results and restores arguments (`gateway/app/anonymization/middleware.py:141-145, 160-167, 337-349`). Only governed runs set it (`api/app/autonomous/`). On a route that pseudonymizes:

- the model writes its search query from pseudonymized text, so arguments need restoring;
- knowledge passages must still reach the model word for word (Decision M2-1);
- history results must be covered, as they are when they travel as messages.

One switch cannot do all three. A message can be marked to stay word for word (`middleware.py:155-156`), which may be enough for knowledge. H1a builds the rule per tool. **Until then, Stage 1 leaves the switch off:** `search_knowledge` receives the query as the model wrote it, placeholders included, so search is weaker on a pseudonymizing route; passages still arrive word for word. No stock route pseudonymizes: the example ships with it switched off (`gateway.yaml.example:477`); switched on, it applies to tiers 3 to 5 (`:484`).

**Citations on agent turns (API R50, R62 to R64, R71, R72).** Today a reply's quotations from matter documents are checked against the passages the server fetched and numbered before the model was asked, and saved as citations (ADR 0018). On an agent turn nothing is fetched beforehand. Ruled 13 November:

- **Numbering.** `search_knowledge` returns numbered passages. The numbers run on across every search in a turn, and a passage returned twice keeps its first number. Numbers start again each turn.
- **The citing rule** is in the system prompt, and each result carries a one-line reminder of the format (R62; his choice was "Both"). The reminder is an instruction inside a data message, and the ADR has to say so and why. `lq_ai_assembled` gains the citing rule as a part, kind `citing_rule` (API R76). Where it sits in the prompt's order was answered twice and is not reconciled (annex B2). Ruled 13 November (ADR R33): the reminder is allowed because it is fixed wording from LQ.AI's code, the same in every result, and says only how to cite. It is the one instruction allowed in a data message and is listed in the turn's record. The evaluation runs with and without it; if it does not help, it is removed.
- **The list.** The loop keeps the turn's passage list and saves it with a paused turn, so it survives a confirmation. Read on `main`, not run: the loop collects case-law sources across rounds today, and a paused turn's saved state does not yet hold them.
- **The check.** When the turn ends, the reply's quotations are checked against that list by today's checker, unchanged, and enter the ledger as today.
- **Follow-ups (R71, R72).** A tool result lives only inside its turn. So at the start of a turn, the passages the previous reply cited (verified citations only) are placed first in the new turn's list as [1] to [k]. They are sent in today's "retrieved context" block, word for word, as a system message of their own (API R75). Ruled 13 November (API R80, amending R72): the block's header loses the citing rule and keeps its label, so the rule appears once, as the prompt part plus the reminders; and passages are carried only when the turn's agent can search knowledge. The turn's record lists the carried passages by count and source ids, with the reply they came from and no text (audit 17). Searches in the turn continue from [k+1]. Only the previous reply's passages are carried, not the whole chat's. The cost is more tokens on every follow-up turn, and document text is again in a system message.
- **When.** Built in Stage 1, with or straight after slice 1i, before agents are announced (R64). Until it merges, the default agent's file says `knowledge: none` and keeps today's server fetch. A security-path slice, larger since R71 and R72; not sized.

The gap was found by reading the code, not by running it.

**Placeholders after a mid-turn load (API R38).** Not tested: on a pseudonymizing route, placeholders may change number after a skill is loaded mid-turn. Slice 1h adds a gateway test (search, load, search again, compare placeholders). If the effect is real, `load_skill` on such routes waits for the per-tool rule planned with the history tool.

### B5. Records

Where each thing is kept:

- **Agent text:** one table of versions. A saved version is never edited.
- **The full record of an agent turn:** the details field of the `chat.message_sent` audit row. That field is free-form, so no audit migration is needed. The `work_product_attribution` row keeps what it holds today.
- **The reply row** (the reply's row in the messages table) gains three things: the agent's id, its version, and how the reply ended: one of `completed`, `rounds_limit`, `spend_limit`, `stopped_by_user`, `connection_closed`, `failed` and `pause_expired`, the same value as in the record (API R79, audit 16). A refused turn is not on the list, because it leaves no reply. The pill and the "changed to" line read the first two (API rulings R17 and R26). Summed tokens and cost fill columns the row already has, and loaded skill names still reach `messages.applied_skills` by the existing path (audit ruling 2, as amended).

What the audit row carries:

- the agent's id, version and fingerprint: the file's fingerprint, from the store. It is `agent_file_fingerprint`. Beside it, as `agent_instructions_sent_fingerprint`, the gateway's fingerprint of the instructions it was sent (API R67, V22);
- the file's model and the model that ran, and whether the sender picked it (API R47);
- the LQ.AI prompt's version, the skills offered, each skill loaded and its fingerprint, the tools offered and called, the knowledge bases searched, any "run without" choice, the passages carried into the turn by count and source ids (audit 17), and what ended the turn (API R79);
- a name and fingerprint for every part of the prompt: the LQ.AI prompt, operator instructions, the Organization Profile, the agent, the skills list, each loaded skill and, on agent turns, the citing rule (API R62);
- no agent, skill or prompt text (ADR 0016 P3).

Every chat turn's audit row carries the LQ.AI prompt's version and fingerprint, agents on or off (API R47).

Where that comes from:

- The gateway is the source of truth for what was assembled. On each round it returns one `lq_ai_assembled` object: `parts`, in order, each with a kind (`lq_ai_prompt`, `operator`, `agent`, `skills_list`, `skill`), a name, a version where it has one, and a fingerprint. The citing rule is a part too, kind `citing_rule`, with a version and a fingerprint (API R76, R80). The Organization Profile is a part of kind `organization_profile`, with a fingerprint (V22). `lq_ai_applied_skills` stays as it is.
- The backend copies that into its record, listed per round.
- The gateway reports and does not keep. Its routing log is unchanged and stays the per-round record of model, tier, cost and pseudonymization, joined to the audit row by message id, with no gateway migration (audit ruling 12).
- The kinds shown to the maintainer do not include the Organization Profile, which audit ruling 6 names; to settle in slice 1a-1.

What can be read back: the text of agent versions and of the LQ.AI prompt. The rest is proven by fingerprint and not kept. Ruled 13 November (V23): for operator instructions and the Organization Profile that limit is accepted; where an old turn's record is shown beside the current text, the interface compares fingerprints and says "changed since this turn". The orchestrator's reading, not ruled: no Stage 1 screen shows a chat's owner an old turn's record, so that line waits for the receipts extension. So the claim is "the record says which", not "you can re-read the prompt".

What each fingerprint covers (API R67, which supersedes R60). Every fingerprint is over saved text a user can read, never the rendered prompt. The agent has two. The record's agent fingerprint is the file's, from the store: it is what View file shows, and the exit test compares those two. Separately, the gateway reports a fingerprint of the instructions it was sent, kept in the record as `agent_instructions_sent_fingerprint`; the file's is `agent_file_fingerprint` (V22). A skill's fingerprint is over the skill as saved, not as rendered. The LQ.AI prompt is identified by its file and version.

Who can read the record (review ruling V6, API R65). In Stage 1, only someone with access to the audit log. A chat's owner sees the names of loaded skills under each reply, from the reply row, and not the searches run. Extending the receipts call so the owner reads each turn's record (API R51) is kept as the goal and moves out of Stage 1. Where it goes was answered twice on 13 November and is not reconciled: a slice after Stage 1 is announced and before agents turn on for every install (ADR R31), and "rule after the API reports" (V26). The API discussion has since reported (annex E).

Limits:

- The gateway writes one routing-log row per round, so an agent turn has several.
- Slices 1f-3, 1h and 1i each write their part of the record for turns that run straight through. A turn that pauses for a tool confirmation or a connector sign-in, and the resumed turn, get their agent record in slices 1l-1 and 1l-2, at seven sites. A paused turn stores its frozen agent reference with its saved state, and the resumed turn runs on that version even if the chat's agent has changed since. The saved state also carries the agent's instructions, so the turn finishes even if that version is retired or deleted meanwhile (API R68). Agents are not announced as usable until all of these slices are on `main` (B1), so an announced turn that completes, pauses, fails part-way or is refused has its record. One more case was ruled on 13 November (V14): a turn that succeeds while its audit write fails. Today such a turn keeps its reply and has no audit row (a probe on `main`, on the streamed path with the loop replaced by a stub; annex H). On an agent turn the reply and the audit row become one write. If the record cannot be written, the reply is not saved and the user gets an error, even though a streamed answer may already have been shown. Chat with agents off stays as today, so there a successful turn can still lack its audit row; that ends when the old chat path is removed (ADR R26). Part of the failed-turn slice; not sized.
- **Admin re-runs.** Audit ruling 13 says an admin re-run's audit row names the blocked turn's agent and says the re-run did not run as that agent, and that the re-run's own reply carries no agent pointer. Ruled 13 November (API R30): in Stage 1 the admin re-run is not wired to agent refusals. A refused agent turn saves no message and no reply row, so there is nothing to re-run, and no Stage 1 slice changes the override handler. Audit ruling 13 applies once something writes a refusal row. By search of `main`, not run: nothing writes a refusal reply row today, so the re-run may not be reachable at all. That is to be confirmed on a running stack and filed as its own issue. Ruled 13 November (API R81): the admin re-run is removed with the old chat path. An admin who wants a refused turn run changes the route or the matter's floor, and the user resends. The ADR states it as a capability removed at the trigger.
- **Refusals.** A refused agent turn writes an audit row of its own in slice 1g-2 (audit ruling 11): the agent's id, version and fingerprint, the item refused and the reason code. The action is `agent.turn_refused` (API R45). The ruling adds "and later the 'run without' choice". Audit rows are not edited. Ruled 13 November (V21): two rows, neither edited. The refusal row records the refusal; the resent turn's own record lists what it ran without; a refusal the user abandons leaves the refusal row alone. The reply row's pointer and the audit row must agree.
- **Failed turns (API R69, which lifted a hold on R54).** Run on 13 November on a clean copy of `main`, with the loop replaced by a stub (annex H). Today, when the loop fails on the non-streaming path, only the user's message is left: no reply row and no audit row. On the streamed path a reply row with the error and an audit row are written. Ruled: both paths save a reply row with the error and write the turn's record, together or not at all, and the loop hands back what it had done when it failed (rounds completed, tools called). A new security-path slice in Stage 1, not sized. Not run: a real loop failing after real tool calls. The review of 13 November had read the streamed path's audit write as best-effort; the run showed the row is written when the loop fails. Ruled 13 November (API R74): a paused turn that runs out ends as a failed turn in the same way.
- **Closed connections (API R66).** Today, on the streamed path, a client that disconnects cancels the loop and nothing is saved (the same run; the non-streaming path was not run). Ruled: the loop runs protected from the connection closing. A closed stream is noted, the round in flight finishes, no further round starts, and the reply and record are saved as stopped. A tool call is never cut half-way. Part of slice 1o, for every tool turn, agents on or off.
- Tool-call rows and the gateway's routing log are not marked with the agent. They join through the message id. `load_skill` and `search_knowledge` each write one tool-call row (tier 0, digest only); results are recorded as outcome and counts. Their rows carry the provider name `lq-ai`, meaning a tool LQ.AI itself runs (API R45).
- The server holds the chat's agent: a pointer on the chat row to one saved version, not a copy. Every record site uses the id, version and fingerprint frozen at the start of the turn. An agent can be set, swapped or removed between turns, so one chat can hold turns from several agents and from none. With agents on, clearing a chat's agent returns it to the default agent. Ruled 13 November (audit 14, API R84): only the server's own change is an audit event. When a chat's agent is retired or deleted and the chat falls back to the default agent, the server writes a `chat.agent_reassigned` row in the same write, at the next turn's start: the chat id; from (agent id, version, name); to (`default`); the reason (`agent_retired` or `agent_deleted`); no user as actor. A user's own change is not an event; each turn's record names its agent.

Agents shipped in the repo are reviewed like code. The default agent is one: a built-in file with no skills listed and `tools: chat`, readable through View file like any other (API R16). Stage 1 builds one route for all: their instructions sit in the same section under the same limits, and the label says "built in to LQ.AI". LQ.AI says shipped agents are reviewed like code, not attested.

**The tier check before the call (slice 1g-1).** The gateway's models listing carries each alias's tier, taken from its primary provider. It is absent only when that provider is not configured. So the API can learn the tier before the call. 1g-1 must resolve skill tier minimums through the same user, team, built-in order the API's internal skill endpoint gives the gateway (`api/app/api/internal.py:142-179`), or the two checks will disagree. The gateway still checks on every round; the check only makes sure it has nothing left to refuse.

**Skills total (slice 1g-2).** Today there is no total: the two attachment lists are each capped at 16, sticky skills come on top, and the request to the gateway is capped at 16. The plan's rule, "listed plus hand-attached plus sticky skills are at most 16, refused with a notice before the call", is new work in 1g-2. So is refusing inline skill text on an agent chat.

## C. Slices for Stages 2 to 4, the history tool and contributed agents

One pull request is at most about 400 changed lines including tests. **[S]** marks a security-path slice; **[C]** one a contributor could take, which adds a maintainer review. Days, as used in the plan's calendar: about 1 per backend slice, 1 to 2 for **[S]**, 1.75 per interface slice. Nobody has tested these rates.

Draft 3's slice G1, a gateway label for agent instructions, is gone. Its work is slices 1a-1 and 1a-2, the first gateway slices of Stage 1.

### Stage 2 — Build one on screen (8 PRs, about 2,550 lines, 12.5 days)

The next two sections moved here from the main plan on 13 November.

#### The builder screen

The brief asked for "a Diablo RPG kind of thing". The screen keeps what does the work in that idea (an inventory panel, fixed slots, locked items that say why, a pane to try the build, a save file) and deliberately drops the game vocabulary, because its readers are lawyers.

An illustration of the end state, once every slot exists:

```
 Agents › NDA Comparer · version 2 · experimental     [View file] [Save]
┌─ Installed here ────────┐ ┌─ NDA Comparer ───────────────────────┐
│ MODELS                  │ │ When to use   [Compares a set of…]   │
│  local            Added │ │ Instructions  [You compare non-…]    │
│   Tier 1, on site       │ │                                      │
│  smart    Not available │ │ Model      local              Remove │
│   Tier 4. nda-snapshot  │ │ Skills     nda-snapshot       Add…   │
│   needs tier 2 or       │ │ Knowledge  This matter        Add…   │
│   stronger              │ │ Tools      What chat offers here     │
│ SKILLS                  │ │ History    This chat          Remove │
│  nda-snapshot     Added │ │ Workspace  Its own files      Remove │
│   Needs: tier 2 or      │ │ Helpers    Not available: your       │
│   stronger; no inputs   │ │            operator has not switched │
│   Adds: NDA comparison  │ │            helpers on                │
│ KNOWLEDGE, CONNECTORS … │ │ Can use: local (tier 1), nda-snapshot│
│ Set by your operator:   │ │ this matter's knowledge, own files   │
│  at most 20 rounds      │ ├─ Try it ─────────────────────────────┤
│ This matter:            │ │ > Compare the five NDAs              │
│  no minimum tier        │ │ NDA Comparer v2:  | NDA | Conf. Info…│
└─────────────────────────┘ └──────────────────────────────────────┘
```

- **Left:** what the operator installed. Each item is a small card: what it needs, what it adds. An item that cannot be added stays visible, with the reason in words. The operator's terms and the matter's terms are shown and cannot be edited.
- **Right:** seven slots. "Helpers" is the interface word for sub-agents. The **Can use** line changes as items are added.
- **Try it:** a chat using the version on screen. Each reply says which skills were loaded. It has a matter chooser, and every try starts clean (interface rulings, 13 November). Each try is a new hidden chat (API R73).
- Add and Remove work by click or keyboard. There is no drag-and-drop.

Interface text says "operator" for whoever runs the deployment and sets its settings. An admin is a signed-in user with the admin role. On a small install they are the same person; in a firm they may be two.

#### Building it

1. Open Agents. Choose "New agent", or paste or upload a file. Ruled 13 November (interface): the Agents page is the one way into editing an agent or copying one; the pill in a chat only switches agents.
2. Write "When to use" and the instructions.
3. Model › Add › `local`.
4. Skills › Add › `nda-snapshot`. Its card says it needs tier 2 or stronger. The `smart` card changes to "Not available", because `smart` is tier 4 here. The **Can use** line gains the skill. Adding a skill puts it on the list the model may load from; it does not load it.
5. Tools shows one choice, "What chat offers here". Confirm it.
6. Type in "Try it". The text is saved as version 1 and the reply comes from it, in a hidden chat made for that try, with the chosen matter: an ordinary chat row, hidden from the chat list and search (API R73, amending R19's "one per agent"). Earlier tries are a list of those hidden chats, one turn each. Other chats stay on the version they had. An unsaved skill must be saved before it can be tried with an agent. Edit the instructions and try again: version 2. Version 1 still exists, unchanged. Ruled 13 November (interface): the pane has a matter chooser, which starts on the matter this agent was last tried against, and on no matter the first time. Every try starts clean: it runs as the first turn of an empty chat, and earlier tries stay visible above but are not sent to the model. So a follow-up question cannot be tested here.
7. "View file" shows the exact text and its fingerprint. "Use in chat" starts a new chat set to this agent, at this version. The chat shows the agent's name as a pill with an agent icon.

Opened from a matter whose minimum is tier 3, `smart` would read "Not available: this matter needs tier 3 or stronger". This line predates the rulings of 13 November: the builder is no longer opened from a matter. Whether the cards are checked against the matter chosen in "Try it" is not ruled.

#### The slices

| Slice | What | Lines |
|---|---|---|
| 2a | Edit name, when to use, instructions; Save; **Try it**. The Tools slot is shown with one explicit choice, "What chat offers here", which the builder confirms before the first save; the file gets `tools: chat`. Try it saves the text as a version first, so every turn has a row, and runs it in the builder's scratch chat: an ordinary chat row with a flag that keeps it out of the chat list and search, one per try (API R73; until 13 November it was one per agent, reused). The flag's column is in slice 1e's one migration (B8). Since 13 November it also needs a matter chooser, tries that are not sent the earlier turns, and the last matter used (interface rulings). Ruled 13 November (API R73, R78): each try makes a new hidden chat with the chosen matter and the new version, so nothing is added to the send path; earlier tries are listed by a read call, and the last matter is read from the newest one. Deleting a version deletes the try chats that ran it; otherwise they are kept until the agent is deleted, with no clean-up job. Not re-sized. Other chats stay on their version. An unsaved skill shows "Save this skill to try it with an agent" | 400 |
| 2b | Model and Skills slots. Each item is a card: what it needs, what it adds. A skill's card says it is loaded by the model when needed | 400 |
| 2c | Knowledge slot; pick among the matter's knowledge bases | 350 |
| 2d **[S]** | Carry one of the user's own knowledge bases by name into a chat where it is not attached. Conditional: see below | 250 |
| 2e | "Installed here" panel for models, skills and knowledge, with reasons; the "Can use" line, which changes as items are added | 350 |
| 2f **[C]** | Claude Code import and export. First file: a pure mapping function with tests | 400 |
| 2g **[C]** | Three starter agents (comparer, researcher, drafter), one file each | 150 |
| 2h **[S]** | To re-scope: the required-inputs check is removed everywhere (API ruling R11), so such skills are listed from Stage 1 and the missing-input check named below no longer exists. `load_skill` takes inputs. A skill that declares required inputs can be listed; the list shows what it asks for; the model supplies the values as arguments; the gateway's existing missing-input check and untrusted-input wrapping apply. A missing input comes back as a tool error the model can read, not a failed turn | 250 |

**Slice 2d and the rule it crosses.** Today a chat in no matter retrieves nothing, and attachment to a matter is the only grant. Retrieved passages are sent to the provider un-pseudonymized, and that stays true when they arrive as a tool result. So carrying a knowledge base from matter A into a chat under matter B's terms, or no matter's, moves documents across terms. Proposed rule for the ADR: an unbound knowledge base of the user's own may be carried anywhere; one bound to a matter may be carried only within that matter. If the ADR does not state a rule, 2d leaves the Stages 1–3 ADR and waits for its own decision. Narrowing (2c) is unaffected. DE-408 does not have to be decided first.

**Import is lenient (2f).** Known fields are mapped and the rest are shown as notices. A Claude Code file with no `tools` line makes the builder choose; it is read neither as "all" nor as "none".

**Needs to merge.** Stage 1.

**Exit test.** With the keyboard only: build the example, try it, save twice. An old chat's record still leads to version 1's text. Import a Claude Code file with no `tools` line: the builder must choose. Open a file naming a knowledge base you do not have: "Not available: not found. Choose one of yours, or run without it." List a built-in skill that asks for inputs: the model loads it with values, and the record shows the skill as loaded.

**Not in Stage 2.** Tools beyond `chat`. Sharing inside a team. Comparing versions. A size meter.

### Stage 3 — Tools and connectors (4 PRs, about 900 lines, 6 days)

| Slice | What | Lines |
|---|---|---|
| 3a **[S]** | `tools: none` and the selectors in A2, applied at all three places chat assembles tools, including after a resume | 250 |
| 3b **[S]** | For non-admins: the list of connectors, including those with no sign-in, and each connector's tools. Smaller than drafted: endpoints for research sources, research capabilities and connector sign-in already exist for ordinary users | 120 |
| 3c | Tools slot with real choices; connectors in the 2e panel; "Needs you: connect" | 350 |
| 3d | To re-scope: agent turns are bounded by rounds and spend from Stage 1 (API ruling R23). What remains is the file's own lower limit, carried through a pause; `limits.max_tool_calls`, whose name is not ruled. The build plan puts the file's lower number in slice 1p as well, so little is left here; not re-sized. Today the cap is compared after a whole round, so a round with several calls can overshoot | 180 |

Slice 3e, streaming the last round of a loop turn, moved to Stage 1 as its last slice (B3). Today every round is a non-streaming call and the final text is sent to the browser in one piece (`api/app/chat/tool_loop.py:1080`; `api/app/api/chats.py:3698`).

**Needs to merge.** Stage 2 slices 2a and 2e: slice 3c puts connectors in the 2e panel.

**Exit test.** An agent with `tools: none`, no `skills` and `knowledge: none`: no loop runs, the reply arrives word by word, and the tool-call log has no row for the turn. With `tools: [research]`: the record lists the research tools, `load_skill` and `search_knowledge`, and no others. With a connector the user has not signed in to: "Needs you: connect".

**Not in Stage 3.** Installing connectors. New tools. One registry for all tools (DE-416). Narrowing to one authority source. Streaming any round but the last.

### Slice H1 — the history tool **[S]** (2 PRs, about 450 lines, 3.5 days)

| Slice | What | Lines |
|---|---|---|
| H1a **[S]** | Gateway: cover the results of a named tool, and restore its arguments, without doing the same to every tool on the request (B4) | 200 |
| H1b **[S]** | `search_history`: a chat tool over this chat's messages outside the window, for the chat's owner; `history: chat` in the file and the check; a tool-call row and an audit row for every search, with counts only | 250 |

**Needs to merge.** Stage 1. The ADR that PRD entry DE-409 already requires for the rule in H1a; a committee item (E). **Not before mid-August 2027** under ordering A. It needs only Stage 1, so the maintainer may pull it forward at Stage 2's expense.

**Exit test.** With pseudonymization switched on (the stock example has it off), in a chat longer than the window: the agent is asked about something said early on. It calls `search_history` and quotes the message. A gateway test shows the tool result left the deployment pseudonymized. All three conditions hold before the tool ships: the per-tool cover rule, that test, and the two rows per search. Until then `history` stays a reserved field.

**Not in H1.** Other chats of the matter: ruled 12 November as not a later stage of this tool, but a separate proposal with its own ADR. Summaries of old messages. Any change to the window itself.

### Stage 4 — The agent's own workspace (4 to 5 PRs, 1,100 to 1,300 lines, about 7 days)

Draft 2 said 3 PRs and 800 lines. That was low. Today's saved-work store is keyed to a skill and every operation takes a skill binding.

| Slice | What | Lines |
|---|---|---|
| 4a **[S]** | A store keyed to the agent, not its version, so an edit keeps the files. Migration, model, operations, deletion, `docs/db-schema.md` | 350 |
| 4b **[S]** | A second code path with no skill binding; three workspace tools (list, read, write) as a new tool source in chat, modelled on the skill workspace tools; `workspace` in the check | 300 |
| 4c **[S]** | Owner inspection, export and reset for agent stores, which ADR 0035 D8b requires | 200 |
| 4d | Workspace slot on the Stage 2 screen; the agent's files on its page | 300 |

**Needs to merge.** Stage 1 for 4a to 4c; the Stage 2 screen for 4d. The amendment to ADR 0035 D8b, a committee item (E). A minor release, because 4a is a migration. Slices 4a to 4c are security-path changes.

**Exit test.** Operator switch off: "Not available: your operator has not switched workspaces on". On: the agent saves a note in one chat and reads it in another chat of the same matter. A second agent using the same skills cannot see it. The owner can inspect, export and reset the agent's files.

**Limits.** Storage is per matter, not per chat. Today only a matter's owner may use saved work; Stage 4 keeps that unless decided otherwise. Saved files are never put into a prompt automatically; the agent reads them with a tool.

### Contributed agents, slices L1 to L4 (about 700 lines, 4 days)

Earlier drafts called this the Labs track.

Contributed agents need no Labs ADR: they are files added by pull request and reviewed like code. Ruled 13 November: one whose instructions carry legal substance follows the skills path in `skills/CONTRIBUTING.md` (claim, draft, attest, lawyer and engineer review).

| Slice | What | Lines |
|---|---|---|
| L1 **[C]** | `agents/contributed/<name>/`: the agent file, any skills it needs, a README saying what to bring. A CI check that each file is valid. Needs slice 1d only | 200 |
| L2 | A CI check that each contributed agent loads and passes the check on the stock example configuration. Models by alias only | 150 |
| L3 | "Propose this agent": opens GitHub's new-file page with the agent file filled in. One file per page; long files not verified | 150 |
| L4 | A "Community" section on the Agents list | 200 |

- L1 to L3 are CI and a link. They need nothing in the images.
- L4 does. `skills/` reaches the release image by a `COPY` and reaches development by a mount on the api and worker services. A repo-root `agents/` folder needs the same, plus a settings path, before L4 can list anything.
- No stand-alone "validate skills" CI job exists to copy. The closest models are the skills tests in the main CI workflow and the release-image skills check.
- Settled 12 November, for built-in agents only (ADR ruling R12): agents shipped in the repo are reviewed like code, not attested. Ruled 13 November for contributed agents: one whose instructions carry legal substance follows the skills path; the others are reviewed like code. The Labs list page waits for a Labs ADR and is outside this plan.

## D. Sub-agents trial specification

A throwaway. Depends on Slice 0 only. A contributor may take it from December.

A sub-agent is a turn built the same way from another agent file; `delegate` is one more tool in the parent's loop. The trial hard-codes most of that.

**The two tools on this track (ruled 12 November).** `delegate` is a tool that lets a main chat create a sub-agent. `plan` is a tool that creates a plan (markdown or something else), which the chat itself follows and updates. The trial covers `delegate` only. `plan` has no design, no size and no trial. A plan is a document that belongs to the chat, stored by the server and shown in the chat, and the agent updates it across turns. It arrives with `delegate`, after the trial, and is not in Stages 1 to 4. The user approves it. Ruled 13 November: that is decided in the sub-agents ADR, not on 22 November. How an approval is recorded waits for the trial.

- Branch only, behind an off-by-default setting, never merged. About 250–350 lines with one integration test; 2–3 days.
- **Hard-code:** depth 1; one `delegate(task)` call per turn; sub-agent instructions as a constant; no skills list; sub-agent tools are the read-only research tools only; sub-agent cap 3; non-streaming path only.
- **Skip:** pauses (a sub-agent confirmation or sign-in pause returns an error tool message), tool-log parentage (log lines instead), interface, storage, cost roll-up.
- **Must confront:**
  - (a) Terms. The sub-agent's request is a copy of the parent's with fresh messages, so the matter's minimum tier, privileged flag and user id carry. Assert that its routing-log tier matches the matter's. **A copied request also inherits the parent's loaded skills, skills list, files and skill inputs.** The trial must clear them or keep them on purpose.
  - (b) Pseudonymized task text. Run once on a pseudonymizing route. Observe what the sub-agent receives and whether its answer is restored sensibly.
  - (c) Transaction length. Commit before the sub-agent starts and observe what breaks.
  - (d) An explicit `delegate` branch ahead of the connector fallback.
- **Shows on screen:** one chat turn in a matter where the answer includes a passage a sub-agent produced, plus the routing-log rows (parent and sub-agent, same message id, same tier) and the tool-log rows.

**Questions, by what the trial can do with them.**

| # | Question | The trial |
|---|---|---|
| 1 | Does the sub-agent provably run under the parent's minimum tier and privileged flag, on every route the gateway may choose? | Observes; partly answerable from the code now |
| 2 | What does the sub-agent see when the parent's route pseudonymizes, and can it use tools with pseudonymized arguments? | Observes |
| 3 | Can the parent's tool-log row be committed before the sub-agent runs without breaking atomic audit (ADR 0016 P5)? | Observes |
| 4 | Is a parent column on the tool-call log required, or is the message id enough? | Observes |
| 5 | What is the right budget: shared cap, separate cap, a deadline for the whole turn? | Informs; a design judgement |
| 6 | What happens when a sub-agent hits a confirmation or sign-in pause: refuse, or nest the pause? | Cannot answer: it skips pauses. **The ADR answers by argument** |
| 7 | What context does a sub-agent need (history, knowledge, attached files), and where is it built? | Informs; a design judgement |
| 8 | Does sub-agent output need its own stored record for the transcript to be accurate? | Cannot answer: it skips storage. **The ADR answers by argument** |

**Design inputs for the ADR and the build.** These are known holes, not solved problems:

- cap accounting between parent and sub-agent;
- sub-agent context built outside the loop;
- an open transaction and no turn deadline;
- nested pauses;
- unknown tool kinds falling through to connectors;
- log parentage;
- pseudonymized task text;
- **a sub-agent's gateway refusal fails the whole parent turn**; the ADR must say whether it should become a tool error the parent can read;
- **the citation and source return channel**: a sub-agent's sources and quotations are local to its own loop and are not checked or shown by the parent unless forwarded;
- handing documents down;
- showing progress without streaming;
- cost per hand-off.

A sub-agent with a connector comes later still (DE-409). The earlier guess of 7 PRs and 1,500 lines for the build is low.

## E. Governance path

**The rule.** GOVERNANCE.md rule 1: architectural and product decisions are ADR-first. Rule 3: scope and roadmap decisions belong to the committee. A new file format, a new user-facing concept and a check that authorizes are all of these. So:

- **Build and demonstrate on a branch:** waits for nothing.
- **Merge Stage 1:** waits for one ADR, "Agent files in chat". About two pages. Covers Stages 1 to 3 and, since 13 November, the replacement of ordinary chat, its trigger, the removal of the old chat path and the New harness freeze (decisions 11, 14 and 15 below). Whether "about two pages" and 22 November still hold was not put to the maintainer (open question 42). Bundled with nothing. Numbered when its pull request opens: 0043 and 0044 are Accepted on `main`; #804 claims 0045. Ruled 12 November: the plan and the one page give the title only. The ADR takes the next free number when its pull request opens, probably 0046. The earlier "Agents in chat" draft is marked superseded where it sits and is never filed. Ruled 12 November: one new ADR whose header says it amends ADR 0007 (new request fields, section order, protected headings, required inputs no longer enforced), sits beside ADRs 0035 and 0038, and reverses direction 2 of 7 October (New harness as the base). It cites 0038 as Proposed.

**Can the ADR be tabled on 15 November? No.** This design adds five decisions (5 to 9 below) to the six kept from draft 3, and they are gateway and security-path decisions. Only about two working days fall before the 15 November call, and Slice 0 takes them. So:

- **15 November call:** Slice 0 is shown and this design is presented for direction. Nothing is tabled for agreement. Ruled 13 November (API R57): the design is not shown until Slice 0 has run through the gateway; if it is not ready by Sunday, the item moves to 22 November with the ADR. Ruled 12 November: one page goes with it, carrying the turn shape, the decisions as headings, the aim, and four questions for the committee: the aim, agents as the product, the user-readable prompt and the `plan` tool. ADR ruling R13 named three; R17 added the second. A draft is at `discussions/2026-11-15-one-page-draft.md`. Ruled 13 November (ADR R34): the orchestrator rewrites it after the fold of that day; the draft there predates the rulings on the replacement, the trigger and the freeze.
- **22 November call:** the ADR, about two pages, is tabled.

**Timing.** ADRs here have been dated Accepted on the day of the call that agreed them (0022 on 26 July, 0035 on 20 September, 0043 and 0044 on 18 October; all Sundays). Members who miss a call may object on the posted minutes within seven days; silence is assent. Assuming minutes are posted on the call day:

| | Optimistic (Accepted at the call) | Cautious (objection window closed) |
|---|---|---|
| Agreed at the 22 November call | 22 November | 29 November |
| Slips one call | 29 November | 6 December |

Each day the minutes are late moves the cautious date by a day. The 8 November minutes were still unposted on 10 November. The week's delay moves no date in the plan.

**If the ADR is not agreed at the first attempt.** Work continues on the branch. Slice 0 and later branch work are shown at calls. No slice numbered 1 merges to `main` (the private fixes and slice 0a do not wait for the ADR), no setting appears in a release, and nobody outside a developer machine uses an agent. The next calls are 29 November and 6 December. If the ADR is amended, the file format and the section order are the parts most likely to change; slices 1d, 1a-1 and 1a-2 are redone. If it is rejected, the branch is kept as evidence and the plan returns to the maintainer.

**The ADR must decide:**

1. File format v1: the fields in A1 only, and the reserved names.
2. That an agent is a new kind of file beside skills, and the revision of DE-211 that follows.
3. The ask-versus-allow rule and the refusal rule, applied to the whole file before the first model call.
4. What records carry; that agent text never enters an audit row (ADR 0016 P3); what deletion does: a version that ran in a matter cannot be deleted while the matter is open, and can be retired (A4); a chat on a retired or deleted agent moves to the default agent, with a line that says so; a paused turn finishes on the version it started with (API R68). That a turn which fails part-way leaves a reply and a record, written together (API R69), and that on an agent turn a successful reply is not saved without its record (V14). That an admin re-run is not wired to agent refusals in Stage 1; audit ruling 13's rule applies once something writes a refusal row (API R30). Ruled 13 November (ADR R32, V29): the ADR has a short "Limits" section carrying four in plain words. The admin re-run is not wired to agent refusals in Stage 1. A version that ran in an open matter is retired, not deleted, and a paused turn finishes on its frozen version. A failed turn leaves a reply and a record written together, and an agent reply is not saved without its record. With agents off a successful turn can still lack its audit row, which ends at the trigger. Also for that section, from other rulings: a paused turn that runs out ends as a failed turn (API R74); the admin re-run is removed at the trigger (API R81); the record keeps only a fingerprint of operator text (V23).
5. That LQ.AI has a system prompt: a visible, versioned file, and who may change it. That a user can read the current text of every authored part of the system prompt: LQ.AI's, the operator's, the agent's and each skill's. For a past turn, the record says which version or fingerprint of each part was used; the text itself can be read back only for agent versions and the LQ.AI prompt. Fixed wording that LQ.AI's own code adds (labels, tool descriptions, the notice at a limit) is in the open-source code, not on the read screen. (Narrowed 13 November.)
6. The system prompt's sections and their order for an agent turn; that agent instructions are a labelled section; that the label is not a guarantee of rank. The citing rule is a part of its own; its place in the order was answered twice on 13 November (API R76, ADR R29) and is not reconciled.
7. That skills are listed and the model loads them; that `load_skill` attaches the skill so the gateway's checks apply; that missing required inputs no longer refuse a skill. This changes ordinary chat too. Required inputs are decided in ADR 0007, which this ADR already amends; an earlier draft of this plan named ADR 0006, which is the document pipeline. Ruled 12 November (B6): this ADR covers the change.
8. That knowledge is a tool for agent turns, and what changes for a chat with no agent: the LQ.AI prompt applies to every chat on upgrade. Two exceptions in Stage 1: the passages the previous reply cited are re-sent in a system message at the start of the next turn (API R72), and the default agent keeps the server fetch until the citations slice merges (API R64). Ruled 13 November (ADR R24, R41): the ADR has one section, "what changes for every chat", naming all of them: the LQ.AI prompt (API R12); the agents setting changing every chat on an install (R20); an upgrade changing the default agent for every chat on it (R35); progress events, Stop and stop-on-disconnect on every tool turn (R36, R46, R66); the removal of the required-inputs check (R11, B6); and the token-and-cost sum (slice 0a). All wait for the ADR and ship when merged in a minor release, each with a release-note line and a line in `docs/HONEST-STATE.md`, except slice 0a, which is on the list but merges when ready (V25). That operators' instructions and the Organization Profile become readable is not on the list: it gets a release-note line only (ADR R30, V28).
9. That each round of the loop is a full gateway request, that a progress event is sent after each round, and the rounds and spend limits, with an unpriced paid route refused where a spend limit is set (API R82).
10. The rule for carrying a knowledge base (slice 2d), or that 2d is outside this ADR.
11. That Stage 1 ships agents behind an off-by-default setting, labelled experimental, with a line in `docs/HONEST-STATE.md`; that the setting is the operator's, and that with it on every chat turn sent through the agent loop has an agent (API R31). Ruled 13 November (ADR R25, R26): that the next minor release after Stage 1 turns agents on by default, unless a stated blocker is open; and that at that point, the trigger, the setting and the old chat path are removed together, with no switch back. Whether "experimental" comes off then was not asked (open question 43).
12. That the server holds a chat's agent, as a pointer to a saved version frozen at the start of each turn. Added from the API ruling of 12 November; confirmed as its own decision on 13 November (ADR R22).
13. That agents shipped in the repo are reviewed like code, not attested, and that a contributed agent whose instructions carry legal substance follows the skills attestation path. (Until 13 November this item was the `plan` tool, which moved to the sub-agents ADR.)
14. That the agent loop replaces the main chat interface, with ordinary chat becoming the default agent. Ruled 13 November (ADR R21, superseding R7): the ADR decides the replacement now, not only the aim. Its conditions are ADR 0038 D7's two tests, which must be shown met before agents turn on by default, and the ADR says where each stands (ADR R27): an agent turn is at least as visible as an ordinary turn (ADR 0038 D2), and the pricing rule of ADR 0035 D6 is resolved for ordinary turns.
15. That no new capability is added to New harness or the legacy planner while Stages 1 to 3 are built; fixes continue (ADR R23). Retiring or rebuilding New harness stays a later decision.

**Ruled 12 November: order and rules in, names out.** The ADR fixes the sections and their order, who writes each, that inputs cannot forge headings, that the model loads skills from a list, and that each round is a full gateway request. Field names, heading text and slice detail stay in the plan and the OpenAPI update.

Decisions 1 to 4, 10 and 11 follow the 8 November direction, which is in draft minutes only. Decisions 5 to 9 follow the maintainer's direction of 10 November on this plan. Decisions 14 and 15, and the trigger in decision 11, follow his rulings of 13 November.

**Where the two trigger tests stand.** The API discussion's report of 13 November: read on `main`, not run. It is a report, not a ruling.

- *Visibility (ADR 0038 D2).* An agent turn is a turn on the same send path. So it keeps the reply row's applied-skills, tier, provider, model, token and cost fields, the chat and message ids on routing-log rows, tool-call rows, audit rows and traces. Gaps: the query embedding's routing-log row is unlinked until slice 1i (API R83); whether the receipts call shows an owner the new fields of an agent turn's record was not read, and that reading is outside Stage 1 (API R65); a refused turn leaves an audit row and no reply. Not checked: traces across tool-loop rounds.
- *Pricing (ADR 0035 D6, "Refuse unknown paid-provider pricing").* Ordinary chat today runs unpriced routes and records no cost. Stage 1 refuses an unpriced paid route only when a spend limit is set (API R82). With none set, the turn still runs. So D6 is applied where a budget exists and not otherwise. Whether that meets the test is the ADR's to say.
- *Receipts.* Answered twice on 13 November and not reconciled: a slice before the trigger (ADR R31), and "rule after the API reports" (V26). Open question 40.

**Existing decisions this ADR touches.** Ruled 13 November: it names them.

- **ADR 0007** (prompt assembly): amended. New request fields, the section order, protected headings, and required inputs no longer enforced.
- **PRD entry DE-388** says that moving untrusted document text out of the system message needs its own ADR and an adversarial evaluation. This ADR is that decision for agent turns (review ruling V2). Its scope narrowed on 13 November: only knowledge returned by `search_knowledge` moves, to a tool result. Attached-file text stays a system message in Stage 1 (API R70), and the passages carried from the previous reply travel in a system message too (API R72). The ADR must say both, and that DE-388 stays open for them and for ordinary chat. It also states the provider limit of API R75 (annex B2). After the trigger ordinary chat is gone, and attached files and carried passages are what stays open. DE-388 lists five points:
  1. *The data channel.* A tool result, for knowledge on agent turns. Nothing else moves.
  2. *How the citation contract survives.* The citing rule is in the system prompt and, as a one-line reminder, in each result (API R62, R63). The reminder is an instruction inside a data message. Ruled 13 November (ADR R33): it is allowed because it is fixed, format-only and measured (annex B4).
  3. *Whether the anonymization skip changes.* Ruled 13 November (V16): the posture is unchanged and the mechanism is stated. Knowledge passages still reach the provider word for word, as Decision M2-1 requires for citation checking. On agent turns that is because chat tool results are not pseudonymized, not because of the skip flag. The flag still covers carried passages and attached files.
  4. *Ordering against replayed history.* Ruled 13 November (V17): left open. The ADR says point 4 is not answered and stays with DE-388. This narrows review ruling V2, which said the ADR answers DE-388's listed points.
  5. *What evaluation result counts as fixed.* Ruled 13 November (V18): the ADR does not claim "fixed". The bar to merge: on the corpus, a model follows an instruction planted in a knowledge passage no more often as a tool result than as today's system message, on `local` and one cloud model. The numbers are published in `docs/security/`.

  The evaluation runs before slices 1f-2 and 1i merge, as ruled. What it has to cover shrank with the scope. Ruled 13 November (V19): its corpus is a small set of planted-instruction cases for knowledge passages only, built in a new Stage 1 slice, kept with the tests and offered to DE-110 later; it does not wait for DE-110's pattern library. The evaluation runs with and without the citing reminder (ADR R33).
- **PRD entry DE-409** already requires an ADR for what is pseudonymized in tool arguments and results. The history tool's cover rule (slice H1a) waits for that ADR.
- **ADR 0015, D1:** the chat loop's tool allowlist gains two built-in tools, `load_skill` and `search_knowledge`, switched on by the operator's agents setting.
- **ADR 0018** (the citation ledger): unchanged. It applies to agent turns: citations are carried through `search_knowledge`, and today's checker and ledger are used as they are (API R50, R63). How the citation contract survives relocation is point 2 in the DE-388 line above.
- **ADR 0038, D2 and D7, and ADR 0035, D6.** D7's two tests are conditions of the trigger (decision 14). ADR 0038 is Proposed.
- **Not put to the maintainer:** ADR 0025, which routes a breaking change to a minor release with a label, and removing the setting and the old chat path is one; ADR 0029, the definition of 1.0, which uses "experimental" as a label; ADR 0031, headless API use, since an API-only client that sends a chat message gets the default agent after the trigger. Read by search, not in full, by the ADR discussion. Open question 44.

It decides that New harness is not the base (ADR ruling R6) and, since 13 November, the freeze (decision 15, ADR R23).

**It must not decide:** sub-agents, the `plan` tool included; the contributed-agents slices; whether New harness is retired or rebuilt; the agent's own workspace; the history tool and the per-tool cover rule (H1); whether a file may mark a skill always-loaded.

**Committee items:**

- this ADR;
- ratification of ADR 0016, as it stands on `main`: a second item on 22 November;
- an amendment to PRD section 1.3, which says "the skills are the product": the maintainer's direction of 12 November is that agents are the product;
- a PRD entry revising DE-211, which names an "extension of skill format" but scopes the runtime to OpenWebUI Pipelines;
- withdrawal of the earlier drafts' items: a mandatory `main` agent, replacing ordinary chat, finishing New harness under DE-412 and DE-415, foundation packages. Since 13 November "replacing ordinary chat" is not withdrawn: the ADR decides it (decision 14, ADR R21). The built-in default agent ruled on 12 November stands where "a mandatory `main` agent" stood;
- changing the stock `local` model in `gateway.yaml.example` to Gemma 4: a security-path change separate from this ADR, after Slice 0. Not yet ruled;
- **the Stage 4 amendment to ADR 0035 D8b.** D8b's subject is a skill that opts into storage "scoped by exact skill identity". A store whose owner is an agent, with no skill opting in, changes that subject. This plan reads it as an amendment, not a clarification. The reading is the maintainer's to confirm;
- the ADR that PRD entry DE-409 requires for covering a named tool's results on a pseudonymizing route (H1);
- the sub-agents ADR, which also decides the `plan` tool (ruled 13 November);
- a Labs ADR;
- the later decision on New harness (F).

DE-420 stays filed and undecided. ADR 0038 stays Proposed; its ratification issue (#726) is not touched by this plan.

**Review.** **[S]** slices touch authorization, audit logging, `api/app/skills/**` or `gateway/**` and take the security-path checklist. The sole maintainer's own pull requests merge under the logged bypass in ADR 0034, so the limit is his hours.

## F. Engines and what stays frozen

The agent file adds no engine. **The ordinary chat tool loop is the agent engine.** The file decides what the loop is given: the system prompt, the skills list, the tools. Today there are three loops (ordinary chat, the run tree's sub-agent loop, the legacy matter planner) and four kinds of tool (DE-416 names three paths; skill tools are a fourth).

| Stage | Loops | Change |
|---|---|---|
| Today | 3 | New harness is merged and off by default. Not verified: its server release; whether the legacy planner has an off switch |
| 1 | 3 | Agent turns run in the chat loop. New tool kinds in chat: `load_skill` and `search_knowledge`. The loop runs whenever the agent offers a tool, which is nearly always (A2). On an install with agents off, chat is as today: the loop runs only when a tool is offered, otherwise one streamed call. With agents on, a chat with none chosen runs the default agent. The release after Stage 1 turns agents on for every install and removes the agents-off path (ADR R25, R26) |
| 2–4, H1 | 3 | More tools in the same loop: connectors by name, `search_history`, the workspace tools. Slice 3e streams the last round |
| Sub-agents | 3 | One more tool kind, `delegate`. This is a second place sub-agents run, beside the run tree. The ADR must say so |
| Later | 3 or fewer | **Decision point**, a committee item, after sub-agents have been in use for one release: retire New harness and the legacy planner, or rebuild them on the chat loop |

"Frozen" means no new capability is wired into the run tree or the legacy planner. Bug and security fixes continue. No fourth loop is built. Ruled 13 November (ADR R23): the freeze is a decision of the ADR, for as long as Stages 1 to 3 are built. What a New harness run is after the trigger, when every chat turn has an agent and its runs have none (API R31), is not ruled (open question 44).

**Why the run tree is not the host.** Five reasons:

- Its profiles are code, looked up in about ten places across two processes. They are not data a builder can write.
- Its top level can only propose a plan. It has no tool loop.
- New tools for it wait on an access module that is not built.
- It allows one active run per person, and a user cannot attach a library skill to it.
- Using it would need amendments to ADR 0035 and ADR 0038.

What New harness proved, a governed run inside a chat, is the evidence the sub-agents ADR will draw on. Further points:

- *Why not call the run tree as one tool from chat?* ADR 0038 itself rejected letting the chat model start a run through a tool call, because planning would run before any allowance is disclosed. The run tree also allows one active run per owner.
- *Why can the run tree's answers not be reused?* Its answers to tier, budget and pause questions rest on plan approval and durable effects. The chat loop has neither. The trial (D) finds what the chat loop needs in their place.
- *Does New harness have a skill loader to reuse?* No: its prompts are versioned files (`api/app/autonomous/orchestration/new_harness.py:96-99`). Its knowledge tool is not ported (B4).

A builder cannot build a New-harness-style plan-then-execute run under this plan. The nearest thing is a lead agent with sub-agents. A shipped `main` example, a lead with sub-agents, may follow the sub-agents build. It is an optional agent in the list, not the default, and nothing depends on it.

## G. Why earlier attempts stalled

| Pattern in the six earlier attempts | This plan |
|---|---|
| Scope grew with each draft, up to replacing chat | It grew here too. Draft 4 was a builder beside chat. Since 12 November the default agent replaces ordinary chat on an install with agents on (API R20), and since 13 November the ADR decides the replacement itself, with a trigger one release after Stage 1 (ADR R21, R25, R26). Cuts are listed |
| Many decisions, some reversed within days | One ADR for Stages 1 to 3, which since 13 November also decides the replacement, the trigger and the freeze; the other committee items are listed in E |
| Documents, no running code after mid-October | Slice 0 runs before the ADR is tabled; the trial runs before the sub-agents ADR |
| Each layer rested on something unratified | Stage 1 rests on one ADR, which itself follows draft minutes. Also unsettled: the shell, D8b |
| Work ran in series through one person | Still true for Stage 1. The trial and L1 can go to a volunteer from December |
| Names and numbers changed meaning | Slice 0, Stages 1 to 4, H1 and two named tracks; the ADR takes its number when opened. Draft 4 relettered Stage 1's slices; draft 3's letters are retired |
| Draft 3 assumed today's chat turn underneath the file | The maintainer corrected the shape on 10 November. Draft 4 keeps the file, ask versus allow, refusal and records, and rebuilds the turn. Cost: Stage 1 was nine days longer in draft 4. The rulings of 12 November added about 26.5 more |

**What we stop doing:** designing the end state before the first slice runs; writing a decision for something unsized; adding capability to New harness or the legacy planner; counting volunteers who have not come forward; reusing a stage name for a different thing.

## H. Sources

- **Governance:** GOVERNANCE.md (rules 1 and 3; the seven-day rule; Sunday calls); CLAUDE.md "Security-sensitive paths"; CONTRIBUTING.md; `skills/CONTRIBUTING.md`; `docs/ROADMAP.md`.
- **ADRs:** 0007 (section 2, required inputs; amended 2 September 2026), 0015 (D1), 0016 (P3, P5), 0022, 0025 (a migration is not a patch), 0030 (reported), 0034, 0035 (D6, D8b), 0037, 0038 (Proposed; D2 and D7; the direction of 7–8 October), 0043 and 0044 (Accepted), 0018 (the citation ledger), 0045 (in open PR #804).
- **PRD:** section 1.5.2 (tiers); DE-110, DE-211, DE-388, DE-408, DE-409, DE-412, DE-415, DE-416, DE-420.
- **Tiers and the example:** `gateway/app/tier_floor.py:60-64` (a lower tier number is the stronger tier; a request is refused when its tier is weaker than the minimum); `gateway.yaml.example:93-97` (`anthropic-prod` is tier 4), `:201` (`ollama-local` is tier 1), `:305-354` (aliases), `:431-436` (default minimum tier 4; privileged 3); `skills/nda-snapshot/SKILL.md:21-23` (table mode; needs tier 2); `gateway/app/skills/assembler.py:369` (a skill contributes its body); `docs/quickstart/sample-ndas/`.
- **How a turn is built today (draft 4; read, not run):**
  - Messages: `api/app/api/chats.py:1659-1766` (knowledge block `:1676-1682`, attached files `:1715-1727`, history `:1764`); history window `:240-303` and `api/app/config.py:174-194`; chat search endpoint `chats.py:807-830`.
  - Knowledge: `chats.py:1189` (`_retrieve_kb_context_for_chat`), called at `:1649`; its audit row `:1687-1701`. New harness's tool: `api/app/autonomous/orchestration/tools.py:376-505`.
  - Gateway assembly: `gateway/app/api/inference.py:394-500` (early return with no skill `:424`; the join `:476-482`; one system message `:490-491`); `:627`, `:661` and `:701-710` (assembly, tier check and pseudonymization, in that order); `gateway/app/skills/assembler.py:102` (operator heading), `:112-116` (protected headings), `:369`, `:378-380`, `:385-397` (body, reference files, on-demand list), `:464-484` (required inputs), `:500-505` (skills first, then the joined text); `gateway/app/tier_floor.py:86, 119`; `gateway/app/providers/openai_schema.py:85`.
  - Tools and the loop: `api/app/chat/tool_schemas.py:212-246` (four tool kinds); `api/app/skills/chat_tools.py:16-22, 74-75`; `api/app/chat/tool_loop.py:787` (the loop), `:875` and `:1014` (cap), `:680-687` (dispatch), `:1004-1011` (after a round with no counted call, one last no-tools round), `:1033` (last round, tools off), `:1058-1082` (each round a full, non-streaming request), `:1101` (only the final response is surfaced); `chats.py:1861` (skill tools added once), `:3249, 3668` (loop only when a tool is offered), `:3698` (final text in one piece), `:2130-2148, 2426-2441` (pause and resume); `api/app/config.py:505-507` (cap, default 8).
  - Pseudonymization and tools: `gateway/app/anonymization/middleware.py:141-145, 155-167, 337-349`; the switch is set only under `api/app/autonomous/` (`orchestration/effects.py:384`, `guard.py:2328`).
  - Local models and tools: `gateway/app/providers/ollama.py:501-511` (tools passed), `:566, 633-651` (tool calls returned).
  - Workspace and New harness: ADR 0035 D8b (`docs/adr/0035-governed-orchestration-run-tree.md:122-133`); `api/app/skills/workspace.py`; `api/app/config.py:557`; `api/app/autonomous/orchestration/new_harness.py:96-99`.
- **Other code opened:** `api/app/schemas/chats.py`; `api/app/chat/tool_schemas.py:244-330`; `api/app/mcp/service.py:136` (connector tools ask for confirmation by default); `api/app/autonomous/orchestration/profiles.py:305-316`; the gateway's model listing and four provider adapters. Other code facts are reported from private notes.
- **Run, not read (two probes):**
  - `research/2026-11-12-local-tool-probe.txt`: `gemma4:26b` and `gemma4:e4b` called `load_skill` when a skill was needed and not otherwise, three runs each, direct to Ollama and not through the gateway.
  - `research/2026-11-13-failed-turn-probe.txt`: what the send handler writes when the loop fails, when the audit write fails and when the client disconnects. Run by the API discussion on a clean copy of `main` at db379f26f, with a throwaway Postgres. The loop was replaced by a stub; no gateway, no model. Not covered: a disconnect on the non-streaming path, a real loop failing after real tool calls, the single-shot path with no tools.
- **Issues and pull requests:** #563, #599, #662, #725, #726, #794–#799, #802, #804, #815.
- **Committee:** published minutes to 1 November 2026; draft minutes of 8 November, not yet published.
- **Research and review:** six private maintainer notes, three reviews of draft 1 and two of draft 2. Not linked here. Paths in this plan that begin `discussions/`, `research/`, `reviews/` or `build-plan/` are in the maintainer's private working folder, not in this repository.

## I. Slots, stages, dates and this week

Moved from the main plan on 12 November, when it was cut. Stage 1 was redone on 12 and 13 November by a separate build-plan session. Its slices, sizes, order and dates are that session's estimates; the eight rulings the maintainer made there are marked B1 to B8. Stages 2 to 4 are not re-sized. File paths, code facts and the survey of what else is moving are in `build-plan/build-plan.md`, which is outside this plan.

### The seven slots

| Slot | What a builder gets | Stage | Indicative date (ordering A) |
|---|---|---|---|
| Model and instructions | The agent asks for a model; the matter's tier still decides | 1 | late May 2027 |
| Skills | A list the model loads from. All 17 built-in skills can be listed, and any of the user's own: missing inputs no longer refuse a skill | 1 | late May 2027 |
| | The model supplies a skill's inputs as arguments when it loads (slice 2h, to re-scope) | 2 | early July 2027 |
| Knowledge | A search tool over `matter`; or `none` | 1 | late May 2027 |
| | Pick among the matter's knowledge bases; carry one of my own | 2 | early July 2027 |
| Tools | "What chat offers here", written as `tools: chat` | 1 | late May 2027 |
| | Narrow to none, research, authority sources or named connectors | 3 | late July 2027 |
| History | A tool that finds earlier messages of this chat that no longer fit in the request | H1 | not before mid-August 2027 |
| Workspace | Tools to list, read and write files the agent keeps for itself in a matter, across chats | 4 | early September 2027 |
| Sub-agents | A `delegate` tool: hand a task to another agent | own track | mid-November 2027 at the earliest |

**Four words, kept apart.** *Knowledge* is documents you attach. *History* is this chat's earlier messages. *Workspace* is files the agent writes and reads back. *Longer-term memory* across matters has no design and no date.

A builder cannot install a connector; the operator does.

### Stages

One pull request is about 400 changed lines at most. **[S]** marks a security-path slice, which needs the maintainer.

#### Stage 1 — An agent file runs in chat

| | |
|---|---|
| Goal | A person pastes or uploads a file and uses it in chat. The model picks its skill and searches the matter |
| Effort | 31 slices, about 8,550 lines, 48 days, plus 2 days for Slice 0 and 2 of preparation. Draft 7 said 14 PRs, 4,100 lines and 21.5 days. The private fixes are in no figure |
| Needs to merge | The three privately tracked fixes, first (B5). A fourth was put on the private track on 13 November (V20); it is not sized, and whether B5 covers it is not ruled. The ADR ([annex E](#e-governance-path)), for every slice numbered 1 and for 3e. For the screens, the shell cutover (PR #815) on `main` (B2). A minor release: 1e is a migration, and 1b and 1r change every chat |

**Ruled for the build, 12 November.** B1 to B8, in the maintainer's words in `build-plan/rulings.md`.

- **B1.** There is no early usable point. Nobody is told agents are usable until everything ruled into Stage 1 is on `main`. Put to the maintainer at about 46 days and mid-May.
- **B2.** The agent screens are built after the shell cutover (PR #815) is on `main`. Gateway and backend slices go first.
- **B3.** Slice 3e moves into Stage 1. Ruled 13 November: agents are announced as usable after 3e, so Stage 1 has one end (review ruling V9, confirmed by API R68, which withdrew R58). The build-plan session had read B1 with B3 as: usable before 3e.
- **B4.** Stage 1 is finished before Stage 2 starts.
- **B5.** The private fixes go first, while the ADR is pending. Their days are not sized and come out of the same 8 a month.
- **B6.** The LQ.AI prompt for every chat and the removal of the required-inputs check wait for the ADR. Then each ships in the next release cut after it merges, which becomes a minor release with a line in the release notes. That line does not yet say that operators' instructions and the Organization Profile become readable by their users, which the interface discussion asked operators to be told. Ruled 13 November (ADR R30, V28): operators are told by a release-note line only. Ruled the same day (ADR R24, R41): the full list of every-chat changes is in annex E decision 8.
- **B7.** Ordering A: builder first.
- **B8.** One migration, in slice 1e. It also carries the Stage 2 scratch-chat flag.

**The slices below are a build-plan session's estimates, not rulings.** No code was written or run for them.

- **Lines.** Each slice starts from Draft 7's figure for its parent, spread across the split. Work the rulings added is sized from the call sites read on `legalquants/main`.
- **Days.** Draft 7's rates, which nobody has tested: a security-path slice takes one day per 160 lines, to the nearest half day and at least one day; any other backend slice, 1 day; an interface slice, 1.75 days.
- **In no figure:** the private fixes, rebases, review of contributor slices, committee and release work, and the redesign itself.
- **Web slices** rest on a survey of the redesign that a sub-agent made by reading. Nothing was built or merged to check it.

**Slice 0 is not 0a or 0b.** Slice 0 is this week's throwaway branch and never merges. 0a and 0b are real slices that merge to `main`.

**On `main` before the ADR**

| Slice | What | Lines | Days | Needs |
|---|---|---|---|---|
| 0a **[S]** | The token-and-cost sum (API R29, audit 5). The loop adds up each round's tokens and cost. The totals go on the reply row for every tool-loop turn. A paused turn carries its running totals | 250 | 1.5 | nothing |
| 0b | The loop hands control back after each round. No behaviour changes. Progress events, stop, the limits and `load_skill` all need it. Whether it may merge before the ADR is asked, not ruled | 200 | 1 | 0a |

**Gateway, after the ADR**

| Slice | What | Lines | Days | Needs |
|---|---|---|---|---|
| 1a-1 **[S]** | Assembly runs for a chat request with no skill. The `lq_ai_assembled` object on the response and on each stream chunk, filled with today's parts. A field by which the chat send path marks a chat turn: other callers use the same endpoint, and the LQ.AI prompt must not reach them. Ruled 13 November (API R32): a new field, separate from the purpose tag; its name is not ruled. Fingerprints are over saved text: a skill's is over the skill as saved, not as rendered (API R67). Since 13 November: assembly no longer joins other system messages under the operator heading, so document text goes as a system message of its own (API R75); the Organization Profile is a part of kind `organization_profile` (V22) | 300 | 2 | the ADR |
| 1a-2 **[S]** | The agent section: a field for the agent's instructions and one for where the server loaded it from; the label; the section order; headings that inputs cannot forge. The gateway reports a fingerprint of the instructions it was sent, as `agent_instructions_sent_fingerprint` (API R67, V22) | 250 | 1.5 | 1a-1 |
| 1b **[S]** | The LQ.AI system prompt: a versioned file, its section for every chat, its part in `lq_ai_assembled`, and a call that returns its text to a signed-in user. Where the file lives is asked, not ruled | 200 | 1 | 1a-1; the maintainer's text |
| 1c **[S]** | The skills list: a field of listed names, each rendered as name and description, and its part in `lq_ai_assembled`. `docs/api/gateway-openapi.yaml` | 200 | 1 | 1a-2 |
| 1r **[S]** | The required-inputs check is removed everywhere (API R11) | 150 | 1 | the ADR (B6) |

**Backend, after the ADR**

| Slice | What | Lines | Days | Needs |
|---|---|---|---|---|
| 1d | File format v1: parser, validator, fingerprint; no `author` field (API R43; the slice was sized as if there were one); two example files; the default agent file, with no `model` line, no skills, `tools: chat`, named `lq-ai`, titled "LQ.AI", empty body. It ships with `knowledge: none` and changes to `[matter]` when the citations slice merges (API R52, R61, R64) | 380 | 1 | the ADR |
| 1e | One migration (B8): the versions table; the chat's agent pointer; the reply's agent id and version; how a reply ended, one of seven values (API R79); the hidden-chat flag for Stage 2's tries, which must also be found by agent and user (API R73). `docs/db-schema.md`. Since 13 November also a retired state, the name kept after deletion, and the shipped default agents' texts (API R35, R55); not re-sized | 400 | 1 | 1d |
| 1j | Agent endpoints: save from text, list (the default agent first, marked `is_default`; API R42), read, download, retire, delete. Deleting a version deletes the hidden try chats that ran it, and a version used only in tries can be deleted while its matter is open (API R78, V27) | 300 | 1 | 1d, 1e |
| 1f-1 **[S]** | The agents setting. Chat create and chat update take an agent version; chat read returns the agent and whether a newer version exists (`newer_version`; API R42; none for the default agent, API R35). With agents on, none chosen means the default agent. The `docs/HONEST-STATE.md` line. When a chat's agent is retired or deleted, the fall-back to the default agent writes a `chat.agent_reassigned` audit row in the same write (audit 14, API R84). API R67 changes nothing here; it named this slice in error (an API note of 13 November) | 300 | 2 | 1e, 1j |
| 1f-2 **[S]** | The send path. The chat's agent is read and frozen for the turn; the gateway fields are set; the request's model is optional and has no default on an agent turn (API R33); no knowledge fetch before the model on agent turns, except on the default agent until the citations slice merges (API R64); attached-file text stays a system message (API R70); the pointer on the reply row | 350 | 2 | 1f-1, 1a-2, 1c; the DE-388 evaluation |
| 1f-3 **[S]** | The record for turns that run straight through. The audit row gains the agent's id, version and file fingerprint, from the store, and the gateway's parts for each round, among them the gateway's own fingerprint of the instructions it was sent (API R67). It carries the file's model beside the model that ran, and the LQ.AI prompt's version on every chat turn (API R47) | 200 | 1 | 1f-2, 1b |
| 1g-1 **[S]** | The check, as one function: the file against the operator, the matter and the user, giving each item a state and a reason. A read-only call that returns those states for an agent in a matter: `POST /agents/{id}/versions/{n}/check`, with the same item list a 409 carries (API R48, which counts this call as new and unsized) | 300 | 2 | 1d |
| 1g-2 **[S]** | The refusal. The check runs before the message is saved; a 409 lists the items; `run_without` on a resend; at most 16 skills; skills attached by hand in the same check and the same 409 (API R40); inline skill text refused only where the user chose the agent (API R34); `run_without` never names the model (API R53); one audit row per refusal, action `agent.turn_refused` (audit 11, API R45); with a spend limit set, an unpriced paid route is refused here, naming the model (API R82) | 300 | 2 | 1g-1, 1f-2 |
| 1n | Progress events at the start and end of each step (API R39), names and counts only, on a streamed send and on a resumed turn. For every tool turn, agents on or off (API R36). Not re-sized | 250 | 1 | 0b |
| 1p **[S]** | The two limits on agent turns: rounds, 20 by default, and an optional spend limit, both operator settings; the file may lower the rounds. One last round with tools off; the reply row and a progress event say which limit ended the turn | 250 | 1.5 | 0a, 0b, 1e, 1f-2 |
| 1o **[S]** | Stop between rounds: a stop call; the loop checks at each round boundary; the reply is saved as stopped with what was gathered; the record says so, and whether the user or a closed connection stopped it (audit 16). Ruled 13 November (API R46): the stop call and a closed stream ship together in this slice, which starts by verifying what a closed stream does today. A probe on 13 November showed it on the streamed path, with the loop replaced by a stub: the loop is cancelled and nothing is saved (annex H). Ruled (API R66): the loop is protected from the connection closing; the round in flight finishes, and the reply and record are saved as stopped. A stopped reply always has text (API R37). For every tool turn (API R36). Not re-sized | 350 | 2 | 0b, 1e, 1n |
| 1h **[S]** | `load_skill`: attaches a listed skill for the following rounds, brings its tools, writes a tool-call row, survives a pause with the frozen agent reference and the agent's instructions beside it (API R68). Uses the governed entry point; provider name `lq-ai` (API R45). Adds a gateway test for placeholder renumbering after a load (API R38) | 350 | 2 | 1c, 1f-2, 1g-2, 1p |
| 1i **[S]** | `search_knowledge`: a chat tool over chat's own retrieval, with an audit row and a tool-call row for every search, empty ones included. On a pseudonymizing route the query goes as the model wrote it until H1. Results are numbered passages, each with a one-line reminder of the citing format (API R62, R63). The rest of citations is a slice of its own, with or straight after this one (API R64); not sized. Since 13 November the search's audit row names the embedding's provider and tier, or "keyword only", and the tool sends the turn's chat and message ids with the embeddings request for the gateway to write on its routing-log row: a gateway change (audit 15, API R83). Not re-sized | 300 | 2 | 1f-2; the DE-388 evaluation |
| 1l-1 **[S]** | Records on turns that pause for a tool confirmation, and on their resumed turns. The paused turn's saved state carries the agent's instructions (API R68) | 220 | 1.5 | 1h, 1f-3 |
| 1l-2 **[S]** | Records on turns that pause for a connector sign-in. The documentation, `docs/security/audit-logging.md` and `docs/compliance/`, with the admin re-run limit as reworded (audit 13). The change to the override handler has no slice yet | 200 | 1 | 1l-1 |

**Screens, after the shell cutover is on `main` (B2)**

| Slice | What | Lines | Days | Needs |
|---|---|---|---|---|
| 1k | The Agents page: list, paste, upload, View file, Download, Use in chat (starts a new chat set to that agent), labelled "experimental". The one way into editing an agent or copying one (interface ruling, 13 November); its "Edit" and "Make a copy" controls are not drawn yet (parked). A row in the sidebar; where it sits is asked, not ruled | 300 | 1.75 | 1j, 1f-1 |
| 1m-1 | The agent pill in the message box: it opens a list and edits the chat. It only switches agents, with no edit or copy entry (interface ruling, 13 November). The default agent's screens (mockup boards 9 to 11). The model picker may send nothing when the user has not picked (API R33). On every agent chat it returns after each send, to the file's model or, on the default agent, the install's default: a picked model lasts one turn (interface ruling, 13 November) | 350 | 1.75 | 1f-1, 1j |
| 1m-2 | A pill on every reply, and a line where the agent changes | 250 | 1.75 | 1f-2 |
| 1m-3 | Live step lines; the "limit reached" and "stopped" marks; a Stop that waits for the round | 300 | 1.75 | 1n, 1o, 1p |
| 1m-4 | The refusal notice, built from the 409's list, with "run this turn without it" | 250 | 1.75 | 1g-2 |
| 1m-5 | The "newer version" line above the message box, with the control to move and a dismiss. Every saved version raises it (API R41); none for the default agent (API R35) | 200 | 1.75 | 1f-1 |
| 1m-6 | Reasons and tiers on the agent's page; loaded skill names under each reply. Searches appear as live step lines while the turn runs (slice 1m-3) and are not kept under the reply in Stage 1 (review ruling V6, API R65) | 300 | 1.75 | 1g-1, 1h, 1i |
| 1m-7 | The read screen: the LQ.AI prompt, the operator's instructions, the Organization Profile. What the operator row shows is asked, not ruled. Ruled 13 November (interface): reading the operator instructions and the Organization Profile is a Stage 1 slice of its own, with one read call (API R56), so it can be reviewed, and dropped, on its own. The maintainer confirmed the same day that this is that slice, and none is added (V15) | 300 | 1.75 | 1b |

**Last in Stage 1 (B3)**

| Slice | What | Lines | Days | Needs |
|---|---|---|---|---|
| 3e **[S]** | The last round of a loop turn streams word by word. Not verified that this fits one PR. Ruled 13 November (API R59): every round is requested from the gateway as a stream. Text is passed to the browser as it arrives; if the round turns out to be tool calls, nothing was shown. The gateway's last chunk of each round carries that round's cost, so the sum and the spend limit stay right. A gateway change; to be re-sized | 300 | 2 | 0a, 0b, 1n |

**Totals.** 31 slices, 8,550 lines, 48 days. By kind: 17 security-path slices, 27 days; 5 other backend slices, 5 days; 8 screens, 14 days; 3e, 2 days (marked security-path on 13 November; its days are unchanged). Without 3e: 30 slices, 8,250 lines, 46 days.

**48 days is a floor.** Four slices of 200 lines (1b, 1c, 1f-3 and 1l-2) fall exactly between 1 and 1.5 days at the rate above and are counted at 1; counting them at 1.5 adds 2 days. And the work below has no slice and no size.

Ruled, not yet sliced:

- citations on agent turns: the passage list kept by the loop and saved with a paused turn, the check at the end, the citing rule as a prompt part, and the previous reply's cited passages carried into the next turn (API R50, R62 to R64, R71, R72, R76, R80). The carried block's header loses the rule, passages are carried only when the agent can search knowledge, and the record lists them by count and source ids (audit 17). A security-path slice, with or straight after slice 1i;
- a reply and a record for a turn that fails part-way, written together (API R69): a security-path slice. The same slice makes a successful agent turn's reply and record one write (V14), and closes a paused turn that runs out as a failed turn (API R74);
- protecting the loop from a closed connection, inside slice 1o (API R66);
- carrying the agent's instructions in a paused turn's saved state, inside slices 1h and 1l-1 (API R68);
- the adversarial evaluation that DE-388 requires, before slices 1f-2 and 1i merge (review ruling V2), and before it a new slice that builds its small corpus of planted-instruction cases (V19). The ADR discussion's guess for the corpus is two to three days; it is not an estimate;
- a retired state for agents, the name kept after deletion, and the move to the default agent (API R49 and R55; review ruling V11);
- keeping each shipped default agent's text in the store (API R35);
- removing the old chat path, in the release that turns agents on for every install (ADR R25, R26). By the API discussion's report, read and not sized, it covers: the server-side knowledge fetch and its call (the block formatter stays, because carried passages use it); the agents-off branches of the send path, non-streaming and streamed, and the single-shot path with no tools; the cap of 8 tool calls and its setting; the agents setting and V14's exception; the admin re-run (API R81); and the tests and API documents for all of these. Its guess is 2 to 4 days, not an estimate. It is after Stage 1 and in no figure; its place in the order is open question 41;
- the check as a call of its own, where it is more than slice 1g-1 already holds (API R48);
- the web chat's input form once the inputs check is gone (open question 27);
- the PRD, OpenAPI and audit-logging documents that go with each change, where a slice does not already name them;
- the exit-test steps listed below.

Slices 1a-1, 1e, 1f-1, 1g-2, 1h, 1i, 1j, 1l-1, 1n and 1o also grew on 13 November and are not re-sized.

Moved out of Stage 1 on 13 November: extending the receipts call so a chat's owner reads a turn's record (API R51, R65). Where it goes was answered twice later that day and is not reconciled: a slice after Stage 1 is announced and before the trigger (ADR R31), and "rule after the API reports" (V26). No slice or size is added here.

**25 May is a merge date.** It is when the last Stage 1 slice merges to `main`, and when agents are announced as usable. No release is tied to it, and the roadmap's Candidate train (30 April) falls before it. An operator gets agents from the first release after it. Ruled 13 November (ADR R25, R26): that release ships agents off by default; the next minor release, the trigger, turns them on for every install unless a stated blocker is open, and removes the setting and the old chat path. Neither release has a date.

**The order.** One person builds this, so the order is one queue. Branch work waits for nothing; the gates are gates on merging.

| Step | Slices | Merges when |
|---|---|---|
| 1 | Slice 0; the one page for 15 November; the ADR's pull request; the LQ.AI prompt's first text | never (Slice 0), or as documents |
| 2 | The three private fixes; a fourth was added on 13 November | now, through the private channel (B5); whether B5 covers the fourth is not ruled |
| 3 | 0a, 0b | now for 0a; 0b is asked, not ruled |
| 4 | 1a-1, 1a-2, 1b, 1c, 1r | after the ADR |
| 5 | 1d, 1e, 1j | after the ADR |
| 6 | 1f-1, 1f-2, 1f-3 | after the ADR |
| 7 | 1g-1, 1g-2 | after the ADR |
| 8 | 1n, 1p, 1o | after the ADR |
| 9 | 1h, 1i | after the ADR |
| 10 | 1l-1, 1l-2 | after the ADR |
| 11 | 1k, 1m-1 to 1m-7 | after PR #815 is on `main` (B2) |
| 12 | 3e | after step 11 (B3). Agents are announced as usable here |

**A contributor could take,** each on their own fork and each adding a maintainer review: 1j; 1n once 0b is on `main`; the stream half of 1m-3; 1k, 1m-2, 1m-5 and 1m-7 after the cutover, if someone can review interface slices (open question 3); L1 once 1d is on `main`. Not for a contributor: the 17 security-path slices, 3e, 0b, and 1m-1, which edits a message box the redesign will rebuild.

**Exit test.** On the stock `gateway.yaml.example`: Ollama serving the `local` models; the Anthropic and OpenAI keys set (the stock example embeds knowledge through OpenAI); the agents setting on; an ordinary matter with the five sample NDAs in an attached knowledge base.

1. Paste the example. It saves as version 1. Set it on a chat and ask for the comparison. The reply comes from `local` (tier 1; `nda-snapshot` needs tier 2 or stronger). The record shows the LQ.AI prompt's version, `nda-snapshot` offered, and `load_skill` and `search_knowledge` among the tools. View file and the audit row show the same id, version and file fingerprint. The gateway's fingerprint of the instructions it was sent is a separate entry and is not compared (API R67).
2. If the model called `load_skill` and `search_knowledge` on that turn, the record lists `nda-snapshot` as loaded, with its fingerprint, and each search has an audit row, empty ones included. If it did not, that is a finding about the model, and it is written down.
3. Paste the file again with `model: smart`. It saves as version 2. Send: the chat is still on version 1 and replies from `local`. Move the chat to version 2 and send again. The turn is refused before any model call: "`nda-snapshot` needs tier 2 or stronger; `smart` is tier 4". No message is saved, and the refusal has an audit row of its own that names the agent, the item and the reason. Choose "run this turn without `nda-snapshot`". The reply comes from `smart`, the skill is not on the list offered, and the record shows the choice.
4. Paste it with `workspace: own`. Save is refused: "reserved".
5. With one test connector installed (the stock example has none): load the skill, trigger a tool that asks for confirmation, and approve. The resumed turn still has the skill loaded, and its record has the same version.
6. Setting off: setting an agent on a chat is refused, and chat gets its knowledge the old way and still streams. Setting on: a chat with no agent chosen runs the default agent, and its record names it.

**Steps the rulings need, none written yet:** a turn that reaches the rounds limit; a turn that is stopped; a chat moved by the "newer version" line; step lines seen on a streamed turn; the read screen; an answer that arrives word by word (3e); a reply row whose cost is the sum of its rounds; a send through the API with no model, answered from `local` (API R33); the reply's quotations shown as verified citations that open on the source passage (API R50); with agents off, a matter with knowledge and a file attached: the response lists the LQ.AI part, and a quotation from a passage comes back exactly as written (API R36); a playbook run, a tabular extraction, a citation check and a prompt enhancement each show no LQ.AI part (API R32); a follow-up that quotes a passage the previous reply cited, with no new search (API R72); a turn whose model call fails part-way, leaving a reply row with the error and a record (API R69); a tab closed mid-turn, leaving a reply saved as stopped (API R66); an agent deleted while its turn is paused, and the turn still finishes (API R68); an agent turn whose audit write fails: no reply is saved and the user sees an error (V14); a pause left to run out, closed as a failed turn (API R74); with a spend limit set, a turn on an unpriced paid route refused at the check (API R82); a chat whose agent is deleted, with a `chat.agent_reassigned` row at its next turn (API R84); a search whose audit row names its embedding provider and tier (audit 15); a try in a matter, and its version then deleted while the matter is open (V27).

#### Stages 2 to 4, and the history tool

Slice tables and full exit tests: [annex C](#c-slices-for-stages-2-to-4-the-history-tool-and-contributed-agents).

| | Stage 2: build on screen | Stage 3: tools | H1: history tool | Stage 4: own workspace |
|---|---|---|---|---|
| A person can | Build, try and save an agent without writing a file; import a Claude Code agent | Name the agent's tools; see what the operator offers | Have the agent find something said earlier in a long chat | Have an agent keep notes in one chat and read them in another chat of the same matter |
| Effort | 8 PRs, 2,550 lines, 12.5 days | 4 PRs, about 900 lines, 6 days (3e moved to Stage 1) | 2 PRs, 450 lines, 3.5 days | 4–5 PRs, 1,100–1,300 lines, 7 days |
| Needs to merge | Stage 1 | Stage 2 slices 2a and 2e | Stage 1; a rule for covering this tool's results on a pseudonymizing route | Stage 1; the Stage 2 screen; an amendment to ADR 0035 D8b (a committee item); a minor release |

**Why the history tool waits.** Earlier messages are pseudonymized today because they travel as messages; tool results are not. H1 covers this tool's results at the gateway, or it does not ship. Three conditions, all required: a per-tool rule at the gateway that covers this tool's results; a gateway test proving a history result left the deployment pseudonymized; a tool-call row and an audit row for every search, with counts only. Until then `history` stays a reserved field.

### Sub-agents and contributed agents

**Sub-agents:** a `delegate` tool in the same loop. `delegate` is a tool that lets a main chat create a sub-agent. A sub-agent is a turn built the same way from another agent file. The path is unchanged: a throwaway trial (3 days, never merged), an ADR written from what it showed, then the build. The build is unsized until the trial; 14 days is a low guess. Specification: [annex D](#d-sub-agents-trial-specification).

**The `plan` tool.** `plan` is a tool that creates a plan (markdown or something else), which the chat itself follows and updates. The user approves its plan. Ruled 13 November: that the tool exists, and that approval, are decided in the sub-agents ADR, not on 22 November. A plan is a document that belongs to the chat, stored by the server and shown in the chat; the agent updates it across turns. It is on this track: it arrives with `delegate`, after the trial, and is not in Stages 1 to 4. Its design, its size and how an approval is recorded are not ruled and wait for the trial.

**Contributed agents** are files added by pull request and reviewed like code. One whose instructions carry legal substance follows the skills attestation path (ruled 13 November). Four slices, 4 days. The first, L1, is a folder and a validity check.

**Neither the trial nor L1 is held to a month.** L1 depends only on slice 1d. The trial depends on Slice 0. Either may start in December if a volunteer takes it.

### What we can show and when

**Assumption, for the maintainer to correct:** 8 working days a month, about two a week, counted from 10 November 2026, with two weeks off at the year end. The roadmap's figure for all work is about 16 person-days a month; the shell redesign, Labs and the release trains compete for them. Each date below is the cumulative days at that rate. The sums are the build-plan session's (`build-plan/size.py`).

**Not in any date:** the three private fixes, which go first (B5), or the fourth, added on 13 November (V20). Every two days they take moves every later date by a week. **No slack is in any date:** each assumes every slice takes its estimate and merges when written.

| Work | Days | Cumulative | Date |
|---|---|---|---|
| Slice 0 | 2 | 2 | 15 November (the call) |
| Preparation: the ADR, the one page, the LQ.AI prompt's first text | 2 | 4 | 22 November (the call) |
| The private fixes | not sized | | |
| 0a, 0b | 2.5 | 6.5 | 2 December |
| Gateway: 1a-1, 1a-2, 1b, 1c, 1r | 6.5 | 13 | 8 January 2027 |
| 1d, 1e, 1j | 3 | 16 | 19 January |
| 1f-1, 1f-2, 1f-3 | 5 | 21 | 5 February |
| 1g-1, 1g-2 | 4 | 25 | 19 February |
| 1n, 1p, 1o | 4.5 | 29.5 | 7 March |
| 1h, 1i | 4 | 33.5 | 21 March |
| 1l-1, 1l-2 | 2.5 | 36 | 30 March |
| The eight screens | 14 | 50 | 18 May: the last screen merges |
| 3e | 2 | 52 | **25 May: Stage 1 ends; agents announced as usable** |

The first two rows show the call dates; the rate itself gives 17 and 24 November. The one page sits in the second row but is due on the 15th.

The later stages are not re-sized, so these are floors on top of a Stage 1 that is itself a floor:

| Work | Days | Cumulative | Draft 7 said | Now about |
|---|---|---|---|---|
| Stage 2 | 12.5 | 64.5 | early April 2027 | early July 2027 |
| Stage 3, without 3e | 6 | 70.5 | early May | late July |
| History tool H1 | 3.5 | 74 | mid-May | mid-August |
| Stage 4 | 7 | 81 | mid-June | early September |
| Contributed agents L1–L4 | 4 | 85 | late June | mid-September |
| Sub-agents trial | 3 | 88 | early July | late September |
| Sub-agents ADR and build | 14 or more | 102 | late August or September | mid-November 2027 at the earliest |

A volunteer may still take L1 once 1d is on `main`, and the sub-agents trial once Slice 0 has run.

**What moved since Draft 7.** Stage 1's exit was late February; it is now three months later. Of the 26.5 added days: 10.5 are six more screens; 3.5 are stop and the two limits; 2.5 are 0a and 0b; 2 are 3e; 1 is progress events; 1 is the removal of the inputs check. The other 6 come from splitting 1a, 1f and 1g, whose line counts grew.

**Beside the roadmap.** Stage 1 now ends at about the same time as the roadmap's Candidate train (30 April 2027) and the earliest 1.0 tag (May 2027). At 8 days a month it takes half of the maintainer's observed days until late May, across three release trains. Open question 1.

**Ordering.** Ruled 12 November (B7): A, builder first. A volunteer may still run the sub-agents trial earlier.

**The ADR** can no longer be one page tabled on 15 November: it has five more decisions to make, and this week's two days go to Slice 0. Show Slice 0 and this design on 15 November, for direction; table the ADR, about two pages, on 22 November. Until it is agreed, no slice numbered 1 merges or ships. The private fixes and 0a merge before it. On this queue the first gateway slice is ready to merge in early December, so the ADR delays nothing unless it slips two calls. It covers Stages 1 to 3 and, since 13 November, the replacement of ordinary chat, the trigger and the freeze. Timing, contents and the separate committee items: [annex E](#e-governance-path).

**The shell.** The screens are due to start about the end of March 2027. PR #815, the cutover, is a draft at the end of a chain of open pull requests and waits for ADR 0045, which the committee is asked to finalise on 22 November (GitHub, 12 November, as the build-plan session read it). The redesign's later rebuild of the message box has no pull request, so the agent pill and the "newer version" line will be placed twice.

### Not in this plan

A file describing New harness. An operator-installed agents directory. Team sharing. Support for two interface shells. Version compare, a size meter, example prompts, model effort settings. Longer-term memory. A slice for the `plan` tool. Streaming the text of any round but the last (progress events are not text streaming). A skill marked always-loaded. A loaded skill kept for the whole chat. History beyond this chat. Any change to retrieval on an install with agents off, until the old chat path is removed. A slice, a size or a date for that removal. Narrowing to one authority source. The Labs list page.

### Risks

| # | Risk | Response |
|---|---|---|
| 1 | The ADR slips a call, or minutes are posted late | Work continues on a branch; merge moves a week per slip |
| 2 | A small local model does not call tools reliably, loads no skill, or loads the wrong one | Slice 0 runs on `gemma4:e4b` as the local model. A first probe is in `research/2026-11-12-local-tool-probe.txt`. The Ollama adapter passes tools and returns tool calls (read, not run). The record says what was loaded. After the trigger there is no server-side knowledge fetch to fall back on; whether that makes this risk a named blocker is not ruled (open question 43) |
| 3 | On a pseudonymizing route the model writes its search query from pseudonymized text, so knowledge search is weaker there | Accepted for Stage 1. H1 builds the rule per tool (annex B4). Open question 6 |
| 4 | A pasted file from a stranger now speaks from the system prompt | The label, the order, protected headings. The ADR says this is a label, not a guarantee. A pasted file's instructions can direct every tool the chat offers, and in Stage 1 a file cannot ask for fewer: `tools: none` arrives in Stage 3 |
| 5 | A turn of several rounds is slow. Not measured | Slice 0 reports rounds and times. Progress events show each round as it ends. Slice 3e streams the last round |
| 6 | Slice 2d carries a knowledge base into a chat under different matter terms | The ADR states the rule, or 2d leaves the ADR |
| 7 | Sub-agents prove larger than guessed | The trial sizes the build before any ADR |
| 8 | The example replies poorly: the model must search well by itself, and search returns top passages, not each NDA in full | Not verified. The exit test asserts only what the server controls |
| 9 | The private fixes are first in the queue and not sized; a fourth joined them on 13 November | Every two days they take moves every later date by a week. Triage sizes them |
| 10 | The shell cutover (PR #815) is not on `main` when the screens are due, about the end of March 2027 | The screens wait (B2). About four months of gateway and backend work come first |
| 11 | The 22 November call carries five items: this ADR, ADR 0045, ADR 0016, the PRD section 1.3 change and the DE-211 revision | The one that slips takes a week |
| 12 | A release is cut in the middle of Stage 1 with the agents setting half built | Open question 22 |

Defects found while reading code for this plan are tracked privately. Ruled 12 November (B5): three are fixed first, while the ADR is pending. A fourth item was put on the private track on 13 November (V20). It is not sized, and whether B5 covers it is not ruled. This plan does not say where any of them sits, and it is written as if they were fixed.

### Open items with an owner

Smaller than the main plan's open questions.

| Item | Owner |
|---|---|
| The name of the field that marks a chat turn, and the list of request builders that must set it: send, loop rounds, resume, re-run (API R32) | slice 1a-1 |
| The label's exact wording (API R44) | slice 1a-2, approved in review |
| Annex A5, items (a) and (b) | slice 1d |
| The call for reading operator instructions and the Organization Profile (API R56) | the read-screen slice, 1m-7 |
| Parked by the interface discussion on 13 November: screens not drawn (a reply with no pill; the builder's "save this skill first" notice; View file reading "deleted by its owner"); the Agents page's "Edit" and "Make a copy" controls; whether a stopped or failed reply keeps its step lines once saved; four mockup guesses not confirmed | the interface slices |
| Handed to the interface discussion on 13 November while it is parked: earlier tries in "Try it" are a list of hidden chats, one turn each (API R73); screens that exist only for agents off stop at the trigger (ADR R26); a "changed since this turn" line where an old turn's record is shown (V23) | the interface slices |
| Removing the old chat path: its slice, its size and its place in the order (ADR R26; the API discussion's report in annex I) | the maintainer (open question 41) |
| The private file's entry for the fourth privately tracked fix (V20) | the maintainer |
| Where the citing rule sits in the system prompt's order: answered twice on 13 November, last (API R76) and straight after the LQ.AI prompt (ADR R29). Its heading joins the set inputs cannot forge either way | the maintainer (open question 39) |
| Where the owner's reading of a turn's record through receipts goes: answered twice on 13 November, a slice before the trigger (ADR R31) and "rule after the API reports" (V26) | the maintainer (open question 40) |
### This week: one task

**Slice 0.** On a throwaway branch. 2 days. Never merged as it is. No gateway change.

- **Includes:** a parser for the example file's fields (`schema`, `name`, `title`, `description`, `model`, `skills`, `knowledge`, `tools: chat`, and the body); `model` and `knowledge` are read and ignored. On send, the server builds one system message: the body, then each listed skill's name and description. It offers `load_skill` in the chat loop. When the model calls it, the server adds the skill to the request, and the gateway's existing assembly merges it on the next round. A developer switch hides all of it.
- **Wrong on this branch, on purpose:** the parsed file is held in the browser and sent with the message; the design has the server hold the chat's agent. No LQ.AI prompt. Once a skill is loaded, the agent's text sits under the gateway's "Operator system instructions" heading: the wrong label, and the reason for slice 1a-2. Knowledge still arrives the old way. The limit is chat's 8 tool calls, not the rounds limit.
- **Leaves out:** the table, records, the check, any screen beyond a paste box.
- **Not usable** in a matter with real data.
- **Done when:** with the `nda-comparer` example on `local`, served by `gemma4:e4b`, and two short NDAs pasted into the message, the model calls `load_skill("nda-snapshot")` and the final response's `lq_ai_applied_skills` names `nda-snapshot`. The gateway log cannot show this, and no log line is added for it. Asked something that needs no skill, it loads nothing. Repeat on one cloud alias with a test skill that sets no tier minimum. Then try `nda-snapshot` on `smart`: the gateway should refuse the round after the load, which is the mid-turn refusal slices 1g-1 and 1g-2 remove. Note the rounds and the time for each.

Ruled 13 November (API R57): the design is not shown until Slice 0 has run through the gateway. If it is not ready by Sunday 15 November, the item moves to 22 November with the ADR. On 12 November the build-plan session found no branch for Slice 0 among this repository's branches and worktrees.

### The first two weeks (10–24 November)

Building first:

- [ ] Slice 0.
- [ ] The one page for 15 November: the turn shape, the ADR's decisions as headings, the aim, and four questions for the committee (the aim, agents as the product, the user-readable prompt, the `plan` tool). A draft is at `discussions/2026-11-15-one-page-draft.md`.
- [ ] Triage the private defects through the private channel, and fix them first, while the ADR is pending (B5).
- [ ] Slice 0a, on `main` and independent of the ADR: sum tokens and cost over a tool-loop turn's rounds, paused and resumed turns included.
- [ ] Slice 0b on a branch. Whether it may merge before the ADR is open question 20.
- [ ] Turn Slice 0's parser into slice 1d; start slice 1a-1 on a branch.
- [ ] Confirm on a running stack whether the admin re-run can be reached today, then file an issue: fix or remove (API R30). Ruled 13 November (API R81): it is removed with the old chat path.
- [ ] Draft the ADR "Agent files in chat". Open its pull request before 22 November.
- [ ] Write the first text of the LQ.AI system prompt. It is short, and it is the maintainer's.
- [ ] If "Agents" is to have a row in the redesigned sidebar, raise it in the ADR 0045 discussion before its comments close on 20 November (open question 21).

This list is more than the four working days the plan's rate gives a fortnight, and it has 0a and 0b before 24 November where the dates table says 2 December. Read it as what comes first, not as a promise for the fortnight.

Then housekeeping:

- [ ] Publish the 8 November minutes.
- [ ] Open an issue each for the sub-agents trial and for L1, with size, first file and reviewer.
- [ ] Update #662, which still invites leads for tracks this plan freezes. Comment on #725, #726 and #802.
- [ ] Put the committee items in annex E on the agenda.

The removal of the required-inputs check is slice 1r and waits for the ADR (B6).

## J. Changes since draft 4

Rulings of 12 November, from four discussions (API, interface, audit, ADR). Each is recorded in the maintainer's words in `discussions/`.

**Folded in:**

- **API R1, R2, R5.** The agent belongs to the chat, and the server holds it. The chat points at a saved version; each turn freezes that version when it starts. The message request carries only the message. Reverses "the chat remembers its agent in the browser".
- **API R6.** A chat stays on its version until the user moves it.
- **API R7.** A chat's agent can be set, swapped or removed between turns.
- **API R8.** On an agent chat, saved skills can still be attached by hand. Inline skill text is refused.
- **API R3, R4.** Confirmed without change: the check runs every turn; a turn is the whole tool loop.
- **Audit 1.** The gateway reports what it assembled, each round. The backend copies that into its record.
- **ADR R1, R2.** New wording under "One agent file".
- **ADR R3.** What `delegate` and `plan` are.
- **Interface.** The interface slices are drawn against the redesigned shell. The agent's name is a pill with an agent icon.

**Second fold, later on 12 November (draft 6).**

- **API R9.** The sender may pick another model for one turn. The check runs against it and the record shows it.
- **API R10.** The check runs before the message is saved. A refusal is a 409 listing the items; "run without" is the same message sent again with a `run_without` list.
- **API R11.** Missing required inputs never refuse a skill, in any chat. All 17 built-in skills can be listed in Stage 1.
- **API R12.** The LQ.AI system prompt is for every chat. Only the agent and skills-list sections are agent-only.
- **API R13; interface.** The answer still arrives in one piece, but the stream carries a progress event after each round. The chat shows them as live step lines.
- **API R16, R20; interface.** The default agent is a built-in agent file. With agents on, every chat has an agent, and one with none chosen runs the default. The agents setting is the operator's, not a per-person switch.
- **API R17.** Each reply row stores the agent id and version it ran on. This reverses "no agent columns on the message row", and differed from audit ruling 2 until R26 settled it; see Records.
- **API R19; interface.** "Try it" saves a version and runs it in a scratch chat: an ordinary chat, hidden from the list, one per agent.
- **API R23.** An agent turn is bounded by rounds (20 by default) and an optional spend limit. A load is an ordinary round.
- **API R25.** Stop ends a turn between rounds.
- **API R15, R22, R24; audit 3.** Slice 0 runs on `gemma4:e4b` and is done on the response field alone.
- **API R14, R18, R21.** Confirmed without change: the tool order; a loaded skill lasts one turn; `search_history` is this chat only and does not ship uncovered.
- **Audit 2, 4, 5, 6, 7.** The audit row is the one full record. `load_skill` and `search_knowledge` write tool-call log rows. Tokens and cost are summed over a turn's rounds. Every prompt part has a fingerprint, and the plan says which texts can be read back. The record is complete at the first usable point for turns that run straight through.
- **ADR R4.** The 22 November ADR decides that a `plan` tool exists and that the user approves its plan.
- **ADR R5, R6, R7.** One new ADR, "Agent files in chat": it amends ADR 0007, sits beside ADRs 0035 and 0038, and cites 0038 as Proposed. It asks the committee to endorse the aim that the agent loop replaces the main chat interface, with the replacement itself a later decision.
- **Interface.** The agent pill in the message box changes the chat's agent. Every reply carries its pill, with a line where the agent changes. A line above the message box announces a newer version.

**Third fold, same evening.**

- **API R26.** Settles the reply row: it stores only a pointer, the agent's id and version. Everything else about the turn stays on the audit row.
- **API R27.** The gateway's report is one `lq_ai_assembled` object on each response.
- **API R28.** A plan is a document that belongs to the chat. It arrives with `delegate`, after the trial, and is not in Stages 1 to 4.
- **API R29.** The token and cost sum merges first, as its own PR on `main`, paused turns included.
- **ADR R8.** A user can read every part of the system prompt that shaped their turn.
- **ADR R9.** The agent file could carry an author field, so a built-in agent is not labelled user-written. Narrowed by ADR R11 in the fourth fold.
- **ADR R10.** The ADR fixes the order and the rules. Field names, heading text and slice detail stay in the plan.

**Fourth fold, same evening (draft 7).** The audit discussion and the ADR discussion are closed.

- **ADR R11, R12.** The server writes the label from where it loaded the agent: "built in to LQ.AI" or "written by a user of this deployment". An `author` line in the file is only the file's claim. Built-in agents sit in the same section under the same limits, and are reviewed like code, not attested.
- **ADR R13, R19.** On 15 November: Slice 0 and one page. The ADR is tabled on 22 November. A draft of the page is in `discussions/`.
- **ADR R14.** The ADR has a title and no number until its pull request opens.
- **ADR R15.** This plan is cut: the slots, stages, dates, risks and this week's task moved to annex I, the change list to annex J, the glossary to annex K. The target was about 3,500 words; the seventh fold says where it stands.
- **ADR R16.** The plan is committed to `docs/plans/` in the ADR's pull request, after a scrub. Not done yet.
- **ADR R17.** "Agents" are the product, not skills: a committee item amending PRD section 1.3.
- **ADR R18.** ADR 0016 is tabled for ratification on 22 November too.
- **Audit 8, 9.** `search_history` is this chat only, for good, and ships only when three conditions hold.
- **Audit 10.** An admin re-run of a blocked turn is unrecorded for the agent. Accepted, as a stated limit.
- **Interface.** People can read their operator's instructions and the Organization Profile in the interface.

**Fifth fold, 13 November (draft 8).** A build-plan session redid Stage 1, and the maintainer made eight rulings in it. Two more audit rulings arrived after that discussion had closed.

- **B1.** No early usable point: agents are announced as usable only when all of Stage 1 is on `main`. Reverses "By adopting this plan you accept", item 8.
- **B2.** The agent screens wait for the shell cutover, PR #815, on `main`.
- **B3.** Slice 3e moves from Stage 3 to the end of Stage 1.
- **B4.** Stage 1 is finished before Stage 2 starts.
- **B5.** The private fixes go first, while the ADR is pending.
- **B6.** The two every-chat changes wait for the ADR and ship when merged. Settles open question 18.
- **B7.** Ordering A. Settles open question 2.
- **B8.** One migration, in slice 1e; slice 2a loses its own.
- **Audit 2, amended.** The reply row gains only the agent pointer. Loaded skill names still reach the row by the existing path; summed tokens and cost fill columns it already has.
- **Audit 10, corrected; audit 11.** A refused agent turn writes an audit row of its own. Until this ruling, "the refused turn's audit row still names the agent" was not true.
- **Audit 12.** The gateway's routing log is unchanged. The backend's audit row is the only durable copy of the assembled parts, listed per round.
- **Stage 1 re-sized.** 31 slices, about 8,550 lines and 48 days, where Draft 7 had 14 PRs, 4,100 lines and 21.5 days. Slices 1a, 1f, 1g, 1l and 1m are split; 0a, 0b, 1n, 1o, 1p and 1r are new. These are the build-plan session's estimates. Stages 2 to 4 are not re-sized.
- **Thirteen questions added** to the main plan's open questions, 19 to 31.

**Sixth fold, 13 November (draft 9).**

- **Audit 13.** Supersedes audit 10. An admin re-run's audit row names the blocked turn's agent and says the re-run did not run as it. The re-run's reply carries no agent pointer and shows no pill. Settles open question 28; three follow-ups are with the API discussion.
- **The Agents row in the sidebar.** Put to the maintainer in the build-plan session: "Decide later". Open question 21 stays open.
- **The decided list** moved from the main plan to annex L, to shorten the main plan.

**Seventh fold, 13 November (draft 10).** A review of Draft 9 (`reviews/2026-11-13-draft9-review.md`) made 22 comments. The eight that need no ruling are applied here, with three exceptions: comments 2, 6, 16, 17, 18, 20, 21 and 22. The other fourteen wait for the maintainer or the API discussion and change nothing in this draft.

Not applied:

- **From comment 21:** "main" and "builder" still carry more than one meaning each, and "message row" and "per-turn record" remain in places in the annexes.
- **From comment 2:** the reading "replacing chat for everyone is the later decision" went into open question 10 as a reading to confirm. It was not written into annex E item 14 or the main plan's item 9, because that would settle the question.
- **From comment 22:** one of its five cuts depends on comment 13, which the maintainer has not ruled. So the main plan is about 3,920 words, not the 3,430 the review projected.

Applied:

- **Main plan shortened** to about 3,920 words. "The builder screen" and "Building it" moved to annex C. "Records" is three short paragraphs; the detail is in annex B5, now a list. Settled questions moved below.
- **Stage 1's 48 days is stated as a floor,** with a list of ruled work that has no slice, and 18 May is stated as a merge date, not a release.
- **Twelve smaller open items** are listed with their owners in annex I.
- **Contradictions removed:** the `limits` stage, the reply row's three additions, which prompt parts are agent-only, what the ADR decides about New harness, annex G's first and last rows, and smaller ones.
- **One wrong reference fixed:** required skill inputs are decided in ADR 0007, not ADR 0006.
- **The contributed-agents track** is no longer called the Labs track; "Labs" now means only the shell's Labs page.
- **The one page for 15 November** was corrected in `discussions/` against this draft.

**Eighth fold, 13 November (draft 11).** The maintainer ruled on the nine review comments that needed him, as twelve questions. His words are in `reviews/2026-11-13-review-rulings.md` (V1 to V12).

- **V1, V5, V7.** Three go to the API discussion, which is to put each to him: citations on agent turns, what a failed turn records, and what each fingerprint covers. Open questions 32 to 34.
- **V2.** The ADR "Agent files in chat" is the DE-388 decision for agent turns. The adversarial evaluation runs before slices 1f-2 and 1i merge. Not sized.
- **V3.** Annex E names the existing decisions the ADR touches: DE-409, ADR 0015 D1 and ADR 0018.
- **V4.** The committee's wording on reading the prompt is narrowed to the current text of every authored part.
- **V6.** In Stage 1 a chat's owner cannot read the turn's audit record. Settles open question 29.
- **V8.** A contributed agent whose instructions carry legal substance follows the skills attestation path.
- **V9.** Agents are announced as usable after slice 3e, so Stage 1 has one end. Settles open question 19. The "answer does not stream" limit leaves the list of commitments, annex E and the one page.
- **V10.** The `plan` tool is decided in the sub-agents ADR, not on 22 November. Supersedes ADR R4 on that point. Annex E's item 13 is now the attestation rule.
- **V11.** A version that ran in a matter cannot be deleted while the matter is open; it can be retired.
- **V12.** "By adopting this plan you accept" is retitled "What this plan commits LQ.AI to", and each item says who decides it. Not taken up: asking the committee about capacity, tabling the LQ.AI prompt's text, and a new PRD entry in place of revising DE-211.

**Ninth fold, 13 November (draft 12).** The API discussion worked through its queue: rulings R30 to R57, in the maintainer's words in `discussions/api.md`. It is not closed.

- **R30.** A refused agent turn saves nothing but its audit row. The admin re-run is not wired to agent refusals in Stage 1; whether it can be reached at all is checked on a running stack and filed as an issue.
- **R31.** "Every chat has an agent" means every chat turn sent through the agent loop. Admin re-runs, New harness runs and older replies have none. With agents turned off, chats keep their pointer and run as ordinary chat.
- **R32.** A new request field, set only by chat, tells the gateway a request is a chat turn. Settles open question 31.
- **R33.** On an agent turn the request's model has no default: absent means the file's model.
- **R34.** Inline skill text is allowed on the default agent. Narrows R8.
- **R35.** A chat on the default agent follows the shipped file, with no version; old texts are kept. Amends R20.
- **R36.** Ordinary chat: document text unchanged; progress events and Stop for every tool turn.
- **R37.** The limits are stated plainly; no count of tool calls; a stopped reply always has text.
- **R38.** Placeholder renumbering after a mid-turn load is tested in slice 1h.
- **R39.** Progress events at the start and end of each step. Amends R13.
- **R40.** Skills attached by hand go through the same check, before the message is saved.
- **R41.** Every saved version raises the "newer version" line, "Try it" versions included.
- **R42.** The agents list includes the default agent; reading a chat reports a newer version.
- **R43.** `author` is not a version 1 field; a file may carry it under `metadata`.
- **R44.** The label's wording is left to slice 1a-2.
- **R45.** The refusal action is `agent.turn_refused`; the built-in tools' rows carry the provider name `lq-ai`; `load_skill` uses the governed entry point.
- **R46.** Stop ships in one slice: the stop call and a closed stream. Settles open question 24.
- **R47.** Every chat turn's record carries the LQ.AI prompt's version; an overridden turn's record carries both models. Settles open question 25.
- **R48.** The check is also a call of its own.
- **R49, R55.** A version that ran in a matter is retired, not deleted, while the matter is open. A chat on a retired or deleted agent falls back to the default agent, with a line that says so. Agrees with review ruling V11 and adds the fall-back for retired agents.
- **R50.** Verified citations are carried through `search_knowledge`. Answers review ruling V1 and open question 32.
- **R51.** The receipts call is extended so a chat's owner reads a turn's record. **Conflicts with review ruling V6** of the same day ("audit log only, for now"). Not resolved in this fold; resolved in the eleventh (R65).
- **R52.** The default agent's file: no `model` line, no skills, `tools: chat`, `knowledge: [matter]`. Its name and body stay open. Amended in the eleventh fold (R64): it ships with `knowledge: none` first.
- **R53.** A refused model is fixed by picking; `run_without` never names the model.
- **R54.** A turn that fails part-way always leaves a reply and a record. Answers review ruling V5 and open question 33. Held, then put in force after a run (eleventh fold, R69).
- **R56.** The call for reading operator instructions and the Organization Profile is left to the interface slices.
- **R57.** The design is not shown until Slice 0 has run through the gateway. If it is not ready by 15 November, the item moves to 22 November. Settles open question 30.

**Tenth fold, 13 November (draft 13).** The API discussion's last four rulings; the maintainer then answered "Settled" for that discussion.

- **R58.** Agents are usable before the streaming slice, as the build plan read B1 and B3. **Conflicts with review ruling V9** ("After 3e"), given about an hour earlier by the files' times. Not resolved in this fold; resolved in the eleventh (R68 withdrew it).
- **R59.** Slice 3e requests every round from the gateway as a stream, and the gateway's last chunk of each round carries that round's cost. A gateway change: security path, to be re-sized.
- **R60.** What each fingerprint covers is left to slice 1a-1, settled in review. Settles open question 34. Superseded in the eleventh fold (R67).
- **R61.** The default agent is named `lq-ai`, titled "LQ.AI", with an empty body for now. Settles open question 9.
- **Left to slices by his rulings:** the label's wording (1a-2), fingerprint coverage (1a-1), the read call for operator text (the interface slices). **Without an owner:** review comment 12(d), and a paused turn frozen on a version that is then retired or deleted.

**Eleventh fold, 13 November (draft 14).** The API discussion was reopened for the three items the review rulings sent it (V1, V5, V7), the case V11 left open, and the two conflicts. Rulings R62 to R72; the maintainer then answered "Settled again". Two interface rulings of the same day are folded too.

- **Both conflicts are settled.** V9 stands and R58 is withdrawn (R68): agents are announced after slice 3e. V6 stands for Stage 1 and R51 becomes a later item (R65). Open questions 19 and 29 are settled as the review rulings had them.
- **R62.** The citing rule is in the system prompt and, as a one-line reminder, with each search result. Amends R50.
- **R63.** Numbers run on across a turn; a repeat keeps its first number; the loop keeps the list and saves it with a paused turn; today's checker and ledger are unchanged.
- **R64.** Citations are built in Stage 1, with or straight after `search_knowledge`. Until then the default agent's file says `knowledge: none` and keeps the server fetch. Amends R52 and R61.
- **R65.** The owner reading a turn's record through receipts is a later item: a deferred enhancement or another stage.
- **R54 held, then R69.** He asked for a run first. After it: a failed turn always leaves a reply and a record, written together or not at all. A new security-path slice, not sized.
- **R66.** The turn outlives the connection; a closed stream stops it after the round in flight. Part of slice 1o.
- **R67.** Fingerprints are over saved text; the agent has two. Supersedes R60.
- **R68.** Also: a paused turn finishes on its frozen version even if that version is retired or deleted meanwhile.
- **R70.** Attached-file text stays a system message in Stage 1. This reverses item 12 of this plan's decided list.
- **R71, R72.** The previous reply's verified cited passages are carried into the next turn, first in its list as [1] to [k], in today's "retrieved context" block.
- **Interface, 13 November.** A model picked on the default agent lasts one turn too, so with agents on no chat keeps a picked model. Editing an agent starts from the Agents page only; the pill only switches agents. The interface discussion asked whether API R33 and R52 already make "no model" resolve to the install's default. R33's text says so ("if the file names none, the default model as today"). That is this plan's reading, not a new ruling.
- **Run, not read.** `research/2026-11-13-failed-turn-probe.txt`, with the loop replaced by a stub (annex H).
- **The orchestrator's notes, none of them ruled.**
  - `knowledge: none` now means two things: no knowledge, on any agent; and "fetched by the server", on the default agent until citations merge (open question 37). Settled in the twelfth fold.
  - The probe shows, on the streamed path, that a successful turn whose audit write fails keeps its reply and has no audit row. R69 covers failed turns (open question 38). Settled in the twelfth fold.
  - With R70 and R72, the ADR's DE-388 answer covers `search_knowledge` results only, and three of DE-388's five points have no answer in this plan (annex E).
  - The API discussion estimated the citations slice before R71 and R72 widened it. No figure is given here.
- **Handed to discussions that are closed,** so recorded in this plan instead. In annex E: the ADR must defend the citing reminder inside a tool result and state DE-388's narrower scope. In annex B5 and the open-items table: the record holds two agent fingerprints under different names. In annex B5 and annex E item 4: the audit write is no longer best-effort for failed turns.
- **Without an owner:** review comment 12(d); a paused turn that is never resumed; where the citing rule sits in the prompt's order.

**Twelfth fold, 13 November (draft 15).** The maintainer answered open questions 37 and 38, put to him by the orchestrator. His words are in `reviews/2026-11-13-review-rulings.md` (V13 and V14).

- **V13.** The default agent's file says `knowledge: none` while the server still fetches for it, until the citations slice merges. Accepted as it is: no comment in the file, no other value, no change to the slice order.
- **V14.** On an agent turn the reply and the audit row are one write, for a turn that succeeds as well as one that fails. If the record cannot be written, the reply is not saved and the user gets an error. Chat with agents off stays as today. Part of the failed-turn slice; not sized.

**Thirteenth fold, 13 November (draft 15).** Seven more rulings in the interface discussion, which the maintainer then answered "Settled, park those". His words are in `discussions/web.md`.

- **"Try it" searches the matter you pick in the builder.** The pane has a matter chooser. As amended the same day, it starts on the matter this agent was last tried against, and on no matter the first time. The clause "the matter you opened the builder from" was dropped, because editing starts from the Agents page only.
- **Every try starts clean.** Each try runs as the first turn of an empty chat. Earlier tries stay visible above and are not sent to the model, so a follow-up question cannot be tested there.
- **The first web change is in Stage 1, as planned:** the Agents page and the pill. No change to this plan.
- **The upstream `/workspace/models` page is left alone.** Its fate belongs to the OpenWebUI removal work. Settles open question 5.
- **Reading the operator instructions and the Organization Profile is a Stage 1 slice of its own,** with one read call, so it can be reviewed, and dropped, on its own. The question put to him said the read screen had no slice. This plan has had slice 1m-7 for it since the re-split, so it read the ruling as confirming 1m-7 and added no slice. The maintainer confirmed that the same day (V15).
- **Handed to the API discussion, which is settled,** so listed in the open-items table: how the scratch chat changes its matter between tries, runs a try without the earlier turns, and remembers the last matter used.
- **Parked, not ruled:** three screens not drawn; the Agents page's missing "Edit" and "Make a copy" controls; whether a stopped or failed reply keeps its step lines once saved; the plan-approval screen; where a dismissed "newer version" line is remembered (open question 15); four mockup guesses.

**Fourteenth fold, 13 November (draft 16).** The ADR, audit and API discussions were reopened for the items handed to each after it closed. Three dialogs were open to the maintainer at once, so he asked the orchestrator to consolidate the questions. His answers taken there are V16 to V29 in `reviews/2026-11-13-review-rulings.md`, and each discussion recorded its own under its own numbers. All three then answered "Settled". Folded here: ADR R21 to R44, API R73 to R84, audit rulings 14 to 21. His words are in `discussions/adr.md`, `api.md` and `audit.md`.

- **Answered twice, not reconciled.** Two questions reached him in two discussions and got two answers. The citing rule's place: last, after loaded skills (API R76), and straight after the LQ.AI prompt (ADR R29). The receipts extension: "rule after the API reports" (V26), and a slice before the trigger (ADR R31). He has been told and has not said which stands. This plan states neither as settled and adds no slice (open questions 39 and 40).
- **The replacement (ADR R21, R25, R26, R27).** The ADR decides the replacement of ordinary chat now, superseding R7's "later decision". Stage 1 ships with agents off by default. The next minor release turns them on by default, unless a stated blocker is open: the trigger. At the trigger the setting and the old chat path are removed together, with no switch back. ADR 0038 D7's two tests are conditions of the trigger. Settles open question 10.
- **ADR R22, R23.** "The server holds a chat's agent" stays decision 12. The New harness freeze is a decision of this ADR; retiring or rebuilding New harness stays later.
- **ADR R24, with R41 (V25).** The ADR has one section, "what changes for every chat". All of them wait for the ADR and ship when merged in a minor release, each with a release-note line and a line in `docs/HONEST-STATE.md`. Slice 0a is on the list but does not wait. The list is in annex E decision 8. Settles open question 36.
- **ADR R30 (V28), R32 (V29), R33.** Operators learn that their text is readable from a release note only; it does not join the every-chat list. The ADR has a "Limits" section with four limits. The citing reminder is allowed because it is fixed, format-only and measured.
- **ADR R34, R35.** The orchestrator rewrites the one page after this fold. The main plan holds to 3,500 words. Neither is done in this fold.
- **DE-388 (V16 to V19; ADR R37 to R40).** Point 3: the posture is unchanged and the mechanism is stated. Point 4: left open, which narrows review ruling V2. Point 5: no worse than today, with the numbers published. The corpus: a small one, built in a new Stage 1 slice. Not sized.
- **API R73, R78 (V27).** "Try it" makes a new hidden chat for every try, amending R19. A try does not count as "ran in a matter". Deleting a version deletes the try chats that ran it; otherwise they are kept until the agent is deleted.
- **API R74, audit 21 (V24).** A paused turn that runs out ends as a failed turn. No further audit rule. Two lines of this plan that described a paused turn never resumed were reworded or removed.
- **API R75, R76, R80.** Attached-file text and carried passages are a system message of their own, after the assembled one; a provider that takes one system prompt receives them joined. The citing rule is a part of its own, kind `citing_rule`, with a version and a fingerprint, present only when the agent can search knowledge. It appears once: the carried block's header loses it. Passages are carried only when the agent can search knowledge. Amends R72.
- **API R79, audit 16.** One list of how a turn ends, seven values, the same on the reply row and in the record.
- **API R81, R82.** The admin re-run is removed with the old chat path. With a spend limit set, a turn on an unpriced paid route is refused at the check; with none set it runs and the record says "unpriced".
- **Audit 14 and API R84.** Only the server's own change of a chat's agent is an audit event, `chat.agent_reassigned`. Settles open question 11.
- **Audit 15 and API R83.** The search's audit row names the embedding's provider and tier, or "keyword only", and the embedding's routing-log row is tied to the turn. A gateway change in slice 1i. Settles open question 35.
- **Audit 17 to 20 (V21 to V23).** The record lists carried passages by count and source ids. The run-without choice is on the resent turn's row. The record's two agent fingerprints are `agent_file_fingerprint` and `agent_instructions_sent_fingerprint`, and the Organization Profile is a part of kind `organization_profile`. The record keeps only a fingerprint of operator text; that limit is accepted, with a "changed since this turn" line.
- **API notes, not rulings.** With no model sent and none in the file, the turn runs the request's default, which on `main` is the `smart` alias. R67 named slice 1f-1 in error.
- **Reports, not rulings, by the API discussion; read, not run, not sized.** What removing the old chat path covers is in annex I, with a guess of 2 to 4 days. Where the two trigger tests stand is in annex E.
- **What the replacement makes temporary. The orchestrator's reading.** V14's agents-off exception; API R36's "ordinary chat unchanged"; the cap of 8 tool calls; "experimental and off by default"; open question 13 as it was worded. Each now ends at the trigger.
- **Not put to the maintainer** (open questions 41 to 44): where the removal sits in the order and who sizes it; whether 22 November and "about two pages" still hold; whether "experimental" comes off at the trigger, and whether the local-model risk is a named blocker; ADRs 0025, 0029 and 0031 against the trigger, and New harness runs after it.
- **The orchestrator's error.** The list of every-chat changes it sent the ADR discussion, which became the list under R24, left out the token-and-cost sum and the removal of the required-inputs check. V25 put the first to him; the second already waited for the ADR under B6.
- **Handed to the interface discussion, which is parked,** so listed in the open-items table: earlier tries are a list of hidden chats; screens for agents off stop at the trigger; the "changed since this turn" line.
- **Not done:** the cut to 3,500 words (ADR R35); the one page (ADR R34); the scrub, commit and private backup (ADR R16). `build-plan/build-plan.md` still rests on Draft 7. The main plan is about 4,660 words after this fold, against the 3,500 ruled.

**Fifteenth fold, 13 November (draft 17): the cut.** ADR rulings R15 and R35 hold the main plan to 3,500 words. No ruling is added and none changes.

- **Moved to a new annex M, word for word:** the nine commitments, and six passages of "How a turn is built" (steps 1, 4, 8 and 9, the label wording in step 5, and the two paragraphs on the reply row and on the rulings of 13 November). The main plan keeps a short form of each.
- **Open questions.** The lines that said only "Settled; see annex J" are gone; one sentence lists their numbers. The questions that remain keep their numbers and are now a bulleted list, so a renderer cannot renumber them. Their wording was tightened and nothing was removed.
- **The one page** was rewritten against this draft the same day (ADR R34), at `discussions/2026-11-15-one-page-draft.md`: about 700 words to post. It lists fifteen decisions, and its first question to the committee is now the replacement, not the aim.
- **Not done:** the scrub, commit and private backup (ADR R16).

**Sixteenth fold, 13 November (draft 18): the scrub.** Lines that said where privately tracked fixes sit were removed or reworded, as ruled (ADR R16), and both files were committed to `docs/plans/`. The maintainer made the private backup copy outside the worktrees the same day, which closes ADR R16. He also ruled that the lines stating what `main` does today, its limits included, are committed as written (V30). No other ruling is added and none changes.

**Open questions settled.** Moved from the main plan, which keeps their numbers.

- **2.** Settled 12 November (B7): ordering A, builder first.
- **5.** Settled 13 November (interface): the upstream `/workspace/models` page is left alone. Its fate belongs to the OpenWebUI removal work, not to this plan.
- **4.** Settled 12 November (ADR R12) for built-in agents: reviewed like code, not attested. Settled 13 November for contributed agents: one whose instructions carry legal substance follows the skills attestation path.
- **7.** Settled 12 November: a loaded skill lasts for the turn only.
- **8.** Settled 12 November: `search_history` is this chat only. Reaching other chats would be a separate proposal with its own ADR (audit ruling 8). API R21, taken earlier the same day, had left that as "an open question for later"; this plan follows audit ruling 8.
- **14.** Settled 12 November (API R26): the reply row holds the agent pointer; the audit row holds the record.
- **18.** Settled 12 November (B6): one ADR covers both every-chat changes, and both ship in the next release cut after they merge.
- **9.** Settled 13 November (API R52, R61, R64): the default agent is `lq-ai`, titled "LQ.AI", with an empty body, no `model` line, no skills and `tools: chat`. It ships with `knowledge: none` and changes to `[matter]` when the citations slice merges.
- **34.** Settled 13 November (API R67, superseding R60): every fingerprint is over saved text; the record's agent fingerprint is the file's, and the gateway's is kept under another name.
- **19.** Settled 13 November (review ruling V9; API R68 withdrew R58): agents are announced as usable after slice 3e. Stage 1 has one end.
- **24.** Settled 13 November (API R46): stop ships in one slice, the stop call and a closed stream together.
- **25.** Settled 13 November (API R47): yes to both.
- **30.** Settled 13 November (API R57): Slice 0 must run first; otherwise the item moves to 22 November.
- **31.** Settled 13 November (API R32): a new field that only chat sets.
- **32.** Settled 13 November (API R50, R62 to R64, R71, R72): citations are carried through `search_knowledge`, in Stage 1, and the previous reply's cited passages are carried into the next turn.
- **33.** Settled 13 November (API R69, after a run): a failed turn always leaves a reply and a record, written together.
- **29.** Settled 13 November (review ruling V6, API R65): audit log only in Stage 1. Reading through receipts is the goal, for a deferred enhancement or a later stage. Where it goes was then answered twice the same day and is open again as question 40.
- **37.** Settled 13 November (V13): the default file's `knowledge: none` is accepted as it is until the citations slice merges.
- **38.** Settled 13 November (V14): on an agent turn the reply and the record are one write, for a successful turn too. Chat with agents off stays as today.
- **10.** Settled 13 November (ADR R21, R25, R26): the ADR decides the replacement of ordinary chat, not only the aim. The trigger is one release after Stage 1, and the setting and the old chat path are then removed together.
- **11.** Settled 13 November (audit 14, API R84): only the server's own change of a chat's agent is an audit event, `chat.agent_reassigned`.
- **35.** Settled 13 November (audit 15, API R83): the search's audit row names the embedding's provider and tier, and the embedding's routing-log row carries the turn's ids. The tool-call row stays tier 0.
- **36.** Settled 13 November (ADR R24, R41): one list of every-chat changes in the ADR; all wait for it and ship when merged, except slice 0a, which merges when ready.
- **28.** Settled 13 November (audit ruling 13): an admin re-run's record names the blocked turn's agent and says the re-run did not run as that agent. Its three follow-ups were answered by API R30 and R31: no Stage 1 slice changes the override handler; an agent refusal leaves no reply row, so the pointer question does not arise in Stage 1; a re-run has no agent.

## K. Glossary

- **Agent.** A saved, named set-up for a chat: instructions, a model, a list of skills, knowledge, tools. It works like a profile for the chat: the chat holds it, and the server remembers which version.
- **Skill.** A written method for one legal task. Attached to a chat by hand, or loaded by an agent's model from its list.
- **System prompt, sections.** The text a model reads before the conversation. Here it is built in labelled parts: LQ.AI's, the operator's, the agent's, the skills list, loaded skills.
- **`load_skill`.** The tool by which the model asks for one listed skill's full text.
- **Tool loop, round.** The model is called; it asks for tools (searches, reads, saves); the server runs them and calls the model again. Each call is a round. The loop ends when the model answers.
- **Operator.** Whoever runs an LQ.AI deployment and sets its settings.
- **Matter.** A client matter. It carries its own terms, such as a minimum tier.
- **Tier.** A 1-to-5 rating of how protected a model provider is. Tier 1 (on site) is the strongest, tier 5 the weakest. It does not measure how clever the model is.
- **Pseudonymization.** Replacing names with placeholders before text leaves the deployment, and restoring them in the reply.
- **Connector.** A link to an outside system. The operator installs it; a chat uses it as a tool.
- **Fingerprint.** A short code computed from a file's exact text (a SHA-256 digest). Same fingerprint, same text.
- **Branch, merge.** A branch is a working copy of the code. Merging puts it into the shared product.
- **ADR.** Architecture decision record: the short document the committee ratifies before a significant change merges.
- **Slice.** One pull request's worth of work, about 400 changed lines at most. Slice 0 is a throwaway branch; 0a and 0b are real slices.
- **Gateway.** The Inference Gateway: the one component that holds the provider keys. Every call to a model passes through it, and it applies the tier check and pseudonymization.
- **Audit row, reply row, routing log, tool-call log.** Four places a turn leaves a trace. The audit row (`chat.message_sent`) is the full record of the turn. The reply row is the reply's row in the messages table. The routing log is the gateway's row for each call to a model. The tool-call log has a row for each tool the model called.
- **Cover.** To pseudonymize a tool's results before they leave the deployment. The history tool waits for a rule that does this.
- **New harness.** The experimental run engine merged in October 2026 (ADR 0038, still Proposed). This plan leaves it as merged.
- **Organization Profile.** A text about the organisation that the deployment adds to the prompt, at the head of the loaded skills.
- **Shell cutover.** The pull request (#815) that switches the web interface to its redesigned layout.
- **Usable point.** The moment agents are announced as usable: when all of Stage 1 is on `main`, slice 3e included.
- **The trigger.** The minor release after the one that ships Stage 1. It turns agents on for every install, unless a stated blocker is open, and removes the agents setting and the old chat path together.
- **Old chat path.** Chat as built today, with agents off: knowledge fetched by the server before the model is asked, and no agent on the turn.
- **Citing rule.** The instruction that tells the model how to cite a numbered passage. Today it sits in the header of the block of fetched passages.
- **Carried passages.** The passages the previous reply cited, sent again at the start of the next turn so a follow-up can quote them without a new search.
- **B1 to B8.** The maintainer's eight rulings in the build-plan session, listed in annex I.
- **Labs.** In this plan, the redesigned shell's Labs page only. Agents added to the repo by pull request are called contributed agents (slices L1 to L4); earlier drafts called that the Labs track.
- **Admin.** A signed-in user with the admin role. Often the operator; in a firm, possibly someone else.

## L. Decided in this draft

Moved from the main plan on 13 November, to shorten it. Confirm each. The alternative declined is in brackets.

1. LQ.AI gets a system prompt: a versioned file, written by the maintainer, rendered by the gateway. (None, as today.)
2. Agent instructions are a labelled section of the system prompt. Order: LQ.AI, operator, agent, skills list, loaded skills. (A user-role message, draft 3's design.)
3. Skills are listed; the model loads. `load_skill` attaches the skill, so the gateway's checks apply. (Returning the skill's text as a tool result: simpler, but it skips those checks.)
4. The check before the first call covers every listed skill. (Checking at load, which allows a refusal mid-turn.)
5. Reversed 12 November: missing required inputs never refuse a skill, in any chat, so every skill can be listed in Stage 1. (Not listing them; listing them and failing at load.)
6. Knowledge is a tool, `search_knowledge`, backed by chat's retrieval; no server-side fetch on agent turns. (Porting New harness's tool: another registry, keyword match only.)
7. The workspace is three tools, list, read and write, scoped to the agent in a matter. (Putting saved files into the prompt.)
8. Ruled 12 November: history is a tool over this chat only, `search_history`, and waits for a cover rule. A file with no `history` line gets no such tool. (Shipping it uncovered.)
9. Changed 12 November: an agent's answer does not stream until slice 3e, the last of Stage 1, but progress events do. An agent turn is bounded by rounds (20 by default) and an optional spend limit, and a load is an ordinary round. (No events until the answer; a cap of 8 tool calls with loads outside it.)
10. Sub-agents: a `delegate` tool in the same loop; trial, then ADR. Unchanged.
11. Changed 12 November: the LQ.AI prompt is for every chat; the agent and skills-list sections are for agent turns only. (The LQ.AI prompt on agent turns only.)
12. Changed 13 November (API R70): attached-file text stays a system message in Stage 1; only knowledge moves. (A user-side message labelled as documents; a synthetic tool result. Earlier drafts had decided "its own message".)
13. On a pseudonymizing route, `search_knowledge` takes the query as the model wrote it until H1. (Restoring arguments in Stage 1: one more gateway slice.)
14. Ruled 12 November: the ADR is tabled on 22 November. (15 November, on one page.)
15. Ruled 12 November: the server holds a chat's agent; the message request does not name it. (An `agent` field on each message; the browser remembering it.)
16. Ruled 12 November: on an agent chat, saved skills may be attached by hand; inline skill text is refused.
17. Ruled 12 November: the gateway reports what it assembled; the backend records that. Amended 13 November (API R67): the record's agent fingerprint is the file's, from the store, and the gateway's fingerprint of the instructions is kept beside it. (Recording what the backend asked for; recording both and flagging mismatches.)
18. Ruled 12 November: the check runs before the message is saved; a refusal is a 409 listing the items; "run without" is a resend with a list. A refusal writes an audit row.
19. Ruled 12 November: the sender's model overrides the file's for one turn.
20. Ruled 12 November: with agents on, every chat has an agent, and the default is a built-in agent file. The setting is the operator's. (Ordinary chat under a label.)
21. Ruled 12 November: each reply row stores its agent's id and version, as a pointer. The row also gains how the reply ended; the audit row holds the rest. (The audit row only.)
22. Ruled 12 November: stop ends a turn between rounds.
23. Ruled 12 November: "Try it" saves a version and runs it in a hidden scratch chat, one per agent. Amended 13 November: see items 45 and 49. (Moving the chat you came from; trying without saving.)
24. Ruled 12 November: the audit row is the one full record; every part has a fingerprint, with the read-back limits stated; the record is complete before agents are announced as usable, which is now all of Stage 1. (A new table; keeping skill text or the whole prompt.)
25. Ruled 12 November: `load_skill` and `search_knowledge` each write a row in the existing tool-call log. (The audit row only; storing results.)
26. Ruled 12 November: Slice 0 runs on `gemma4:e4b` and is done on the response field alone. (A debug log line per round.)
27. Ruled 12 November: no early usable point; Stage 1 is finished before Stage 2; ordering A. (An early point at about 26 or 33 days; sub-agents first.)
28. Ruled 12 November: the agent screens wait for the shell cutover; the private fixes go first; one migration, in slice 1e. (Building the screens now; fixing them later; a migration per change.)
29. Ruled 12 November: slice 3e joins Stage 1 as its last slice; the two every-chat changes ship when merged, after the ADR. (3e in Stage 3; holding both changes to the end of Stage 1.)
30. Ruled 12 November: a refused agent turn writes an audit row; the gateway's routing log is unchanged and the backend holds the assembled parts. (No row; a row for every refused chat turn; storing the parts on the routing-log row.)
31. Ruled 13 November: an admin re-run's audit row names the blocked turn's agent and says the re-run did not run as it; the re-run's reply carries no agent pointer. (Re-running as the agent with only the tier floor lifted; refusing re-runs of agent turns; leaving the re-run unrecorded for the agent.)
32. Ruled 13 November: the ADR "Agent files in chat" is the DE-388 decision for agent turns, and the adversarial evaluation runs before the send-path and knowledge-tool slices merge. (No wait for the evaluation; a separate ADR first.)
33. Ruled 13 November: the ADR names the existing decisions it touches: DE-409, ADR 0015 D1 and ADR 0018. (Amending ADR 0015 apart; naming none.)
34. Ruled 13 November: the committee's wording on reading the prompt is the current text of every authored part; for a past turn, the record says which. (The wider sentence; showing the code's fixed wording on the read screen.)
35. Ruled 13 November: in Stage 1 a chat's owner cannot read the turn's audit record; the interface shows loaded skill names only. Reading it through receipts is kept as the goal, for a deferred enhancement or a later stage (API R65). (Extending the receipts call in Stage 1.)
36. Ruled 13 November: a contributed agent whose instructions carry legal substance follows the skills attestation path; the others are reviewed like code. (No attestation for any agent; deciding with the track.)
37. Ruled 13 November: agents are announced as usable after slice 3e. (Before 3e.) API R58 chose the opposite later the same day and was withdrawn by API R68.
38. Ruled 13 November: the `plan` tool is decided in the sub-agents ADR, and stays on the one page as a question. (Keeping it in the 22 November ADR, with the reason stated.)
39. Ruled 13 November: a version that ran in a matter cannot be deleted while the matter is open; it can be retired. Deleting keeps the name and the fact of deletion, and a chat on a deleted agent returns to the default agent. A paused turn finishes on its frozen version even if that version is deleted meanwhile (API R68). A try in the builder does not count as running in a matter (V27). (Deleting freely.)
40. Ruled 13 November: API rulings R30 to R57. Each is listed in annex J's ninth fold; what each declined is in `discussions/api.md`. R51 later moved out of Stage 1 (R65).
41. Ruled 13 November: API rulings R59 and R61 to R72. R58 was withdrawn and R60 superseded. Each is listed in annex J's tenth and eleventh folds; what each declined is in `discussions/api.md`.
42. Ruled 13 November (interface): on every agent chat a picked model lasts one turn, the default agent's included; editing an agent starts from the Agents page only. (The pick staying on the default agent; editing from the pill.)
43. Ruled 13 November: until the citations slice merges, the default agent's file says `knowledge: none` while the server still fetches for it, with nothing added to the file. (A comment in the file; a temporary value; shipping the default file after citations.)
44. Ruled 13 November: on an agent turn the reply and the audit row are one write, for a successful turn too; chat with agents off stays as today. (The same rule for every chat turn; keeping today's behaviour and stating the limit; running it wider first.)
45. Ruled 13 November (interface): "Try it" has a matter chooser that starts on the last matter used for that agent, and every try starts clean. (The matter you came from; never a matter; tries that see the earlier ones, with a "Start over"; clean after each save.)
46. Ruled 13 November (interface): the upstream `/workspace/models` page is left alone; reading the operator instructions and the Organization Profile is a Stage 1 slice of its own. (Hiding the page; putting the read screen inside slice 1k; parking it.)
47. Ruled 13 November (ADR R21 to R27): the ADR decides the replacement of ordinary chat now; "the server holds a chat's agent" stays its own decision; the New harness freeze is a decision of the ADR; there is one list of every-chat changes; the trigger is one release after Stage 1; at the trigger the setting and the old chat path go together; ADR 0038 D7's two tests are conditions of the trigger. (Endorsing the aim only; the trigger at the end of Stage 1, at 1.0, or by a committee check; keeping the setting until a later decision, or for one release; answering the two tests in the ADR now, or setting them aside.)
48. Ruled 13 November (ADR R30, R32 to R35 and R37 to R41; V16 to V19, V25, V28, V29): DE-388 points 3 and 5 are answered and point 4 is left open; a small corpus is built in this plan; slice 0a is on the every-chat list and does not wait; operators are told by a release note only; the ADR has a limits section; the citing reminder is allowed as fixed, format-only and measured; the orchestrator rewrites the one page; the main plan holds to 3,500 words. What each declined is in `discussions/adr.md`.
49. Ruled 13 November: API rulings R73 to R84, with V20, V24 and V27. Each is listed in annex J's fourteenth fold; what each declined is in `discussions/api.md`.
50. Ruled 13 November: audit rulings 14 to 21, with V21 to V23. Each is listed in annex J's fourteenth fold; what each declined is in `discussions/audit.md`.

## M. The main plan's fuller text

Moved here from the main plan on 13 November, as they stood in Draft 16, when the main plan was cut to 3,500 words (ADR rulings R15 and R35). The main plan keeps a short form of each. Where the two differ, this annex has the detail and annexes B, E and I have the reference.

### M1. What this plan commits LQ.AI to

Each item ends by saying who decides it. Until 13 November this section was headed "By adopting this plan you accept".

1. **An agent is a new kind of file beside skills.** The PRD entry DE-211 says "extension of skill format". This plan departs from that, and revising DE-211 is a committee item. The reason: several skills load *into* one chat; an agent *chooses* the model, the skills and the knowledge for that chat. In a sentence: *a skill is a method for one task; an agent is the colleague you set up, who knows which methods, model and documents to use.* The maintainer's direction of 12 November goes further: "agents" are the product, not skills. PRD section 1.3 says "the skills are the product", so amending it is a committee item too. *Decided by the ADR; the PRD changes are separate committee items.*
2. **New harness is frozen. It is not the base.** This reverses the maintainer's own direction of 7 October, recorded in ADR 0038. Its profiles are code, not data a builder can write, and its top level has no tool loop. What is lost: plan approval, accounted budgets and durable effects. Two tools are meant to bring part of this back, on the sub-agents track: `delegate` and `plan` (see annex I, "Sub-agents and contributed agents"). The `plan` tool is not designed or sized. Ruled 13 November: that it exists and that the user approves its plan is decided in the sub-agents ADR, not on 22 November. The one page still asks the committee about it. The five reasons are in [annex F](2026-11-agent-builder-annexes.md#f-engines-and-what-stays-frozen). *Decided by the ADR, the freeze included (ruled 13 November).*
3. **Sub-agents will run in the ordinary chat loop.** That is a second place sub-agents run, beside the run tree, until a later committee decision. *The maintainer's direction, for the sub-agents ADR.*
4. **The turn is built a new way.** LQ.AI gets a system prompt, a visible file; none exists today. Every chat gets it, agent or not, on upgrade. A user can read the current text of every authored part of the system prompt: LQ.AI's, the operator's, the agent's and each loaded skill's. Fixed wording that LQ.AI's own code adds (labels, tool descriptions, the notice at a limit) is in the open-source code, not on the read screen. People can read their operator's instructions and the Organization Profile in the interface. Operators are told by a release-note line that what they write there is shown to their users (ruled 13 November). People read the text as it stands today, not the text an old turn used; that limit is accepted. An admin setting to hide both may be filed as a deferred enhancement; it is not filed. A user-written agent's instructions sit in it under a label, and the label enforces nothing. The model chooses which skill to load, and may load none or the wrong one. The [decided list](2026-11-agent-builder-annexes.md#l-decided-in-this-draft) names each choice and its alternative. *Decided by the ADR.*
5. **Each round is a full gateway request.** So every round passes the tier, pseudonymization and logging checks. The price is time, and one gateway log row per round. While a turn works, the stream carries a small event after each round (skill loaded, search run, tool called), with names and counts only, and the chat shows these as live step lines under the agent's pill. The answer itself arrives word by word from slice 3e, the last slice of Stage 1, and agents are not announced before it. *Decided by the ADR.*
6. **The server holds a chat's agent.** The chat points at one saved version. Each turn freezes that version when it starts, so a change takes effect on the next turn, and a turn that pauses resumes on the version it started with. The chat stays on its version when the owner saves a newer one; the user moves it by editing the chat. An agent can be set, swapped or removed between turns, so one chat can hold turns from several agents and from none. Each turn's record names what ran it, and each reply row stores the agent id and version it ran on. *Decided by the ADR.*
7. **A refused item stops the turn.** The notice names the item and offers "run this turn without it". It is tiresome, and deliberate: nothing is dropped silently. The check runs before the message is saved, so a refused send saves no message. It does write an audit row: the agent, the item refused and the reason. One exception to "nothing is dropped silently": a chat whose agent is retired or deleted moves to the default agent, with a line in the chat that says so. *Decided by the ADR.*
8. **Stage 1 has one end.** Nobody is told agents are usable until everything ruled into Stage 1 is on `main`: the paused-turn records, the refusal notice and slice 3e included (ruled 12 and 13 November). The cost is time: about 25 May 2027 on the build plan's estimate. Whether an operator could turn the setting on from an earlier release is open question 22. *The maintainer's ruling on build order; not an ADR decision.*
9. **Agents replace ordinary chat.** Ruled 13 November: the ADR decides this now, not only the aim. Stage 1 ships with agents off by default and labelled experimental, with a line in `docs/HONEST-STATE.md`. The setting is the operator's, for the whole install; it is not a per-person switch on the Labs page. With it on, every chat turn sent through the agent loop has an agent (admin re-runs, New harness runs and older replies have none): a chat with none chosen runs the default agent, a built-in agent file that can be read through View file like any other. The next minor release after Stage 1 turns agents on for every install, unless a stated blocker is open, and removes the setting and the old chat path together, so there is no switch back. Two tests from ADR 0038 must be shown met first: an agent turn is as visible as an ordinary turn, and the pricing rule of ADR 0035 is resolved for ordinary turns. The removal has no slice, size or date. *Decided by the ADR.*

### M2. How a turn is built: six passages

- **Step 1.** **The chat has an agent.** It is set by editing the chat, not sent with the message. The message request carries the message, the model the sender picked and, on a resend after a refusal, a `run_without` list. With agents on, a chat with none chosen runs the default agent, and clearing a chat's agent returns it to the default. A chat on the default agent always runs the default file of the running release, and has no version to move to. On an agent turn the request's model is optional: absent means the file's model, or the install's default where the file names none. A picked model lasts one turn on every agent chat, the default agent's included.
- **Step 4.** **Refuse or continue.** If a named item is not allowed, the turn is refused before any model call and no message is saved. The refusal lists each item with its state and reason, and writes an audit row that names the agent, its version and fingerprint, the item and the reason. To run without an item, the browser sends the same message again with a `run_without` list for this turn. The chat's agent is unchanged and the record shows the choice. `run_without` may name skills, knowledge bases and tools, never the model: a refused model is fixed by picking another.
- **Step 5, part 3.** the agent's instructions, labelled by the server from where it loaded the agent: "built in to LQ.AI" for agents shipped in the repo, "written by a user of this deployment" for saved ones. Version 1 has no `author` field; a file may say who wrote it under `metadata`, and that is never the label;
- **Step 8.** **The final answer.** The model answers without a tool call, or a limit is reached and one last round runs with tools off; the reply and a progress event say the limit was reached. An agent turn has two limits, and whichever comes first ends it: rounds (an operator setting, 20 by default; a load is an ordinary round; the file may lower the number, never raise it) and an optional spend limit per turn, in USD. If the user stops the turn, it ends at the next round boundary: the round in flight finishes, no further tool runs, and the reply is saved as stopped with what was gathered. With agents off, chat keeps its cap of 8 tool calls until the old chat path is removed. The spend limit is a threshold checked after each round, and only the rounds limit applies to local models. Where a spend limit is set, a turn on a paid route with no price configured is refused at the check. There is no count of tool calls within a round. A stopped reply always has text: a fixed line saying it was stopped and after how many rounds, then anything already written. Closing the tab or losing the connection stops the turn in the same way.
- **Step 9.** **The record** is written: agent id, version and fingerprint, as frozen in step 2; the skills offered and loaded; the tools offered and called. The gateway reports what it assembled on each round, in one `lq_ai_assembled` object (the LQ.AI prompt's version, a fingerprint for each part, each merged skill and its fingerprint), and the backend copies that into the record, round by round. The gateway keeps nothing of it; its routing log is unchanged. The record says what the gateway built, not what the backend asked for. Every fingerprint is over saved text a user can read. The agent has two: the file's, from the store, which View file shows; and the gateway's, over the instructions it was sent, kept under another name. `load_skill` and `search_knowledge` each also write a row in the existing tool-call log. Every chat turn's record carries the LQ.AI prompt's version and fingerprint, agents on or off. An agent turn's record carries the file's model and the model that ran.

The reply row gains three things: the agent's id, its version, and how the reply ended, one of seven values that the record repeats. A refused turn has an audit row that names the agent. An admin re-run is not wired to agent refusals in Stage 1: a refused turn saves nothing to re-run. The admin re-run is removed with the old chat path. Agents are not announced as usable until all of these records are on `main`.

Ruled on 13 November. Verified citations carry over to agent turns: `search_knowledge` returns numbered passages, the loop collects them across the turn, and the reply's quotations are checked and entered in the ledger as today. The passages the previous reply cited are carried into the next turn when the agent can search knowledge. They and attached-file text travel in a system message of their own, after the assembled one. So in Stage 1 document text leaves the system messages only as `search_knowledge` results. A turn that fails part-way always leaves a reply and a record, written together. A pause that runs out ends the turn the same way. On an agent turn that succeeds they are one write too: if the record cannot be written, the reply is not saved and the user gets an error. A version that ran in a matter cannot be deleted while the matter is open; its owner can retire it. A try in the builder does not count.
