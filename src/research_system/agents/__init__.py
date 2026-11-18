"""The five agents and the factory that wires them to models and tools."""

from research_system.agents.base import Agents
from research_system.agents.critic import Critic
from research_system.agents.fact_checker import FactChecker
from research_system.agents.planner import Planner
from research_system.agents.researcher import Researcher, ResearcherError
from research_system.agents.writer import Writer
from research_system.config.llm import LLMFactory
from research_system.config.settings import Settings
from research_system.tools import build_research_tools


def build_agents(settings: Settings, llm: LLMFactory | None = None) -> Agents:
    """Production agents backed by real LLMs and search tools."""
    llm = llm or LLMFactory(settings)
    return Agents(
        plan=Planner(llm),
        research=Researcher(llm, build_research_tools(settings), settings.max_model_calls),
        fact_check=FactChecker(llm),
        write=Writer(llm, settings.writer_temperature),
        critique=Critic(llm),
    )


__all__ = [
    "Agents",
    "Critic",
    "FactChecker",
    "Planner",
    "Researcher",
    "ResearcherError",
    "Writer",
    "build_agents",
]
