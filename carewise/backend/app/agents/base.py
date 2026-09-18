"""Base agent abstractions for CareWise.

The architecture follows a pattern proven in production agentic systems:
- SessionContext carries user state, conversation history, and intermediate
  agent outputs across the orchestration loop.
- BaseAgent is an abstract contract that all specialized agents implement.
- The Orchestrator (in orchestrator.py) routes requests, prevents cycles,
  and synthesizes multi-agent responses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentName(str, Enum):
    EMOTIONAL_SUPPORT = "emotional_support"
    SYMPTOM_TRACKER = "symptom_tracker"
    CARE_COORDINATOR = "care_coordinator"
    RESOURCE_GUIDE = "resource_guide"
    BURNOUT_MONITOR = "burnout_monitor"
    SAFETY = "safety"


@dataclass
class AgentResponse:
    agent: AgentName
    content: str
    handoff_to: AgentName | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_followup: bool = False


@dataclass
class SessionContext:
    """Shared state passed through every agent invocation in a turn."""
    user_id: int
    conversation_id: int
    user_message: str
    user_profile: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)  # role/content pairs
    agent_outputs: list[AgentResponse] = field(default_factory=list)
    visited_agents: set[AgentName] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def append_output(self, response: AgentResponse) -> None:
        self.agent_outputs.append(response)
        self.visited_agents.add(response.agent)

    def has_visited(self, agent: AgentName) -> bool:
        return agent in self.visited_agents


class BaseAgent(ABC):
    name: AgentName
    description: str
    system_prompt: str

    @abstractmethod
    async def handle(self, ctx: SessionContext) -> AgentResponse:
        """Process the user's message in the given session context."""
        ...

    def can_handle(self, ctx: SessionContext) -> bool:
        """Optional cheap pre-check used by intent routing. Default: True."""
        return True
