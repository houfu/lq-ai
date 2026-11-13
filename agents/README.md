# Agent files

An agent file is Markdown with YAML front matter, like a skill's `SKILL.md`. The front matter names the agent and what it may use; the body is its instructions.

- `lq-ai.md` is the default agent, built in to LQ.AI.
- `examples/` holds example files. They are not built in.

Nothing reads these files at run time yet. The format is checked by `api/app/agents/file_format.py`, and `api/tests/agents/` checks that every file here is valid.

The smallest valid file:

```markdown
---
schema: 1
name: my-agent
description: When to use this agent.
tools: chat
---
```

Version 1 fields: `schema`, `name`, `title`, `description`, `metadata`, `model`, `skills`, `knowledge`, `tools` and `limits`. A file in this folder may also carry `version`; a pasted file's `version` is ignored. Any other field is refused. `history`, `workspace`, `subagents`, `use_as`, `memory` and `permissions` are reserved and refused.
