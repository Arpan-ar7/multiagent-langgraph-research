"""Streamlit UI end to end: the real script, against the in-process API with stub agents."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button

from research_system.api import client as client_module
from research_system.api.app import create_app
from research_system.api.client import ResearchClient
from research_system.config.settings import Settings
from research_system.service import ResearchService
from tests.conftest import StubAgents

pytestmark = pytest.mark.integration

SCRIPT = str(Path(__file__).parents[2] / "ui" / "streamlit_app.py")


@pytest.fixture
def api(
    stubs: StubAgents, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ResearchClient]:
    """API client for test setup; the UI script gets its own client to the same app."""
    app = create_app(ResearchService(settings, stubs.agents()))
    with TestClient(app) as http:
        monkeypatch.setattr(client_module, "ResearchClient", lambda url: ResearchClient(http=http))
        st.cache_resource.clear()
        yield ResearchClient(http=http)
    st.cache_resource.clear()


def open_ui(thread_id: str | None = None) -> AppTest:
    # Generous: a cold CI runner (first imports) took >15 s for a script run that takes ~5 s warm.
    at = AppTest.from_file(SCRIPT, default_timeout=60)
    if thread_id:
        at.session_state["thread_id"] = thread_id
    return at.run()


def button(at: AppTest, label: str) -> Button:
    return next(b for b in at.button if b.label == label)


def texts(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_landing_page_shows_form_and_settings(api: ResearchClient) -> None:
    at = open_ui()
    assert not at.exception
    assert at.title[0].value == "Multi-agent research"
    assert at.text_area(key="query") is not None
    assert at.sidebar.slider[0].label == "Sub-questions"
    assert at.sidebar.slider[0].value == 5  # server default from /health
    assert "No runs yet." in [c.value for c in at.sidebar.caption]


def test_starting_a_run_from_the_form_shows_the_report(api: ResearchClient) -> None:
    at = open_ui()
    at.text_area(key="query").input("How are widgets priced?")
    button(at, "Start research").click()
    at.run()
    assert not at.exception
    assert at.session_state["thread_id"]
    assert at.title[0].value == "How are widgets priced?"
    assert len(at.tabs) == 4
    assert "[\\[1\\]](https://example.org/costs)" in texts(at)  # clickable citation
    assert at.metric[0].label == "Coverage"


def test_completed_run_from_history(api: ResearchClient) -> None:
    thread_id = api.start("How are widgets priced?")
    list(api.events(thread_id))
    at = open_ui()
    history = [b for b in at.sidebar.button if b.key == f"run-{thread_id}"]
    assert history, "run should be listed in the sidebar history"
    history[0].click().run()
    assert not at.exception
    assert at.session_state["thread_id"] == thread_id
    assert at.tabs[1].label == "🔗 Sources (3)"


def test_plan_review_flow(api: ResearchClient, stubs: StubAgents) -> None:
    thread_id = api.start("How are widgets priced?", human_review=True)
    list(api.events(thread_id))
    at = open_ui(thread_id)
    assert not at.exception
    assert at.subheader[0].value == "Review the research plan"
    assert len(at.checkbox) == 3

    at.checkbox[1].uncheck()
    button(at, "Approve and research").click()
    at.run()
    assert not at.exception
    assert stubs.researched == ["costs", "risks"]
    assert len(at.tabs) == 4


def test_incomplete_run_can_be_resumed(api: ResearchClient, stubs: StubAgents) -> None:
    stubs.writer_errors = [RuntimeError("Rate limit exceeded: free-models-per-day")]
    thread_id = api.start("How are widgets priced?")
    list(api.events(thread_id))
    at = open_ui(thread_id)
    assert not at.exception
    assert "Rate limit exceeded" in at.error[0].value
    button(at, "▶ Resume run").click().run()
    assert not at.exception
    assert len(at.tabs) == 4 and stubs.calls["research"] == 3


def test_unreachable_api_shows_how_to_start_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_API_URL", "http://127.0.0.1:9")
    st.cache_resource.clear()
    at = open_ui()
    assert not at.exception
    assert "API not reachable" in at.sidebar.error[0].value
    st.cache_resource.clear()
