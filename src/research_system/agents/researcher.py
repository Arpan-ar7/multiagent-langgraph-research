"""Researcher agent: one sub-question -> evidence-backed Finding (notebook 04).

A ReAct loop built with `create_agent`, with middleware for model fallbacks and call limits,
and `ToolStrategy` structured output. `retrieved_urls` is filled by code from the tool
outputs, which is what makes citation grounding checkable.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from research_system.agents.base import today
from research_system.config.llm import LLMFactory
from research_system.prompts import RESEARCHER_SYSTEM
from research_system.schemas import Finding
from research_system.tools import extract_urls


class ResearcherError(RuntimeError):
    """The researcher finished without producing a Finding."""


class Researcher:
    """Answers one sub-question with tools and returns a structured Finding."""

    def __init__(self, llm: LLMFactory, tools: list[BaseTool], max_model_calls: int = 7) -> None:
        self.llm = llm
        self.tools = tools
        self.max_model_calls = max_model_calls

    def __call__(
        self, sub_question: str, strategy: str = "web", *, max_tool_calls: int = 4
    ) -> Finding:
        primary, *backups = self.llm.models("worker")
        middleware: list[AgentMiddleware[Any, Any, Any]] = [
            ToolCallLimitMiddleware(run_limit=max_tool_calls),
            ModelCallLimitMiddleware(run_limit=self.max_model_calls),
        ]
        if backups:
            middleware.insert(0, ModelFallbackMiddleware(*backups))
        agent = create_agent(
            model=primary,
            tools=self.tools,
            system_prompt=RESEARCHER_SYSTEM.format(today=today(), strategy=strategy),
            response_format=ToolStrategy(Finding),
            middleware=middleware,
        )
        result = agent.invoke({"messages": [HumanMessage(sub_question)]})
        finding = result.get("structured_response")
        if not isinstance(finding, Finding):
            raise ResearcherError("no structured Finding (model call limit reached?)")
        seen = {
            url
            for m in result["messages"]
            if isinstance(m, ToolMessage)
            for url in extract_urls(str(m.content))
        }
        return finding.model_copy(
            update={"sub_question": sub_question, "retrieved_urls": sorted(seen)}
        )
