# Agent files

An agent file is Markdown with YAML front matter, like a skill's `SKILL.md`. The front matter names the agent and what it may use; the body is its instructions.

What is here today:

- `lq-ai.md` is the default agent file the format ships with. It is not used yet.
- `examples/` holds two example files.

Nothing in LQ.AI loads these files yet, and no container image includes this folder. The format is checked by `api/app/agents/file_format.py`, and `api/tests/agents/` checks that every file here is valid.

The smallest valid file that a person pastes or uploads:

```markdown
---
schema: 1
name: my-agent
description: When to use this agent.
tools: chat
---
```

A file kept in this repository must also carry `version`, as a whole number of 1 or more, in plain digits. The smallest valid file kept here:

```markdown
---
schema: 1
version: 1
name: my-agent
description: When to use this agent.
tools: chat
---
```

Version 1 fields: `schema`, `version`, `name`, `title`, `description`, `metadata`, `model`, `skills`, `knowledge`, `tools` and `limits`. `version` is the only field the two kinds of file treat differently. A file kept in this repository must state it. A pasted file's `version` is ignored, with a notice, and is left out of the saved text. The one exception: a pasted file whose front matter is written as one set of fields between `{` and `}` is refused if it has `version`, because the field cannot be cut out of it. Any other field is refused. `history`, `workspace`, `subagents`, `use_as`, `memory` and `permissions` are reserved and refused.

## Characters that are refused

These characters are refused anywhere in the file, the body included:

- Control characters (U+0000 to U+001F, U+007F, and U+0080 to U+009F), except tab and the line break.
- Characters that hide text or change the order in which it is shown: the direction embeddings, overrides and pop (U+202A to U+202E), the direction isolates (U+2066 to U+2069), the zero-width space (U+200B), the zero-width no-break space (U+FEFF), the word joiner (U+2060), the invisible maths operators (U+2061 to U+2064) and the tag characters (U+E0000 to U+E007F).

In the front matter only, the line separator (U+2028) and the paragraph separator (U+2029) are also refused when written raw, because YAML reads them as line breaks.

These stay legal, because real text needs them: the zero-width joiner and non-joiner (U+200D, U+200C), the left-to-right and right-to-left marks (U+200E, U+200F) and the soft hyphen (U+00AD).

The rule has two limits:

- Some hidden characters still pass. Variation selectors (for example U+FE00 to U+FE0F) are not refused, in the body or in the front matter. They are not shown on screen as characters of their own, but the model reads them.
- Some real text is refused. Right-to-left text written with direction embeddings or isolates is refused; the same text written plainly, or with the U+200E and U+200F marks, is accepted. Flag emoji built from tag characters, such as the flags of Scotland, England and Wales, are refused.
