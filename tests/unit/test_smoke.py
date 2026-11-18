"""Smoke tests: the package imports and core dependencies are installed."""

import research_system


def test_package_version() -> None:
    assert research_system.__version__ == "0.1.0"


def test_core_dependencies_importable() -> None:
    import langchain_groq  # noqa: F401
    import langchain_tavily  # noqa: F401
    import langgraph.graph  # noqa: F401
