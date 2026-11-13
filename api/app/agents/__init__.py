"""Agents: the agent file format.

An agent is one readable Markdown file with YAML front matter: instructions,
a model, a list of skills the model may load, knowledge and tools. This
package holds the format itself (:mod:`app.agents.file_format`). It has no
endpoint, no table and no effect on chat yet.
"""

from __future__ import annotations

from app.agents.file_format import (
    AgentFile,
    AgentFileCheck,
    AgentFileInvalid,
    AgentFileMode,
    AgentFileNote,
    AgentLimits,
    ListedItem,
    fingerprint_agent_text,
    normalise_line_endings,
    parse_agent_file,
    validate_agent_file,
)

__all__ = [
    "AgentFile",
    "AgentFileCheck",
    "AgentFileInvalid",
    "AgentFileMode",
    "AgentFileNote",
    "AgentLimits",
    "ListedItem",
    "fingerprint_agent_text",
    "normalise_line_endings",
    "parse_agent_file",
    "validate_agent_file",
]
