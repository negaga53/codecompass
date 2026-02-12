"""Agent module — Copilot SDK integration."""

from codecompass.agent.agent import AgentMode, CodeCompassAgent
from codecompass.agent.prompts import (
    ARCHITECTURE_PROMPT,
    CONTRIBUTOR_PROMPT,
    ONBOARDING_SYSTEM_PROMPT,
    STALE_DOCS_PROMPT,
    WHY_QUERY_PROMPT,
    get_onboarding_prompt,
)

__all__ = [
    "AgentMode",
    "ARCHITECTURE_PROMPT",
    "CodeCompassAgent",
    "CONTRIBUTOR_PROMPT",
    "get_onboarding_prompt",
    "ONBOARDING_SYSTEM_PROMPT",
    "STALE_DOCS_PROMPT",
    "WHY_QUERY_PROMPT",
]
