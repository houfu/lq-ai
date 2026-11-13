# Agent builder: what it is and how we get there

**Status:** Draft 18, for the maintainer. **Date:** 2026-11-13. Committed to `docs/plans/` for the ADR's pull request. Lines that locate the privately tracked defects have been removed. Nothing in this plan is built. No ADR is adopted. Code facts are read, not run, except two probes named in annex H; a few are reported from private notes (annex H).
Sizes, days and dates are estimates. Reference detail is in the [annexes](2026-11-agent-builder-annexes.md). The glossary is [annex K](2026-11-agent-builder-annexes.md#k-glossary).

## Summary

1. **What it is.** An agent is one readable file: instructions, a model, a list of skills the model may load, and tools for knowledge and, later, earlier messages, a workspace of its own and sub-agents. A person builds it on one screen and puts it on a chat. The chat keeps it until the person changes it.
2. **Today.** A user cannot save a chat's set-up under a name, read it as a file, or hand it on. Chat has no system prompt of its own, loads every attached skill in full, and fetches knowledge before the model is asked.
3. **How a turn is built.** The server builds each request from the file. The system prompt is an LQ.AI prompt, the operator's text, the agent's instructions and a list of skills. The model thinks, loads a skill, searches, and repeats until it answers. Each call to the model is a round. Every round passes through the gateway, the one component that holds the provider keys.
4. **The file asks; the operator and the matter decide.** The whole file is checked before the first model call, and a refusal says why.
5. **This week.** One task, Slice 0: on a branch, the example agent's model picks a skill from a list and loads it. Shown at the 15 November call. A slice is one pull request's worth of work, about 400 changed lines.
6. **Order.** Stage 1: paste a file and use it. Stage 2: build one on screen. Stage 3: tools. Then a history tool. Stage 4: the agent's own workspace. Then agents contributed by pull request. Sub-agents: a trial, an ADR, then the build. Ruled 12 November: this order, Stage 1 finished before Stage 2 starts, and no early usable point inside Stage 1.
7. **Effort.** About 102 working days, as a floor. Stage 1 is estimated at 48 days, and that is a floor too: work the rulings require has no slice yet (annex I). At an assumed 8 days a month, Stage 1 ends about 25 May 2027, if the redesigned shell has merged by the end of March, and agents are announced as usable then. Operators get agents, off by default, in the first release after that, which has no date; the release after it turns them on for every install. The builder screen follows in early July 2027, and sub-agents in mid-November 2027 at the earliest. These are a build-plan session's estimates, with no slack. They leave out the privately tracked fixes, which are not sized: three that go first, and a fourth added on 13 November.
8. **What changes for every chat.** Every chat gets the LQ.AI system prompt. Missing skill inputs no longer refuse a skill. Tool-loop turns show tokens and cost summed over their rounds. Progress events and Stop reach every tool turn. Stage 1 ships with agents off by default, and there chat is otherwise as today. With agents on, a chat with none chosen runs the default agent, and a picked model lasts one turn. Ruled 13 November: the release after Stage 1 turns agents on for every install, unless a stated blocker is open, and removes the setting and the old chat path together. New harness stays as merged and frozen.

## What it would be

### One agent file

Every line below works in Stage 1.

```markdown
---
schema: 1
name: nda-comparer
title: NDA Comparer
description: >
  Compares a set of NDAs side by side: what counts as confidential,
  who may receive it, return or destruction, and remedies.
model: local                # a request; the matter and the skills still decide
skills: [nda-snapshot]      # the list the model may load from
knowledge: [matter]         # what the knowledge tool may search
tools: chat                 # other tools: what ordinary chat offers here
---
You compare non-disclosure agreements for a commercial legal team.

1. Search this matter's knowledge for the NDAs. Name each one.
2. Load the NDA skill before you compare.
3. Give one table. Rows: the NDAs. Columns: Confidential Information,
   Permitted Recipients, Return or Destruction, Remedies.
4. Quote the clause in each cell. Where an NDA is silent, write "not found".

Do not say which NDA is better. End with the three differences a
supervising lawyer should read first.
```

The model sees `nda-snapshot` as a name and a description, and loads the full text when it decides to.

A skill can bring its own tools and set a minimum tier. It cannot pick a model, scope knowledge or narrow the chat's tools. With one skill the gain is small. In chat, `nda-snapshot` gives the model its written body only. Its four column questions are used by the tabular page, so in this example the agent's own instructions carry the comparison.

The file holds everything its author chose: instructions, model, skills, knowledge, tools. LQ.AI's prompt and each skill are separate files a user can read. The record names each by version and fingerprint; it does not keep their text.

Later stages add lines to the same agent:

```yaml
knowledge: [matter, {name: nda-positions, optional: true}]   # Stage 2
tools: [research, connector:docstore]                        # Stage 3
limits: {max_tool_calls: 6}                                  # rounds; Stage 1 in the build plan
history: chat                                                # history tool; reserved
workspace: own                                               # Stage 4; reserved
subagents: [clause-checker@1]                                # sub-agents track; reserved
```

The smallest valid file has `schema`, `name`, `description` and `tools: chat`. Full format: [annex A](2026-11-agent-builder-annexes.md#a-file-format-v1).

### The builder screen

Stage 2 puts the file on one screen. On the left is what the operator installed, each item a card that says what it needs and what it adds. On the right are seven slots. Below them is a pane to try the build. An item that cannot be added stays visible, with the reason in words. The brief asked for "a Diablo RPG kind of thing": the screen keeps the inventory, the fixed slots, the locked items and the save file, and drops the game vocabulary, because its readers are lawyers. The drawing and the walk-through are in [annex C](2026-11-agent-builder-annexes.md#c-slices-for-stages-2-to-4-the-history-tool-and-contributed-agents).

### The file is the save file

"Download" gives the text. "Upload" and "Paste" take it back. From Stage 1 that is how people share. From Stage 2 the screen also imports and exports Claude Code's agent files.

## What this plan commits LQ.AI to

Each item says who decides it. Each is given in full in [annex M](2026-11-agent-builder-annexes.md#m-the-main-plans-fuller-text).

1. **An agent is a new kind of file beside skills.** A skill is a method for one task; an agent is the colleague you set up, who knows which methods, model and documents to use. PRD entry DE-211 and PRD section 1.3 ("the skills are the product") both change. *Decided by the ADR; the PRD changes are separate committee items.*
2. **New harness is frozen. It is not the base.** This reverses the maintainer's direction of 7 October, recorded in ADR 0038. Plan approval, accounted budgets and durable effects are lost; `delegate` and `plan`, on the sub-agents track, are meant to bring part of that back. *Decided by the ADR, the freeze included.*
3. **Sub-agents will run in the ordinary chat loop,** a second place beside the run tree, until a later committee decision. *The maintainer's direction, for the sub-agents ADR.*
4. **The turn is built a new way.** LQ.AI gets a system prompt, a visible file, on every chat. A user can read the current text of every authored part: LQ.AI's, the operator's, the agent's and each loaded skill's. Operators are told by a release note that their text is shown to their users. A user-written agent's instructions sit under a label that enforces nothing, and the model may load no skill or the wrong one. *Decided by the ADR.*
5. **Each round is a full gateway request,** so every round passes the tier, pseudonymization and logging checks. The price is time. The chat shows live step lines while a turn works; the answer arrives word by word only from slice 3e. *Decided by the ADR.*
6. **The server holds a chat's agent.** The chat points at one saved version, frozen for each turn when it starts. It stays on that version until the user moves it. One chat can hold turns from several agents, and each reply row and record names what ran it. *Decided by the ADR.*
7. **A refused item stops the turn.** The notice names the item and offers "run this turn without it". Nothing is dropped silently, with one exception: a chat whose agent is retired or deleted moves to the default agent, and says so. *Decided by the ADR.*
8. **Stage 1 has one end.** Nobody is told agents are usable until everything ruled into Stage 1 is on `main`, slice 3e included: about 25 May 2027 on the build plan's estimate. *The maintainer's ruling on build order; not an ADR decision.*
9. **Agents replace ordinary chat.** Stage 1 ships with agents off by default and labelled experimental; the setting is the operator's. The next minor release turns agents on for every install, unless a stated blocker is open, and removes the setting and the old chat path together, with no switch back. Two tests from ADR 0038 must be shown met first. The removal has no slice, size or date. *Decided by the ADR.*

## How a turn is built

1. **The chat has an agent.** It is set by editing the chat, not sent with the message. With agents on, a chat with none chosen runs the default agent, which is always the default file of the running release. The request's model is optional on an agent turn: absent means the file's model, or the install's default. A picked model lasts one turn.
2. **The server freezes the version.** It reads the saved version the chat points at and uses that id, version and fingerprint for the whole turn, pauses included. A paused turn keeps the instructions it needs in its saved state, so it finishes on that version even if the version is retired or deleted meanwhile.
3. **Ask versus allow.** Before the user's message is saved, the server checks every line of the file against what the operator switched on, the matter's terms, and what this user may reach. Every listed skill is checked now, not when it is loaded, so a tier refusal cannot arrive half-way through a turn. The check uses the model that will run: the file's, or the one the sender picked for this turn. Skills attached by hand go through the same check and the same refusal.
4. **Refuse or continue.** If a named item is not allowed, the turn is refused before any model call and no message is saved. The refusal lists each item with its state and reason, and writes an audit row. To run without an item, the browser sends the message again with a `run_without` list for this turn; the record shows the choice. `run_without` never names the model.
5. **The gateway builds the system prompt**, each part under its own heading, in this order:
   1. the LQ.AI system prompt (every chat gets this part, agent or not);
   2. operator instructions, when there are any;
   3. the agent's instructions, labelled by the server from where it loaded the agent: "built in to LQ.AI" or "written by a user of this deployment";
   4. the skills list: each allowed skill's name and description;
   5. any skills loaded so far this turn, in full.

   On agent turns that can search knowledge, the rule for citing passages is a part of its own. Its place was answered twice on 13 November, last and straight after part 1, and is not reconciled (open question 39).
6. **Tools are offered:** `load_skill`, when the file lists a skill; `search_knowledge`, in a matter, unless the file says `knowledge: none`; what `tools` asks for; each loaded skill's own tools. Later: `search_history`, the workspace tools, `delegate`.
7. **The loop.** The model thinks and calls tools. The server runs them and sends the results back. `load_skill` attaches the named skill to the request, and the gateway merges it on the next round with its usual checks. The skill stays loaded for the rest of the turn.
8. **The final answer.** The model answers without a tool call, or a limit is reached and one last round runs with tools off; the reply says which. An agent turn has two limits: rounds (an operator setting, 20 by default, which the file may lower) and an optional spend limit per turn. Stop, a closed tab or a lost connection ends the turn at the next round boundary, and the reply is saved as stopped with what was gathered.
9. **The record** is written: the agent's id, version and fingerprint, as frozen in step 2; the skills offered and loaded; the tools offered and called. On each round the gateway reports what it assembled in one `lq_ai_assembled` object, and the backend copies that into the record. So the record says what the gateway built, not what the backend asked for. Every fingerprint is over saved text a user can read.

After step 3, each item in the file is one of:

| State | Meaning |
|---|---|
| In use | Allowed |
| Not available: your operator | Installed but switched off, or not allowed here |
| Not available: this matter | The matter needs a stronger tier, or its privilege setting forbids it |
| Not available: the model's tier is too weak | A listed skill needs a stronger tier than the agent's model has |
| Not available: not found | Not installed here, or not yours |
| Needs you (Stage 3) | A connector you have not signed in to |

Tier 1 is the strongest and tier 5 the weakest. A file cannot set a tier, pseudonymization, a budget or an audit rule.

**Refusal.** A file may mark an item `optional`; then the turn runs without it and a line says what was left out.

**Records.** A saved version is never edited. The `chat.message_sent` audit row is the one full record of an agent turn. It carries ids, versions and what was used, as the gateway reported it, with a name and fingerprint for every part of the prompt. No agent, skill or prompt text enters it. So the claim is "the record says which", not "you can re-read the prompt": a past turn's text can be read back only for agent versions and the LQ.AI prompt.

The reply row gains the agent's id, its version, and how the reply ended. A refused turn has an audit row that names the agent, and saves nothing else. Agents are not announced as usable until all of these records are on `main`.

Ruled on 13 November. Verified citations carry over to agent turns: `search_knowledge` returns numbered passages, and the reply's quotations are checked against them as today. Attached-file text, and the passages the previous reply cited, travel in a system message of their own. A turn that fails part-way, or whose pause runs out, leaves a reply and a record, written together; on an agent turn a successful reply is not saved without its record. A version that ran in a matter is retired, not deleted, while the matter is open.

**Who can read the record.** In Stage 1, only someone with access to the audit log. A chat's owner sees the names of loaded skills under each reply. Reading the record through the receipts call is the goal. Where that goes was answered twice on 13 November and is not reconciled (open question 40).

Detail, with the code read: [annex B](2026-11-agent-builder-annexes.md#b-how-a-turn-is-built-and-what-is-recorded).

## Where the rest is

- **Slots, stages, the Stage 1 slice table, the exit test, dates, risks, what is not in this plan, and this week's task (Slice 0):** [annex I](2026-11-agent-builder-annexes.md#i-slots-stages-dates-and-this-week). Stage 1 was re-sized on 12 and 13 November by a build-plan session, and the maintainer made eight rulings there (B1 to B8). Stages 2 to 4 were not re-sized, so their dates are floors. File paths and code facts are in `build-plan/build-plan.md`, outside this plan.
- **The builder screen, drawn, and how a person builds an agent on it:** [annex C](2026-11-agent-builder-annexes.md#c-slices-for-stages-2-to-4-the-history-tool-and-contributed-agents).
- **The commitments and six passages of the turn, in full:** [annex M](2026-11-agent-builder-annexes.md#m-the-main-plans-fuller-text).
- **What changed since draft 4, ruling by ruling:** [annex J](2026-11-agent-builder-annexes.md#j-changes-since-draft-4).
- **Glossary:** [annex K](2026-11-agent-builder-annexes.md#k-glossary).
- **What this draft decided, with each alternative declined:** [annex L](2026-11-agent-builder-annexes.md#l-decided-in-this-draft).

## Open questions for the maintainer

Numbers are kept from earlier drafts. Settled and moved to annex J: 2, 4, 5, 7 to 11, 14, 18, 19, 24, 25 and 28 to 38.

- **1.** How many days a month go to this plan? Every date follows from the answer. At 8 a month Stage 1 ends in late May 2027, beside the roadmap's Candidate train (30 April) and the earliest 1.0 tag (May).
- **3.** Who, besides the maintainer, can review interface slices? The answer decides whether any of the eight Stage 1 screens can go to a contributor.
- **6.** On a pseudonymizing route, should the gateway cover and restore per tool (risk 3)?
- **12.** How is a `plan`'s approval recorded? Where it lives and its stage were ruled on 12 November: in the chat, on the sub-agents track.
- **13.** Until the release after Stage 1 the agents setting is the operator's, so turning it on gives every user on the install the default agent; after that release every chat has one. Should a user be able to opt out? Not yet put to the maintainer.
- **15.** Where is a dismissed "newer version" notice remembered: server or browser? Parked by the interface discussion on 13 November.
- **16.** Does the stock `gateway.yaml.example` change its `local` model to Gemma 4? A separate security-path change, after Slice 0.
- **17.** The file's name for the rounds limit (`limits.max_tool_calls` today).

Asked by the build-plan session and not ruled. Its sizes assume its recommended answers ([annex I](2026-11-agent-builder-annexes.md#i-slots-stages-dates-and-this-week)):

- **20.** May slice 0b merge before the ADR? It changes no behaviour.
- **21.** Where does "Agents" sit in the redesigned sidebar? ADR 0045 lists New, Home, Tabular, Labs and Customise, and its comments close on 20 November. Put to the maintainer on 13 November: "Decide later".
- **22.** What stops an operator turning agents on from a release cut in the middle of Stage 1? The setting ships in slice 1f-1, and releases are due before Stage 1 ends.
- **23.** Where does the LQ.AI prompt file live?
- **26.** What does the read screen show for operator instructions? The build-plan session found no such setting; the interface discussion describes one. Not reconciled.
- **27.** After the required-inputs check is removed, does the web chat still block a send when a skill's input form is incomplete? The browser checks by itself today (a survey finding, not re-checked).

Answered twice on 13 November. Which answer stands?

- **39.** Where the citing rule sits among the system prompt's parts: last, after loaded skills (API R76), or straight after the LQ.AI prompt (ADR R29).
- **40.** Where the receipts extension goes: a slice after Stage 1 is announced and before agents turn on for every install (ADR R31), or "rule after the API reports" (V26). The API discussion has since reported (annex E).

Raised by the rulings of 13 November and not put to the maintainer:

- **41.** Removing the old chat path has no slice, size or date. Where does it sit against the ruled order, and who sizes it?
- **42.** Do 22 November and "about two pages" still hold, now the ADR also decides the replacement, its timing, the removal and the freeze?
- **43.** Does "experimental" come off when agents turn on for every install? Is the untested risk that a small local model does not call tools a named blocker, once there is no server-side knowledge fetch to fall back on?
- **44.** What does the ADR say about ADRs 0025 (a breaking change), 0029 (the definition of 1.0) and 0031 (API-only clients)? And what is a New harness run once every chat turn has an agent?

Ten smaller open items, most owned by a slice or by the maintainer, are in [annex I](2026-11-agent-builder-annexes.md#open-items-with-an-owner).

**Decided in this draft:** 50 items, each with the alternative declined, are in [annex L](2026-11-agent-builder-annexes.md#l-decided-in-this-draft). Confirm each.
