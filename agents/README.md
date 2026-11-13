# Agent files

An agent file is Markdown with YAML front matter, like a skill's `SKILL.md`. The front matter names the agent and what it may use; the body is its instructions.

What is here today:

- `lq-ai.md` is the default agent file the format ships with. It is not used yet.
- `examples/` holds two example files.

Nothing in LQ.AI loads these files yet, and no container image includes this folder. The format is checked by `api/app/agents/file_format.py`, and `api/tests/agents/` checks that every file here is valid.

The smallest valid file:

```markdown
---
schema: 1
name: my-agent
description: When to use this agent.
tools: chat
---
```

Version 1 fields: `schema`, `name`, `title`, `description`, `metadata`, `model`, `skills`, `knowledge`, `tools` and `limits`. A pasted file's `version` is ignored. Any other field is refused. `history`, `workspace`, `subagents`, `use_as`, `memory` and `permissions` are reserved and refused.
