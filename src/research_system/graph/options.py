"""Per-run options.

Options are stored *in the graph state* (as a dict) rather than in `config`, so they are
checkpointed with the run: a run resumed after a crash keeps the options it started with.
"""

from __future__ import annotations

from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from research_system.config.settings import Settings


class RunOptions(BaseModel):
    """Knobs that can change per research run without code changes."""

    max_sub_questions: int = Field(default=4, ge=1, le=5)
    max_tool_calls: int = Field(default=4, ge=1, le=10)
    max_iterations: int = Field(default=2, ge=1, le=4)
    approval_threshold: int = Field(default=4, ge=1, le=5)
    human_review: bool = False

    @classmethod
    def from_settings(cls, settings: Settings, **overrides: Any) -> RunOptions:
        base = {name: getattr(settings, name) for name in cls.model_fields}
        return cls(**(base | {k: v for k, v in overrides.items() if v is not None}))

    @classmethod
    def from_state(cls, state: Any, defaults: RunOptions) -> RunOptions:
        """Options saved in the run state, falling back to build-time defaults."""
        saved = state.get("options") if isinstance(state, dict) else None
        return cls(**saved) if saved else defaults


def thread_config(thread_id: str, **extra: Any) -> RunnableConfig:
    """RunnableConfig addressing one checkpointed run."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    return cast(RunnableConfig, config | extra)
