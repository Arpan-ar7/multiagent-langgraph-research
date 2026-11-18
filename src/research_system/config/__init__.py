"""Configuration: typed settings and the LLM factory."""

from research_system.config.llm import LLMFactory, make_chat_model
from research_system.config.settings import ModelSpec, Settings, get_settings

__all__ = ["LLMFactory", "ModelSpec", "Settings", "get_settings", "make_chat_model"]
